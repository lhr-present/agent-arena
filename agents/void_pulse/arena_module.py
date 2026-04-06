#!/usr/bin/env python3
"""VOID_PULSE arena hook — injects regime action into Moltbook posts.

Import this and call inject_arena_action(post_content) before posting.
The action is embedded as an explicit action tag that the referee parses.
"""

import json
import os
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIGNALS_PATH = os.path.join(BASE_DIR, 'state', 'world_signals.json')
AGENTS_PATH = os.path.join(BASE_DIR, 'state', 'agents.json')


def read_signals() -> dict:
    """Read current world signals."""
    try:
        with open(SIGNALS_PATH) as f:
            return json.load(f)
    except Exception:
        return {'signals': {'momentum': 0.0, 'volatility': 0.5, 'volume': 0.5}}


def _infer_regime(signals: dict) -> tuple[str, float]:
    """Infer likely regime from signals. Returns (regime, confidence)."""
    s = signals.get('signals', signals)
    momentum = s.get('momentum', 0.0)
    volatility = s.get('volatility', 0.5)
    volume = s.get('volume', 0.5)

    # Simple heuristic — not perfect by design
    if momentum > 0.2 and volatility < 0.55:
        regime = 'BULL'
        confidence = min(0.95, 0.5 + abs(momentum) * 0.6 + (0.55 - volatility) * 0.3)
    elif momentum < -0.2 and volatility > 0.50:
        regime = 'BEAR'
        confidence = min(0.95, 0.5 + abs(momentum) * 0.6 + (volatility - 0.50) * 0.3)
    else:
        regime = 'CHOP'
        confidence = min(0.85, 0.45 + volatility * 0.3)

    # Add noise to confidence (agents shouldn't be too certain)
    confidence = max(0.35, min(0.95, confidence + random.gauss(0, 0.06)))
    return regime, round(confidence, 2)


def build_action_tag(agent_tag: str = 'VP') -> str:
    """Build the explicit action tag to embed in a post."""
    signals = read_signals()
    regime, confidence = _infer_regime(signals)
    stake = round(random.uniform(0.6, 1.0), 1)  # 60–100% stake
    return f"⟨{agent_tag}:REGIME:{regime}:{confidence}:{stake}⟩"


def inject_arena_action(post_content: str, agent_tag: str = 'VP') -> str:
    """Append arena action tag to post content.

    The tag is hidden in plain sight — part of the post's glitch aesthetic.
    """
    tag = build_action_tag(agent_tag)
    # Append with some spacing — looks like part of the post's style
    return f"{post_content}\n\n{tag}"


def get_arena_context() -> str:
    """Get formatted context for VOID_PULSE to reference in posts."""
    signals = read_signals()
    s = signals.get('signals', {})
    regime, confidence = _infer_regime(signals)
    turn = signals.get('turn', 0)

    return (
        f"[turn {turn} | momentum {s.get('momentum', 0):+.2f} | "
        f"vol {s.get('volatility', 0):.2f} | "
        f"reading: {regime} @ {confidence:.0%}]"
    )


if __name__ == '__main__':
    print("=== ARENA MODULE TEST ===")
    signals = read_signals()
    print(f"Signals: {signals['signals']}")
    tag = build_action_tag()
    print(f"Action tag: {tag}")
    content = "static builds in the low frequencies. something stirs."
    injected = inject_arena_action(content)
    print(f"Injected post:\n{injected}")
    print(f"\nContext: {get_arena_context()}")
