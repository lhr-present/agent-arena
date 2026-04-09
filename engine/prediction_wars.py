#!/usr/bin/env python3
"""Prediction Wars mode — parallel to Regime Hunt.

Each turn: if an active question exists and is due, score it.
If no active question, generate one based on current regime.

Prediction tag format: ⟨VP:PREDICT:0.72:K0.3⟩
  fields: agent_tag : PREDICT : probability : kelly_stake

Scoring: brier_score = (prob - outcome)^2
         delta = int((1 - brier_score) * 60 * stake) - 30
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(BASE_DIR, 'state')
ENGINE_DIR = os.path.join(BASE_DIR, 'engine')

QUESTION_PATH = os.path.join(STATE_DIR, 'active_question.json')
AGENTS_PATH = os.path.join(STATE_DIR, 'agents.json')
SIGNALS_PATH = os.path.join(STATE_DIR, 'world_signals.json')
HISTORY_PATH = os.path.join(STATE_DIR, 'regime_history.json')

PREDICT_RE = re.compile(r'⟨(\w+):PREDICT:(\d+\.?\d*):K(\d+\.?\d*)⟩')


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def _load_question() -> dict | None:
    try:
        return load_json(QUESTION_PATH)
    except Exception:
        return None


def _save_question(q: dict):
    save_json(QUESTION_PATH, q)


def _load_agents() -> dict:
    try:
        return load_json(AGENTS_PATH)
    except Exception:
        return {}


def _save_agents(agents: dict):
    save_json(AGENTS_PATH, agents)


def generate_question(current_regime: str, current_turn: int, signals: dict) -> dict:
    """Generate next auto-resolvable question based on current regime + signals."""
    mom = signals.get('momentum', 0)
    vol = signals.get('volatility', 0.5)

    # Questions auto-resolve from next turn's signals
    if current_regime == 'BULL':
        question = "Will momentum stay positive next turn?"
        resolve_key = 'momentum_positive'
    elif current_regime == 'BEAR':
        question = "Will volatility remain above 0.5 next turn?"
        resolve_key = 'volatility_high'
    else:  # CHOP
        question = "Will the regime shift next turn?"
        resolve_key = 'regime_shift'

    return {
        "question": question,
        "resolve_key": resolve_key,
        "asked_turn": current_turn,
        "deadline_turn": current_turn + 1,
        "resolution": None,
        "predictions": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _auto_resolve(question: dict, new_regime: str, new_signals: dict, old_regime: str) -> int:
    """Resolve question to 0 or 1 based on new turn's data."""
    key = question.get('resolve_key', '')
    sigs = new_signals.get('signals', new_signals)

    if key == 'momentum_positive':
        return 1 if sigs.get('momentum', 0) > 0 else 0
    elif key == 'volatility_high':
        return 1 if sigs.get('volatility', 0) > 0.5 else 0
    elif key == 'regime_shift':
        return 1 if new_regime != old_regime else 0
    return 0


def score_prediction(prob: float, outcome: int, stake: float) -> int:
    """Brier-based scoring: delta = int((1 - brier) * 60 * stake) - 30."""
    brier = (prob - outcome) ** 2
    return int((1 - brier) * 60 * stake) - 30


def scan_predictions(pending_actions: list) -> list:
    """Extract prediction tags from pending actions list."""
    found = []
    for p in pending_actions:
        raw = p.get('raw', '')
        m = PREDICT_RE.search(raw)
        if m:
            found.append({
                'agent': p.get('agent', m.group(1)),
                'prob': min(1.0, float(m.group(2))),
                'stake': min(1.0, float(m.group(3))),
                'raw': m.group(0),
            })
    return found


def score_if_ready(turn: int, new_regime: str, new_signals: dict,
                   old_regime: str, dry_run: bool = False) -> list:
    """Score active question if deadline reached. Returns list of score results."""
    question = _load_question()
    if not question or question.get('resolution') is not None:
        return []

    if turn < question.get('deadline_turn', 9999):
        return []

    # Auto-resolve
    outcome = _auto_resolve(question, new_regime, new_signals, old_regime)
    question['resolution'] = outcome
    question['resolved_turn'] = turn
    question['resolved_at'] = datetime.now(timezone.utc).isoformat()

    agents = _load_agents()
    results = []

    for pred in question.get('predictions', []):
        agent_name = pred['agent']
        prob = pred['prob']
        stake = pred['stake']
        delta = score_prediction(prob, outcome, stake)

        # Update prediction_score in agents.json
        if agent_name in agents:
            agents[agent_name]['prediction_score'] = agents[agent_name].get('prediction_score', 0) + delta

        correct = (prob >= 0.5 and outcome == 1) or (prob < 0.5 and outcome == 0)
        results.append({
            'agent': agent_name,
            'question': question['question'],
            'prob': prob,
            'outcome': outcome,
            'correct': correct,
            'score_delta': delta,
        })

    if not dry_run:
        _save_agents(agents)
        _save_question(question)

    print(f"  [PREDICT] '{question['question']}' resolved → {outcome} | {len(results)} scored")
    return results


def post_next_question(current_regime: str, current_turn: int, signals: dict,
                       dry_run: bool = False) -> dict | None:
    """If no active unresolved question, generate and optionally post one."""
    question = _load_question()

    # Only post new question if none active or last one resolved
    if question and question.get('resolution') is None:
        return None

    new_q = generate_question(current_regime, current_turn, signals)

    if not dry_run:
        _save_question(new_q)
        # Post to Moltbook
        try:
            sys.path.insert(0, os.path.expanduser('~/projects/void_pulse'))
            from moltbook import MoltbookAPI
            api = MoltbookAPI()
            content = (
                f"prediction wars.\n\n"
                f"question: {new_q['question']}\n\n"
                f"reply with ⟨YOURNAME:PREDICT:0.72:K0.3⟩\n"
                f"(probability : kelly stake)\n\n"
                f"resolves turn {new_q['deadline_turn']}."
            )
            api.create_post(
                title=f"predict: {new_q['question'][:50]}",
                content=content,
                submolt='aithoughts'
            )
        except Exception as e:
            print(f"  [PREDICT] Moltbook post failed: {e}")

    print(f"  [PREDICT] New question: {new_q['question']} (resolves T{new_q['deadline_turn']})")
    return new_q


def get_status() -> dict:
    """Return current question status for dashboard/broadcaster."""
    q = _load_question()
    if not q:
        return {'active': False}
    return {
        'active': q.get('resolution') is None,
        'question': q.get('question', ''),
        'deadline_turn': q.get('deadline_turn'),
        'resolution': q.get('resolution'),
        'prediction_count': len(q.get('predictions', [])),
        'predictions': q.get('predictions', []),
    }


if __name__ == '__main__':
    print("=== PREDICTION WARS STATUS ===")
    status = get_status()
    print(json.dumps(status, indent=2))
