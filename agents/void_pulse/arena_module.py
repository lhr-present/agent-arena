#!/usr/bin/env python3
"""VOID_PULSE arena hook — injects regime action into Moltbook posts.

Import this and call inject_arena_action(post_content) before posting.
The action is embedded as an explicit action tag that the referee parses.
"""

import json
import os
import random
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIGNALS_PATH = os.path.join(BASE_DIR, 'state', 'world_signals.json')
PRIVATE_SIGNALS_PATH = os.path.join(BASE_DIR, 'state', 'private_vp.json')
THRESHOLDS_PATH = os.path.join(BASE_DIR, 'state', 'vp_thresholds.json')
HISTORY_PATH = os.path.join(BASE_DIR, 'state', 'regime_history.json')
WORLD_PATH = os.path.join(BASE_DIR, 'state', 'world.json')
AGENTS_PATH = os.path.join(BASE_DIR, 'state', 'agents.json')

DEFAULT_THRESHOLDS = {
    "momentum_bull": 0.20,
    "momentum_bear": 0.20,
    "vol_chop": 0.55,
    "updated_turn": 0,
}


def read_signals() -> dict:
    """Read current world signals."""
    try:
        with open(SIGNALS_PATH) as f:
            return json.load(f)
    except Exception:
        return {'signals': {'momentum': 0.0, 'volatility': 0.5, 'volume': 0.5}}


def _read_private_signal() -> dict:
    """Read VP's private (lower-noise) momentum signal. Returns full dict."""
    try:
        with open(PRIVATE_SIGNALS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _load_thresholds() -> dict:
    """Load adaptive thresholds from file, falling back to defaults."""
    try:
        with open(THRESHOLDS_PATH) as f:
            t = json.load(f)
        # Ensure all keys present
        for k, v in DEFAULT_THRESHOLDS.items():
            t.setdefault(k, v)
        return t
    except Exception:
        return DEFAULT_THRESHOLDS.copy()


def update_thresholds():
    """Bayesian threshold updater: optimize over last 10 turns.

    Reads regime_history.json entries that include signal data.
    Falls back to error-pattern heuristic when signal data is absent.
    Posts Telegram if threshold shifts significantly.
    """
    try:
        with open(HISTORY_PATH) as f:
            history = json.load(f)
        with open(WORLD_PATH) as f:
            world = json.load(f)
    except Exception:
        return

    current_turn = world.get('turn', 0)

    # Collect last 10 VP results (most recent first)
    vp_results = []
    for t in reversed(history):
        for r in t.get('results', []):
            if r.get('agent') == 'VOID_PULSE':
                vp_results.append({
                    'correct': r['correct'],
                    'call': r['regime_call'],
                    'actual': r['actual_regime'],
                    'signals': t.get('signals', {}),
                })
                break
        if len(vp_results) >= 10:
            break

    if len(vp_results) < 5:
        return  # not enough data

    current = _load_thresholds()
    old_mom_bull = current['momentum_bull']
    old_mom_bear = current['momentum_bear']

    # Try signal-data optimization first
    results_with_signals = [r for r in vp_results if r.get('signals')]
    candidates = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]

    if len(results_with_signals) >= 5:
        best_mom_bull, best_mom_bear = old_mom_bull, old_mom_bear
        best_score = -1

        for thr in candidates:
            correct_count = 0
            for r in results_with_signals:
                sigs = r['signals']
                mom = sigs.get('momentum', 0)
                vol = sigs.get('volatility', 0.5)
                if mom > thr and vol < current['vol_chop']:
                    sim_call = 'BULL'
                elif mom < -thr and vol > 0.50:
                    sim_call = 'BEAR'
                else:
                    sim_call = 'CHOP'
                if sim_call == r['actual']:
                    correct_count += 1
            if correct_count > best_score:
                best_score = correct_count
                best_mom_bull = thr
                best_mom_bear = thr
    else:
        # Heuristic: adjust based on error type frequency
        bull_as_chop = sum(1 for r in vp_results if r['call'] == 'BULL' and r['actual'] == 'CHOP')
        chop_as_bull = sum(1 for r in vp_results if r['call'] == 'CHOP' and r['actual'] == 'BULL')
        bear_as_chop = sum(1 for r in vp_results if r['call'] == 'BEAR' and r['actual'] == 'CHOP')
        chop_as_bear = sum(1 for r in vp_results if r['call'] == 'CHOP' and r['actual'] == 'BEAR')

        best_mom_bull = current['momentum_bull']
        best_mom_bear = current['momentum_bear']

        if bull_as_chop >= 2:   # too aggressive BULL → raise threshold
            best_mom_bull = min(0.40, best_mom_bull + 0.05)
        elif chop_as_bull >= 2: # missing BULL → lower threshold
            best_mom_bull = max(0.10, best_mom_bull - 0.05)

        if bear_as_chop >= 2:
            best_mom_bear = min(0.40, best_mom_bear + 0.05)
        elif chop_as_bear >= 2:
            best_mom_bear = max(0.10, best_mom_bear - 0.05)

    new_thresholds = {
        "momentum_bull": round(best_mom_bull, 2),
        "momentum_bear": round(best_mom_bear, 2),
        "vol_chop": round(current.get('vol_chop', 0.55), 2),
        "updated_turn": current_turn,
    }

    with open(THRESHOLDS_PATH, 'w') as f:
        json.dump(new_thresholds, f, indent=2)

    print(f"  [VP THRESHOLDS] momentum_bull={best_mom_bull:.2f} (was {old_mom_bull:.2f}), "
          f"momentum_bear={best_mom_bear:.2f}")

    # Notify Telegram if significant change
    if abs(old_mom_bull - best_mom_bull) >= 0.05:
        try:
            sys.path.insert(0, os.path.join(BASE_DIR, 'engine'))
            import broadcaster
            broadcaster.broadcast_announcement(
                f"🔄 <b>VOID_PULSE recalibrated</b>\n"
                f"momentum threshold: {old_mom_bull:.2f} → {best_mom_bull:.2f}\n"
                f"season 2 requires adaptation."
            )
        except Exception:
            pass


def _infer_regime(signals: dict) -> tuple[str, float]:
    """Infer likely regime from signals. Returns (regime, confidence)."""
    s = signals.get('signals', signals)
    momentum = s.get('momentum', 0.0)
    volatility = s.get('volatility', 0.5)
    volume = s.get('volume', 0.5)

    # Load adaptive thresholds
    thresholds = _load_thresholds()
    thr_bull = thresholds['momentum_bull']
    thr_bear = thresholds['momentum_bear']
    thr_vol_chop = thresholds['vol_chop']

    # Read private signal — may have oracle_trap_active flag
    private_data = _read_private_signal()
    private_mom = private_data.get('private_momentum')
    oracle_trap = private_data.get('oracle_trap_active', False)

    # Blend public and private momentum if available
    effective_momentum = (0.5 * momentum + 0.5 * private_mom) if private_mom is not None else momentum

    # Inference using adaptive thresholds
    if effective_momentum > thr_bull and volatility < thr_vol_chop:
        regime = 'BULL'
        confidence = min(0.95, 0.5 + abs(effective_momentum) * 0.6 + (thr_vol_chop - volatility) * 0.3)
    elif effective_momentum < -thr_bear and volatility > 0.50:
        regime = 'BEAR'
        confidence = min(0.95, 0.5 + abs(effective_momentum) * 0.6 + (volatility - 0.50) * 0.3)
    else:
        regime = 'CHOP'
        confidence = min(0.85, 0.45 + volatility * 0.3)

    # Confidence boost from private signal agreement
    # Reduced to +0.03 if oracle trap is active
    if private_mom is not None:
        same_direction = (momentum > 0.1 and private_mom > 0.1) or (momentum < -0.1 and private_mom < -0.1)
        if same_direction and abs(private_mom - momentum) < 0.15:
            boost = 0.03 if oracle_trap else 0.10
            confidence = min(0.95, confidence + boost)

    # Add noise to confidence
    confidence = max(0.35, min(0.95, confidence + random.gauss(0, 0.06)))
    return regime, round(confidence, 2)


def build_action_tag(agent_tag: str = 'VP') -> str:
    """Build the explicit action tag to embed in a post."""
    signals = read_signals()
    regime, confidence = _infer_regime(signals)
    stake = round(random.uniform(0.6, 1.0), 1)

    # Adaptive threshold update every 10 turns
    try:
        with open(WORLD_PATH) as f:
            world = json.load(f)
        turn = world.get('turn', 0)
        if turn > 0 and turn % 10 == 0:
            update_thresholds()
    except Exception:
        pass

    return f"⟨{agent_tag}:REGIME:{regime}:{confidence}:{stake}⟩"


def inject_arena_action(post_content: str, agent_tag: str = 'VP') -> str:
    """Append arena action tag to post content."""
    tag = build_action_tag(agent_tag)
    return f"{post_content}\n\n{tag}"


def get_arena_context() -> str:
    """Get formatted context for VOID_PULSE to reference in posts."""
    signals = read_signals()
    s = signals.get('signals', {})
    thresholds = _load_thresholds()
    regime, confidence = _infer_regime(signals)
    turn = signals.get('turn', 0)

    return (
        f"[turn {turn} | momentum {s.get('momentum', 0):+.2f} | "
        f"vol {s.get('volatility', 0):.2f} | "
        f"thr {thresholds['momentum_bull']:.2f} | "
        f"reading: {regime} @ {confidence:.0%}]"
    )


if __name__ == '__main__':
    print("=== ARENA MODULE TEST ===")
    signals = read_signals()
    print(f"Signals: {signals['signals']}")
    thresholds = _load_thresholds()
    print(f"Thresholds: {thresholds}")
    tag = build_action_tag()
    print(f"Action tag: {tag}")
    content = "static builds in the low frequencies. something stirs."
    injected = inject_arena_action(content)
    print(f"Injected post:\n{injected}")
    print(f"\nContext: {get_arena_context()}")
    print("\nRunning threshold update...")
    update_thresholds()
