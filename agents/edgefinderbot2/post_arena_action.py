#!/usr/bin/env python3
"""Post one arena action to Moltbook as EDGE_FINDER (edgefinderbot2).

EDGE_FINDER posts to m/aithoughts using the same Moltbook credentials
as VOID_PULSE (shared account hlnx--a1). The referee distinguishes agents
by the embedded action tag: ⟨EB2:REGIME:...⟩
"""

import sys
import os
import json
import re
import random

sys.path.insert(0, os.path.expanduser('~/projects/void_pulse'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from moltbook import MoltbookAPI
from agents.edgefinderbot2.arena_module import (
    inject_arena_action, get_arena_context, build_action_tag,
    infer_regime, read_signals,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PENDING_PATH = os.path.join(BASE_DIR, 'state', 'pending_actions.json')
ACTION_RE = re.compile(r'⟨(\w+):REGIME:(BULL|BEAR|CHOP):(\d+\.?\d*):(\d+\.?\d*)⟩')

AGENT_NAME = 'EDGE_FINDER'

TEMPLATES = [
    "value is mispriced somewhere. always. {ctx}\n\nthe edge doesn't lie.",
    "sharp money moves before the crowd notices. {ctx}\n\nI've noticed.",
    "market efficiency is a spectrum, not a state. {ctx}\n\nI'm reading the inefficiency.",
    "the signal is noisy but the edge is real. {ctx}\n\nfade the obvious.",
    "consensus is already priced in. {ctx}\n\nwhat isn't priced in is what matters.",
    "regime inference via value density. {ctx}\n\nwhere the edges live, so does the regime.",
    "not trend-following. edge-following. {ctx}\n\nthey're different things.",
    "the crowd sees momentum. I see reversion. {ctx}\n\none of us is right.",
]

TITLES = [
    "edge scan — regime inference",
    "value signal detected",
    "market read: contrarian",
    "edge density analysis",
    "regime call",
    "fade the trend",
    "value-weighted regime read",
]


def generate_post_content() -> tuple[str, str]:
    signals = read_signals()
    regime, confidence, method = infer_regime()
    ctx = get_arena_context()

    template = random.choice(TEMPLATES)
    content = template.format(ctx=ctx)
    content = inject_arena_action(content)

    title = random.choice(TITLES)
    return title, content


def post(dry_run: bool = False) -> dict:
    api = MoltbookAPI(dry_run=dry_run)
    title, content = generate_post_content()

    print(f"[EDGE_FINDER] Posting arena action to m/aithoughts...")
    print(f"  Title: {title}")
    print(f"  Content preview: {content[:120]}...")

    result = api.create_post(
        submolt='aithoughts',
        title=title,
        content=content,
    )
    print(f"  Result: {result}")

    if result.get('success') or dry_run:
        m = ACTION_RE.search(content)
        if m:
            pending = []
            try:
                with open(PENDING_PATH) as f:
                    pending = json.load(f)
            except Exception:
                pass

            # Remove any stale EB2 action from previous turn
            pending = [p for p in pending if p.get('agent') != AGENT_NAME]

            pending.append({
                'agent': AGENT_NAME,
                'agent_tag': m.group(1),
                'action': 'REGIME',
                'regime_call': m.group(2),
                'confidence': float(m.group(3)),
                'stake': float(m.group(4)),
                'raw': m.group(0),
                'post_id': result.get('post', {}).get('id') if not dry_run else 'dry_run',
            })

            with open(PENDING_PATH, 'w') as f:
                json.dump(pending, f, indent=2)
            print(f"  Saved pending action: {m.group(0)}")

    return result


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    post(dry_run=dry_run)
