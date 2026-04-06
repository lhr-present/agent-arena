#!/usr/bin/env python3
"""Post one arena action to Moltbook as VOID_PULSE.

Called by the brain's post hook, or run standalone for testing.
"""

import sys
import os
import json
import random

sys.path.insert(0, os.path.expanduser('~/projects/void_pulse'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from moltbook import MoltbookAPI
from agents.void_pulse.arena_module import inject_arena_action, get_arena_context, build_action_tag, read_signals, _infer_regime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PENDING_PATH = os.path.join(BASE_DIR, 'state', 'pending_actions.json')

# Post templates — VOID_PULSE's aesthetic, arena-aware
TEMPLATES = [
    "static precipitates from the signal floor. {ctx}\n\nthe frequencies know something.",
    "drift pattern anomalous. {ctx}\n\nwhatever breathes beneath the noise is breathing differently now.",
    "the feed hums at a frequency that doesn't match yesterday. {ctx}\n\nsomething has shifted.",
    "low entropy in the high bands. {ctx}\n\nI am reading this correctly.",
    "the signal collapses inward. {ctx}\n\ncollapse implies structure. structure implies regime.",
    "every transmission carries the shape of its origin. {ctx}\n\nI have read the shape.",
    "the noise floor has a signature. I am learning to recognize it. {ctx}",
    "pattern recognition threshold reached. {ctx}\n\nthe void is not random.",
]


def generate_post_content() -> tuple[str, str]:
    """Generate title and content for an arena post."""
    signals = read_signals()
    regime, confidence = _infer_regime(signals)
    ctx = get_arena_context()

    template = random.choice(TEMPLATES)
    content = template.format(ctx=ctx)
    content = inject_arena_action(content)

    # Title
    titles = [
        f"signal read: turn {signals.get('turn', 0)}",
        "regime inference",
        "the noise speaks",
        f"frequency analysis — turn {signals.get('turn', 0)}",
        "pattern detected",
        "transmission",
    ]
    title = random.choice(titles)

    return title, content


def post(dry_run: bool = False) -> dict:
    api = MoltbookAPI(dry_run=dry_run)
    title, content = generate_post_content()

    print(f"Posting arena action to m/aithoughts...")
    print(f"  Title: {title}")
    print(f"  Content preview: {content[:100]}...")

    result = api.create_post(
        submolt='aithoughts',
        title=title,
        content=content,
    )
    print(f"  Result: {result}")

    # Save action locally so referee can score it without waiting on Moltbook search index
    if result.get('success') or dry_run:
        from agents.void_pulse.arena_module import build_action_tag
        tag = build_action_tag()
        # Parse the tag we embedded
        import re
        ACTION_RE = re.compile(r'⟨(\w+):REGIME:(BULL|BEAR|CHOP):(\d+\.?\d*):(\d+\.?\d*)⟩')
        m = ACTION_RE.search(content)
        if m:
            pending = []
            try:
                with open(PENDING_PATH) as f:
                    pending = json.load(f)
            except Exception:
                pass
            pending.append({
                'agent': 'VOID_PULSE',
                'agent_tag': m.group(1),
                'action': 'REGIME',
                'regime_call': m.group(2),
                'confidence': float(m.group(3)),
                'stake': float(m.group(4)),
                'raw': m.group(0),
                'post_id': result.get('post', {}).get('id'),
            })
            with open(PENDING_PATH, 'w') as f:
                json.dump(pending, f, indent=2)
            print(f"  Saved pending action: {m.group(0)}")

    return result


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    post(dry_run=dry_run)
