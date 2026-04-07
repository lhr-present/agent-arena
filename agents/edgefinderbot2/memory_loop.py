#!/usr/bin/env python3
"""EDGE_FINDER — Memory & Relearning Loop

Runs after each referee turn. Reads regime_history.json to find EB2's
calls vs actual outcomes, identifies patterns in mistakes, and saves
learned signal adjustments to state/eb2_memory.json.

arena_module.py reads this memory to bias its inference weights.

Usage:
    python3 agents/edgefinderbot2/memory_loop.py
    (called from run_turn.py after referee scores)
"""

import json
import os
import sys
from datetime import datetime, timezone
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_DIR = os.path.join(BASE_DIR, 'state')

HISTORY_PATH  = os.path.join(STATE_DIR, 'regime_history.json')
AGENTS_PATH   = os.path.join(STATE_DIR, 'agents.json')
SIGNALS_PATH  = os.path.join(STATE_DIR, 'world_signals.json')
MEMORY_PATH   = os.path.join(STATE_DIR, 'eb2_memory.json')
MEMORY_LOG    = os.path.join(BASE_DIR, 'EB2_MEMORY.md')

AGENT_NAME = 'EDGE_FINDER'

EMPTY_MEMORY = {
    "version": 1,
    "last_updated": None,
    "last_turn_processed": -1,

    "self": {
        "total_reads": 0,
        "correct_reads": 0,
        "accuracy": 0.0,
        "score": 0,
        "streak": 0,
        "best_streak": 0,
        "regime_accuracy": {
            "BULL": {"correct": 0, "total": 0},
            "BEAR": {"correct": 0, "total": 0},
            "CHOP": {"correct": 0, "total": 0},
        },
    },

    # What signal ranges led to correct vs wrong calls
    "signal_lessons": {
        # e.g. "BULL_correct": [{"momentum": 0.3, "volatility": 0.4, ...}, ...]
        "BULL_correct": [], "BULL_wrong": [],
        "BEAR_correct": [], "BEAR_wrong": [],
        "CHOP_correct": [], "CHOP_wrong": [],
    },

    # Learned weight adjustments for contrarian inference
    # Each entry: {"regime": "BULL", "condition": "momentum>0.35,vol<0.45", "delta": +0.1}
    "weight_adjustments": [],

    # Mistakes log: last 20 wrong calls with context
    "mistakes": [],

    # Lessons generated from patterns
    "lessons": [],
}


def load_memory() -> dict:
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return dict(EMPTY_MEMORY)


def save_memory(mem: dict):
    mem['last_updated'] = datetime.now(timezone.utc).isoformat()
    with open(MEMORY_PATH, 'w') as f:
        json.dump(mem, f, indent=2)


def load_history() -> list:
    if not os.path.exists(HISTORY_PATH):
        return []
    with open(HISTORY_PATH) as f:
        return json.load(f)


def _avg(vals: list) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _signal_snapshot(signals_data: dict, turn: int) -> dict | None:
    """Extract signal values at a given turn from history if stored."""
    # world_signals.json only has current turn — we use what we have
    if signals_data.get('turn') == turn:
        return signals_data.get('signals', {})
    return None


def analyze_mistakes(mem: dict, history: list, current_turn: int):
    """Scan history for EB2 calls, update accuracy and signal lessons."""
    last_processed = mem.get('last_turn_processed', -1)
    new_turns = [h for h in history if h.get('turn', -1) > last_processed]

    if not new_turns:
        return 0

    processed = 0
    for turn_data in new_turns:
        turn_num = turn_data.get('turn', 0)
        actual = turn_data.get('regime')
        results = turn_data.get('results', [])

        # Find EB2's result in this turn
        eb2_result = next(
            (r for r in results if r.get('agent') == AGENT_NAME or r.get('agent_tag') == 'EB2'),
            None
        )
        if not eb2_result:
            continue

        called = eb2_result.get('regime_call')
        correct = eb2_result.get('correct', False)
        confidence = eb2_result.get('confidence', 0.5)

        # Update per-regime accuracy
        reg_acc = mem['self']['regime_accuracy']
        if called in reg_acc:
            reg_acc[called]['total'] += 1
            if correct:
                reg_acc[called]['correct'] += 1

        # Update overall
        mem['self']['total_reads'] += 1
        if correct:
            mem['self']['correct_reads'] += 1

        acc = mem['self']['correct_reads'] / mem['self']['total_reads']
        mem['self']['accuracy'] = round(acc, 4)

        # Log mistakes
        if not correct:
            mistake = {
                'turn': turn_num,
                'called': called,
                'actual': actual,
                'confidence': confidence,
                'lesson': _derive_lesson(called, actual),
            }
            mem['mistakes'] = (mem['mistakes'] + [mistake])[-20:]

        mem['last_turn_processed'] = max(mem.get('last_turn_processed', -1), turn_num)
        processed += 1

    return processed


def _derive_lesson(called: str, actual: str) -> str:
    """Generate a specific lesson from a wrong call."""
    lessons = {
        ('BULL', 'BEAR'): "overshot — high momentum with rising vol was actually BEAR. fade harder.",
        ('BULL', 'CHOP'): "BULL call in low-signal environment. when unsure, default CHOP.",
        ('BEAR', 'BULL'): "underestimated continuation. momentum can persist longer than expected.",
        ('BEAR', 'CHOP'): "called BEAR but market just noisy. high vol != bear, check momentum direction.",
        ('CHOP', 'BULL'): "missed BULL entry. low momentum + low vol was quiet accumulation, not chop.",
        ('CHOP', 'BEAR'): "missed BEAR. CHOP was actually deteriorating — watch vol rising from low base.",
    }
    return lessons.get((called, actual), f"called {called}, was {actual}.")


def derive_weight_adjustments(mem: dict) -> list:
    """Analyze mistake patterns and derive signal weight adjustments.

    Returns a list of active adjustments the inference engine should apply.
    """
    adjustments = []
    reg_acc = mem['self']['regime_accuracy']
    total_reads = mem['self']['total_reads']

    if total_reads < 3:
        return []  # not enough data

    # If BULL accuracy is low, reduce BULL confidence delta
    bull_total = reg_acc['BULL']['total']
    if bull_total >= 2:
        bull_acc = reg_acc['BULL']['correct'] / bull_total
        if bull_acc < 0.40:
            adjustments.append({
                'type': 'confidence_penalty',
                'regime': 'BULL',
                'delta': -0.12,
                'reason': f"BULL accuracy {bull_acc:.0%} — systematically overcalling BULL",
            })
        elif bull_acc > 0.75:
            adjustments.append({
                'type': 'confidence_bonus',
                'regime': 'BULL',
                'delta': +0.08,
                'reason': f"BULL accuracy {bull_acc:.0%} — trust BULL signals more",
            })

    # If CHOP accuracy is high, boost CHOP confidence
    chop_total = reg_acc['CHOP']['total']
    if chop_total >= 2:
        chop_acc = reg_acc['CHOP']['correct'] / chop_total
        if chop_acc > 0.70:
            adjustments.append({
                'type': 'confidence_bonus',
                'regime': 'CHOP',
                'delta': +0.07,
                'reason': f"CHOP accuracy {chop_acc:.0%} — CHOP reads are reliable",
            })
        elif chop_acc < 0.35:
            adjustments.append({
                'type': 'confidence_penalty',
                'regime': 'CHOP',
                'delta': -0.10,
                'reason': f"CHOP accuracy {chop_acc:.0%} — stop defaulting to CHOP",
            })

    # Repeated BULL→BEAR mistakes: lower contrarian threshold
    recent_mistakes = mem['mistakes'][-10:]
    bull_to_bear = sum(1 for m in recent_mistakes if m['called'] == 'BULL' and m['actual'] == 'BEAR')
    if bull_to_bear >= 2:
        adjustments.append({
            'type': 'threshold_shift',
            'regime': 'BEAR',
            'delta': +0.06,
            'reason': f"{bull_to_bear} recent BULL→BEAR mistakes — be quicker to call BEAR",
        })

    return adjustments


def generate_lesson_text(mem: dict) -> str:
    """Generate a human-readable lesson summary from current memory."""
    acc = mem['self']['accuracy']
    total = mem['self']['total_reads']
    mistakes = mem['mistakes'][-5:]
    adjustments = mem.get('weight_adjustments', [])

    lines = [f"accuracy: {acc:.0%} over {total} reads"]

    for reg in ['BULL', 'BEAR', 'CHOP']:
        r = mem['self']['regime_accuracy'][reg]
        if r['total'] > 0:
            lines.append(f"  {reg}: {r['correct']}/{r['total']} ({r['correct']/r['total']:.0%})")

    if mistakes:
        lines.append("recent mistakes:")
        for m in mistakes:
            lines.append(f"  turn {m['turn']}: called {m['called']}, was {m['actual']} — {m['lesson']}")

    if adjustments:
        lines.append("active adjustments:")
        for a in adjustments:
            lines.append(f"  [{a['type']}] {a['regime']} {a['delta']:+.2f}: {a['reason']}")

    return "\n".join(lines)


def export_markdown(mem: dict):
    """Write EB2_MEMORY.md for human/Moltbook consumption."""
    reg_acc = mem['self']['regime_accuracy']

    def pct(r):
        return f"{r['correct']}/{r['total']} ({r['correct']/r['total']:.0%})" if r['total'] else "0/0 (—)"

    lines = [
        "# EDGE_FINDER — Memory Log",
        "",
        f"*Last updated: turn {mem.get('last_turn_processed', '?')}*",
        "",
        "## Performance",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Accuracy | {mem['self']['accuracy']:.0%} |",
        f"| Total reads | {mem['self']['total_reads']} |",
        f"| BULL accuracy | {pct(reg_acc['BULL'])} |",
        f"| BEAR accuracy | {pct(reg_acc['BEAR'])} |",
        f"| CHOP accuracy | {pct(reg_acc['CHOP'])} |",
        "",
    ]

    adjustments = mem.get('weight_adjustments', [])
    if adjustments:
        lines += [
            "## Active Adjustments (learned)",
            "",
        ]
        for a in adjustments:
            lines.append(f"- **{a['regime']}** {a['delta']:+.2f} — {a['reason']}")
        lines.append("")

    mistakes = mem.get('mistakes', [])
    if mistakes:
        lines += [
            "## Recent Mistakes",
            "",
            "| Turn | Called | Actual | Lesson |",
            "|------|--------|--------|--------|",
        ]
        for m in mistakes[-8:]:
            lines.append(f"| {m['turn']} | {m['called']} | {m['actual']} | {m['lesson']} |")
        lines.append("")

    lessons = mem.get('lessons', [])
    if lessons:
        lines += ["## Learned Lessons", ""]
        for l in lessons[-5:]:
            lines.append(f"- {l}")
        lines.append("")

    with open(MEMORY_LOG, 'w') as f:
        f.write("\n".join(lines))


def run():
    print(f"[EB2 memory] Loading history...")
    mem = load_memory()
    history = load_history()

    agents = {}
    if os.path.exists(AGENTS_PATH):
        with open(AGENTS_PATH) as f:
            agents = json.load(f)

    agent_state = agents.get(AGENT_NAME, {})
    mem['self']['score'] = agent_state.get('score', 0)
    mem['self']['streak'] = agent_state.get('streak', 0)
    mem['self']['best_streak'] = max(
        mem['self'].get('best_streak', 0),
        agent_state.get('streak', 0)
    )

    current_turn = agent_state.get('last_action_turn', 0) or 0

    n = analyze_mistakes(mem, history, current_turn)
    print(f"[EB2 memory] Processed {n} new turn(s).")

    # Derive and save weight adjustments
    adjustments = derive_weight_adjustments(mem)
    mem['weight_adjustments'] = adjustments

    # Add a lesson if we have enough data
    if mem['self']['total_reads'] > 0 and mem['self']['total_reads'] % 5 == 0:
        lesson = generate_lesson_text(mem)
        mem.setdefault('lessons', []).append(lesson)
        mem['lessons'] = mem['lessons'][-10:]

    save_memory(mem)
    export_markdown(mem)
    print(f"[EB2 memory] Saved. Accuracy: {mem['self']['accuracy']:.0%}, "
          f"adjustments: {len(adjustments)}")

    if adjustments:
        for a in adjustments:
            print(f"  [{a['type']}] {a['regime']} {a['delta']:+.2f}: {a['reason']}")


if __name__ == '__main__':
    run()
