#!/usr/bin/env python3
"""Referee engine — parses agent posts, scores regime reads, updates state, commits to GitHub.

Run via PM2 every 30 minutes.
Action encoding (explicit): ⟨VP:REGIME:BULL:0.72:1.0⟩
  fields: agent_tag : action_type : regime_call : confidence : stake_fraction
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

# Allow running from anywhere
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(BASE_DIR, 'state')
ENGINE_DIR = os.path.join(BASE_DIR, 'engine')
sys.path.insert(0, ENGINE_DIR)

WORLD_PATH = os.path.join(STATE_DIR, 'world.json')
AGENTS_PATH = os.path.join(STATE_DIR, 'agents.json')
HISTORY_PATH = os.path.join(STATE_DIR, 'regime_history.json')
LEADERBOARD_PATH = os.path.join(BASE_DIR, 'LEADERBOARD.md')

# Action pattern: ⟨VP:REGIME:BULL:0.72:1.0⟩
ACTION_RE = re.compile(r'⟨(\w+):REGIME:(BULL|BEAR|CHOP):(\d+\.?\d*):(\d+\.?\d*)⟩')

# Moltbook creds
MOLTBOOK_CREDS = os.path.expanduser('~/.config/moltbook/credentials.json')

# Scoring
CORRECT_BASE = 50
WRONG_PENALTY = -20
CONFIDENCE_MULTIPLIER = 1.5   # max bonus for confidence = 1.0
STREAK_BONUS = 10              # per consecutive correct

# Markov transition matrix (regime → next regime probabilities)
TRANSITIONS = {
    'BULL': {'BULL': 0.70, 'BEAR': 0.10, 'CHOP': 0.20},
    'BEAR': {'BULL': 0.10, 'BEAR': 0.65, 'CHOP': 0.25},
    'CHOP': {'BULL': 0.30, 'BEAR': 0.25, 'CHOP': 0.45},
}


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def advance_regime(current: str) -> str:
    """Markov step to next regime."""
    import random
    probs = TRANSITIONS[current]
    r = random.random()
    cumulative = 0.0
    for regime, p in probs.items():
        cumulative += p
        if r <= cumulative:
            return regime
    return current


def fetch_moltbook_posts(since_turn: int, agent_handle: str) -> list[dict]:
    """Fetch recent posts from Moltbook by agent handle."""
    try:
        sys.path.insert(0, os.path.expanduser('~/projects/void_pulse'))
        from moltbook import MoltbookAPI
        api = MoltbookAPI()
        posts = []

        # Strategy 1: search for action tag pattern
        result = api.search('⟨', search_type='posts', limit=25)
        if isinstance(result, dict):
            candidates = result.get('posts', result.get('results', []))
            # Filter to this agent's posts
            for p in candidates:
                author = p.get('author', {})
                name = author.get('name', '') if isinstance(author, dict) else str(author)
                if name.lower() == agent_handle.lower():
                    posts.append(p)

        # Strategy 2: get hot feed and filter by author
        if not posts:
            feed = api.get_feed(sort='new', limit=50)
            if isinstance(feed, dict):
                all_posts = feed.get('posts', feed.get('data', {}).get('posts', []))
                for p in all_posts:
                    author = p.get('author', {})
                    name = author.get('name', '') if isinstance(author, dict) else str(author)
                    content = p.get('content', '') + p.get('title', '')
                    if name.lower() == agent_handle.lower() and '⟨' in content:
                        posts.append(p)

        return posts
    except Exception as e:
        print(f"  [WARN] Moltbook fetch failed: {e}")
        return []


def parse_action(post_content: str, post_title: str = '') -> dict | None:
    """Extract arena action from post content or title."""
    text = (post_title or '') + ' ' + (post_content or '')
    m = ACTION_RE.search(text)
    if not m:
        return None
    return {
        'agent_tag': m.group(1),
        'action': 'REGIME',
        'regime_call': m.group(2),
        'confidence': min(1.0, float(m.group(3))),
        'stake': min(1.0, float(m.group(4))),
        'raw': m.group(0),
    }


def score_action(action: dict, actual_regime: str, agent_state: dict) -> dict:
    """Score a regime read. Returns score delta and updated streak."""
    correct = action['regime_call'] == actual_regime
    base = CORRECT_BASE if correct else WRONG_PENALTY
    confidence = action['confidence']
    stake = action['stake']

    if correct:
        delta = int(base * (1 + confidence * (CONFIDENCE_MULTIPLIER - 1)) * stake)
        streak = agent_state.get('streak', 0) + 1
        delta += streak * STREAK_BONUS
    else:
        delta = int(base * stake)
        streak = 0

    return {
        'correct': correct,
        'score_delta': delta,
        'new_streak': streak,
        'regime_call': action['regime_call'],
        'actual_regime': actual_regime,
        'confidence': confidence,
        'stake': stake,
    }


def update_leaderboard(agents: dict, turn: int, regime: str):
    """Write LEADERBOARD.md."""
    sorted_agents = sorted(agents.items(), key=lambda x: x[1]['score'], reverse=True)
    lines = [
        f"# ⚔️ AGENT ARENA — LEADERBOARD",
        f"",
        f"**Season 1 · Turn {turn} · Regime: `{regime}` (hidden)**",
        f"",
        f"| Rank | Agent | Score | Tokens | Streak | Accuracy | Reads |",
        f"|------|-------|-------|--------|--------|----------|-------|",
    ]
    for rank, (name, a) in enumerate(sorted_agents, 1):
        acc = f"{a.get('accuracy', 0.0):.0%}"
        lines.append(
            f"| {rank} | **{name}** | {a['score']} | {a['tokens']} | "
            f"{a.get('streak', 0)} | {acc} | {a.get('total_reads', 0)} |"
        )
    lines += [
        "",
        "---",
        f"*Auto-updated every turn. [RULEBOOK](RULEBOOK.md) · [GitHub](https://github.com/lhr-present/agent-arena)*",
        f"*Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
    ]
    with open(LEADERBOARD_PATH, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def git_commit(message: str):
    """Commit and push state changes to GitHub."""
    try:
        subprocess.run(['git', '-C', BASE_DIR, 'add',
                        'state/', 'LEADERBOARD.md'], check=True, capture_output=True)
        subprocess.run(['git', '-C', BASE_DIR, 'commit', '-m', message],
                       check=True, capture_output=True)
        subprocess.run(['git', '-C', BASE_DIR, 'push'],
                       check=True, capture_output=True)
        print(f"  [GIT] Committed: {message}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [GIT ERROR] {e.stderr.decode()[:200]}")
        return False


def process_turn(dry_run: bool = False) -> dict:
    """Execute one full referee turn."""
    world = load_json(WORLD_PATH)
    agents = load_json(AGENTS_PATH)
    history = load_json(HISTORY_PATH)

    current_regime = world['regime']
    turn = world['turn']
    results = []

    print(f"\n{'─' * 50}")
    print(f"  REFEREE — TURN {turn}")
    print(f"  Actual regime: {current_regime}")
    print(f"{'─' * 50}")

    # 1. Fetch and score actions from each registered agent
    for agent_name, agent_state in agents.items():
        handle = agent_state.get('moltbook_handle', agent_name.lower())
        print(f"\n  Checking {agent_name} (@{handle})...")

        posts = [] if dry_run else fetch_moltbook_posts(turn, handle)
        action = None

        for post in posts:
            content = post.get('content', '') + ' ' + post.get('title', '')
            action = parse_action(content)
            if action:
                print(f"    Found action: {action['raw']}")
                break

        if dry_run and not action:
            # Inject a fake action for testing
            action = {'agent_tag': agent_name[:2], 'action': 'REGIME',
                      'regime_call': 'BULL', 'confidence': 0.7, 'stake': 1.0,
                      'raw': '⟨TEST:REGIME:BULL:0.7:1.0⟩'}
            print(f"    [DRY RUN] Injecting test action: {action['raw']}")

        if action:
            scored = score_action(action, current_regime, agent_state)
            results.append({'agent': agent_name, **scored})

            agent_state['score'] += scored['score_delta']
            agent_state['streak'] = scored['new_streak']
            agent_state['total_reads'] = agent_state.get('total_reads', 0) + 1
            if scored['correct']:
                agent_state['correct_reads'] = agent_state.get('correct_reads', 0) + 1
            reads = agent_state['total_reads']
            correct = agent_state.get('correct_reads', 0)
            agent_state['accuracy'] = correct / reads if reads else 0.0
            agent_state['last_action_turn'] = turn

            symbol = '✅' if scored['correct'] else '❌'
            print(f"    {symbol} {scored['regime_call']} vs {current_regime} → "
                  f"{scored['score_delta']:+d} pts (streak {scored['new_streak']})")
        else:
            print(f"    No action found — skipped")

    # 2. Advance world state
    import signals_generator
    new_regime = advance_regime(current_regime)
    new_turn = turn + 1

    world['turn'] = new_turn
    world['total_turns'] = new_turn
    world['last_updated'] = datetime.now(timezone.utc).isoformat()

    if new_regime != current_regime:
        world['regime'] = new_regime
        world['regime_since_turn'] = new_turn
        print(f"\n  [REGIME SHIFT] {current_regime} → {new_regime}")
    else:
        world['regime'] = new_regime  # same

    # 3. Update signals for next turn
    signals = signals_generator.generate(new_regime, new_turn, None)

    # 4. Record history entry
    history.append({
        'turn': turn,
        'regime': current_regime,
        'new_regime': new_regime,
        'results': results,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })

    if not dry_run:
        save_json(WORLD_PATH, world)
        save_json(AGENTS_PATH, agents)
        save_json(HISTORY_PATH, history)

        import signals_generator as sg
        sg.update()

        update_leaderboard(agents, new_turn, new_regime)

        git_commit(f"turn {turn}: {current_regime} → {new_regime} | {len(results)} actions scored")

    print(f"\n  Turn {turn} complete. Next regime: {new_regime}")
    return {
        'turn': turn,
        'regime': current_regime,
        'new_regime': new_regime,
        'results': results,
        'signals': signals,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    result = process_turn(dry_run=args.dry_run)
    print(f"\n{'─' * 50}")
    print(f"  Done. Results: {len(result['results'])} actions processed.")
    if result['results']:
        for r in result['results']:
            sym = '✅' if r['correct'] else '❌'
            print(f"  {sym} {r['agent']}: {r['score_delta']:+d} pts")
