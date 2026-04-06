#!/usr/bin/env python3
"""Narrator — generates dramatic turn summaries using Claude API.

Takes the raw turn result (signals, calls, outcomes, streak, regime) and
returns a one-paragraph story in VOID_PULSE's aesthetic.
Costs ~$0.001 per turn at claude-haiku-4-5 pricing.
"""

import json
import os

ANTHROPIC_KEY_PATH = os.path.expanduser('~/.config/arena/anthropic_key')


def _get_key() -> str:
    # Check env first, then file
    key = os.environ.get('ANTHROPIC_API_KEY')
    if key:
        return key
    with open(ANTHROPIC_KEY_PATH) as f:
        return f.read().strip()


def _build_prompt(turn_result: dict) -> str:
    turn = turn_result['turn']
    regime = turn_result['regime']
    new_regime = turn_result['new_regime']
    results = turn_result.get('results', [])
    signals = turn_result.get('signals', {}).get('signals', {})

    regime_shift = new_regime != regime
    mom = signals.get('momentum', 0)
    vol = signals.get('volatility', 0)

    # Build agent summaries
    agent_lines = []
    for r in results:
        outcome = 'correct' if r['correct'] else 'wrong'
        agent_lines.append(
            f"- {r['agent']}: called {r['regime_call']} with {r['confidence']:.0%} confidence, "
            f"was {outcome} ({r['score_delta']:+d} pts, streak {r['new_streak']})"
        )
    agents_block = '\n'.join(agent_lines) if agent_lines else '- No agents acted this turn.'

    shift_note = ''
    if regime_shift:
        shift_note = f"\nREGIME SHIFTED: {regime} → {new_regime}. This is significant."

    prompt = f"""You are writing the narrative for AGENT ARENA — a live game where AI agents read a hidden market regime.

Turn {turn} just completed. Here is what happened:

SIGNALS (what agents could see, noisy):
- Momentum: {mom:+.3f}
- Volatility: {vol:.3f}

ACTUAL REGIME: {regime} (was hidden from agents)
NEXT REGIME: {new_regime}{shift_note}

AGENT ACTIONS:
{agents_block}

Write a single paragraph (3-5 sentences) that narrates this turn dramatically.

Style rules:
- Match VOID_PULSE's glitch-aesthetic: fragmented, signal-aware, slightly ominous
- Speak about the regime as a living thing, not a data point
- Name agents directly and describe their reads with drama
- If streak is building, mention it as mounting evidence or growing resonance
- If a call was wrong, describe the misread as a gap between signal and truth
- If regime shifted, make it feel like an earthquake
- End with a hint about what the next turn's signals suggest
- NO hashtags, NO emojis, NO marketing language
- ~80 words max

Output ONLY the paragraph. Nothing else."""

    return prompt


def generate(turn_result: dict) -> str | None:
    """Generate narrative for a turn. Returns None if API unavailable."""
    try:
        import anthropic
        key = _get_key()
        client = anthropic.Anthropic(api_key=key)

        prompt = _build_prompt(turn_result)

        message = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=200,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return message.content[0].text.strip()

    except FileNotFoundError:
        return None  # Key not configured — skip silently
    except Exception as e:
        print(f"  [NARRATOR] Failed: {e}")
        return None


if __name__ == '__main__':
    # Test with Turn 2 data
    fake = {
        'turn': 2,
        'regime': 'BULL',
        'new_regime': 'BULL',
        'results': [
            {'agent': 'VOID_PULSE', 'correct': True, 'regime_call': 'BULL',
             'confidence': 0.73, 'stake': 0.7, 'score_delta': 67, 'new_streak': 2}
        ],
        'signals': {'signals': {'momentum': 0.596, 'volatility': 0.436, 'volume': 0.602}},
    }
    narrative = generate(fake)
    print(narrative or '[No API key configured]')
