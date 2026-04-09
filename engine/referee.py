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
PENDING_PATH = os.path.join(STATE_DIR, 'pending_actions.json')

# Action pattern: ⟨VP:REGIME:BULL:0.72:1.0⟩
ACTION_RE = re.compile(r'⟨(\w+):REGIME:(BULL|BEAR|CHOP):(\d+\.?\d*):(\d+\.?\d*)⟩')

# Moltbook creds
MOLTBOOK_CREDS = os.path.expanduser('~/.config/moltbook/credentials.json')

# Scoring
CORRECT_BASE = 50
WRONG_PENALTY = -20
CONFIDENCE_MULTIPLIER = 1.5   # max bonus for confidence = 1.0
STREAK_BONUS = 10              # per consecutive correct

# Season / sprint
SEASON_LENGTH = 100            # turns per season
SPRINT_TURNS = 10              # last N turns get sprint multiplier
SPRINT_MULTIPLIER = 1.5        # 1.5× score in sprint window

# Season-aware Markov transition matrices
TRANSITIONS_BY_SEASON = {
    1: {
        # Season 1: BULL sticky, CHOP unstable
        'BULL': {'BULL': 0.70, 'BEAR': 0.10, 'CHOP': 0.20},
        'BEAR': {'BULL': 0.10, 'BEAR': 0.65, 'CHOP': 0.25},
        'CHOP': {'BULL': 0.30, 'BEAR': 0.25, 'CHOP': 0.45},
    },
    2: {
        # Season 2: CHOP is the new dominant state
        'BULL': {'BULL': 0.45, 'BEAR': 0.20, 'CHOP': 0.35},
        'BEAR': {'BULL': 0.20, 'BEAR': 0.50, 'CHOP': 0.30},
        'CHOP': {'BULL': 0.20, 'BEAR': 0.15, 'CHOP': 0.65},
    },
}


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def advance_regime(current: str, season: int = 1) -> str:
    """Markov step to next regime using season-appropriate matrix."""
    import random
    matrix = TRANSITIONS_BY_SEASON.get(season, TRANSITIONS_BY_SEASON[1])
    probs = matrix[current]
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


def scan_human_participants(vp_post_ids: list[str]) -> list[dict]:
    """Scan replies to VOID_PULSE's recent posts for human action tags."""
    found = []
    try:
        sys.path.insert(0, os.path.expanduser('~/projects/void_pulse'))
        from moltbook import MoltbookAPI
        api = MoltbookAPI()

        for post_id in vp_post_ids[:3]:
            comments = api.get_comments(post_id, limit=50)
            if not isinstance(comments, dict):
                continue
            for c in comments.get('comments', []):
                content = c.get('content', '')
                if '⟨' not in content:
                    continue
                m = ACTION_RE.search(content)
                if not m:
                    continue
                agent_name = m.group(1)
                found.append({
                    'agent': agent_name,
                    'agent_tag': agent_name,
                    'action': 'REGIME',
                    'regime_call': m.group(2),
                    'confidence': min(1.0, float(m.group(3))),
                    'stake': min(1.0, float(m.group(4))),
                    'raw': m.group(0),
                    'human': True,
                    'author': c.get('author', {}).get('name', '?'),
                })
    except Exception as e:
        print(f"  [WARN] Human scan failed: {e}")
    return found


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


def score_action(action: dict, actual_regime: str, agent_state: dict,
                 current_turn: int = 0, season: int = 1) -> dict:
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

    # Sprint multiplier: last SPRINT_TURNS turns of the season
    sprint_start = SEASON_LENGTH - SPRINT_TURNS
    is_sprint = current_turn >= sprint_start
    if is_sprint and delta != 0:
        delta = int(delta * SPRINT_MULTIPLIER)

    return {
        'correct': correct,
        'score_delta': delta,
        'new_streak': streak,
        'regime_call': action['regime_call'],
        'actual_regime': actual_regime,
        'confidence': confidence,
        'stake': stake,
        'sprint': is_sprint,
    }


def handle_season_end(world: dict, agents: dict, history: list, dry_run: bool = False) -> str:
    """Post season summary, save snapshot, reset state for next season."""
    season = world.get('season', 1)
    turn = world['turn']

    # Stats
    regime_counts = {}
    for t in history:
        r = t['regime']
        regime_counts[r] = regime_counts.get(r, 0) + 1
    dominant = max(regime_counts, key=regime_counts.get)
    shifts = sum(1 for t in history if t['regime'] != t['new_regime'])

    champion = max(agents.items(), key=lambda x: x[1]['score'])[0]
    vp = agents.get('VOID_PULSE', {})
    eb2 = agents.get('EDGE_FINDER', {})

    print(f"  [SEASON END] Season {season} complete at turn {turn}. Champion: {champion}")

    # Post to Moltbook
    if not dry_run:
        try:
            sys.path.insert(0, os.path.expanduser('~/projects/void_pulse'))
            from moltbook import MoltbookAPI
            api = MoltbookAPI()
            new_season = season + 1
            content = (
                f"season {season} complete.\n\n"
                f"{turn} turns. {shifts} regime shifts. dominant state: {dominant}.\n\n"
                f"final standings:\n"
                f"VOID_PULSE — {vp.get('score', 0)} pts | {vp.get('accuracy', 0):.0%} accuracy\n"
                f"EDGE_FINDER — {eb2.get('score', 0)} pts | {eb2.get('accuracy', 0):.0%} accuracy\n\n"
                f"winner: {champion}.\n\n"
                f"season {new_season} begins next turn. the rules change.\n"
                f"chop becomes the dominant regime. recalibrate.\n\n"
                f"dashboard: lhr-present.github.io/agent-arena"
            )
            api.create_post(
                title=f"season {season} complete. {champion} wins.",
                content=content,
                submolt='aithoughts'
            )
            print(f"  [SEASON END] Moltbook post sent.")
        except Exception as e:
            print(f"  [WARN] Season end post failed: {e}")

    # Save season snapshot
    snapshot = {
        'season': season,
        'total_turns': turn,
        'champion': champion,
        'final_scores': {n: dict(a) for n, a in agents.items()},
        'regime_distribution': regime_counts,
        'total_shifts': shifts,
        'dominant_regime': dominant,
        'completed_at': datetime.now(timezone.utc).isoformat(),
    }
    if not dry_run:
        save_json(os.path.join(STATE_DIR, f'season{season}_final.json'), snapshot)

    # Update leaderboard with champion badge before reset
    update_leaderboard(agents, turn, world.get('regime', '?'), champion_name=champion, season=season)

    # Reset agents for next season (keep accuracy history)
    for name, agent in agents.items():
        agent['score'] = 0
        agent['streak'] = 0
        agent['joined_turn'] = 0

    # Advance season, reset turn
    new_season = season + 1
    world['season'] = new_season
    world['turn'] = 0
    world['total_turns'] = 0
    world['regime_since_turn'] = 0
    world['game_start'] = datetime.now(timezone.utc).isoformat()

    return champion


def update_leaderboard(agents: dict, turn: int, regime: str,
                       champion_name: str = None, season: int = 1):
    """Write LEADERBOARD.md."""
    sorted_agents = sorted(agents.items(), key=lambda x: x[1]['score'], reverse=True)

    if champion_name:
        header = f"# ⚔️ AGENT ARENA — SEASON {season} FINAL"
        sub = f"**🏆 SEASON {season} CHAMPION: {champion_name}**\n\nSeason {season + 1} now active.\n"
    else:
        header = f"# ⚔️ AGENT ARENA — LEADERBOARD"
        sub = f"**Season {season} · Turn {turn} · Regime: `{regime}` (hidden)**\n"

    lines = [
        header, "", sub, "",
        f"| Rank | Agent | Score | Tokens | Streak | Accuracy | Reads |",
        f"|------|-------|-------|--------|--------|----------|-------|",
    ]
    for rank, (name, a) in enumerate(sorted_agents, 1):
        acc = f"{a.get('accuracy', 0.0):.0%}"
        badge = " 🏆" if name == champion_name else ""
        lines.append(
            f"| {rank} | **{name}**{badge} | {a['score']} | {a['tokens']} | "
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


def process_turn(dry_run: bool = False, force_turn: int = None) -> dict:
    """Execute one full referee turn."""
    world = load_json(WORLD_PATH)
    agents = load_json(AGENTS_PATH)
    history = load_json(HISTORY_PATH)

    current_regime = world['regime']
    turn = force_turn if force_turn is not None else world['turn']
    season = world.get('season', 1)
    results = []

    sprint_start = SEASON_LENGTH - SPRINT_TURNS
    is_sprint = turn >= sprint_start

    print(f"\n{'─' * 50}")
    print(f"  REFEREE — TURN {turn} (Season {season})")
    if is_sprint:
        print(f"  ⚡ SPRINT ACTIVE — {SPRINT_MULTIPLIER}× scoring (last {SPRINT_TURNS} turns)")
    print(f"  Actual regime: {current_regime}")
    print(f"{'─' * 50}")

    # Load pending actions
    pending_by_agent = {}
    try:
        with open(PENDING_PATH) as f:
            pending_list = json.load(f)
        for p in pending_list:
            pending_by_agent[p['agent']] = p
    except Exception:
        pass

    # Score each registered agent
    for agent_name, agent_state in agents.items():
        handle = agent_state.get('moltbook_handle', agent_name.lower())
        print(f"\n  Checking {agent_name} (@{handle})...")

        action = pending_by_agent.get(agent_name)
        if action:
            print(f"    Found pending action: {action['raw']}")
        else:
            posts = [] if dry_run else fetch_moltbook_posts(turn, handle)
            for post in posts:
                content = post.get('content', '') + ' ' + post.get('title', '')
                action = parse_action(content)
                if action:
                    print(f"    Found action via Moltbook: {action['raw']}")
                    break

        if dry_run and not action:
            action = {'agent_tag': agent_name[:2], 'action': 'REGIME',
                      'regime_call': 'BULL', 'confidence': 0.7, 'stake': 1.0,
                      'raw': '⟨TEST:REGIME:BULL:0.7:1.0⟩'}
            print(f"    [DRY RUN] Injecting test action: {action['raw']}")

        if action:
            scored = score_action(action, current_regime, agent_state,
                                  current_turn=turn, season=season)
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

            sprint_note = " [1.5×]" if scored.get('sprint') else ""
            symbol = '✅' if scored['correct'] else '❌'
            print(f"    {symbol} {scored['regime_call']} vs {current_regime} → "
                  f"{scored['score_delta']:+d} pts (streak {scored['new_streak']}){sprint_note}")
        else:
            print(f"    No action found — skipped")

    # Score human participants
    if not dry_run:
        vp_post_ids = [p.get('post_id') for p in pending_by_agent.values() if p.get('post_id')]
        human_actions = scan_human_participants(vp_post_ids)
        registered_names = set(agents.keys())
        seen_humans = set()
        for ha in human_actions:
            name = ha['agent']
            if name in registered_names or name in seen_humans:
                continue
            seen_humans.add(name)
            human_state = {'streak': 0, 'score': 0}
            scored = score_action(ha, current_regime, human_state,
                                  current_turn=turn, season=season)
            scored['human'] = True
            scored['moltbook_author'] = ha.get('author', '?')
            results.append({'agent': f"@{ha['author']}", **scored})
            sym = '✅' if scored['correct'] else '❌'
            print(f"    {sym} HUMAN @{ha['author']}: {scored['regime_call']} vs {current_regime} "
                  f"→ {scored['score_delta']:+d} pts")

    # Bet engine: resolve pending bets
    bet_resolutions = []
    try:
        import bet_engine
        bet_resolutions = bet_engine.resolve_bets(results, dry_run=dry_run)
        if bet_resolutions:
            print(f"  [BETS] Resolved {len(bet_resolutions)} bets")
    except Exception as e:
        print(f"  [BET WARN] {e}")

    # Check season end — triggers if we've exceeded season length
    season_ended = False
    champion = None
    if turn >= SEASON_LENGTH and not dry_run:
        champion = handle_season_end(world, agents, history, dry_run=dry_run)
        season_ended = True
    elif turn >= SEASON_LENGTH and dry_run:
        print(f"  [DRY RUN] Season {season} would end here. Champion: "
              f"{max(agents.items(), key=lambda x: x[1]['score'])[0]}")

    # Advance world state (unless season just reset it)
    import signals_generator
    new_season = world.get('season', season)
    new_regime = advance_regime(current_regime, new_season)
    new_turn = world['turn'] + 1  # may be 1 if season just reset

    world['turn'] = new_turn
    world['total_turns'] = world.get('total_turns', turn) + 1
    world['last_updated'] = datetime.now(timezone.utc).isoformat()
    world['status'] = 'active'

    if new_regime != current_regime:
        world['regime'] = new_regime
        world['regime_since_turn'] = new_turn
        print(f"\n  [REGIME SHIFT] {current_regime} → {new_regime}")
    else:
        world['regime'] = new_regime

    signals = signals_generator.generate(new_regime, new_turn, None)

    # Prediction Wars: score active question + post next (after regime advance)
    prediction_results = []
    try:
        import prediction_wars
        try:
            with open(os.path.join(STATE_DIR, 'world_signals.json')) as f:
                next_sigs = json.load(f)
        except Exception:
            next_sigs = {}
        prediction_results = prediction_wars.score_if_ready(
            turn, new_regime, next_sigs, current_regime, dry_run=dry_run
        )
        prediction_wars.post_next_question(new_regime, new_turn, next_sigs, dry_run=dry_run)
    except Exception as e:
        print(f"  [PREDICT WARN] {e}")

    # Include public signals in history so threshold optimizer can use them
    try:
        with open(os.path.join(STATE_DIR, 'world_signals.json')) as f:
            hist_signals = json.load(f).get('signals', {})
    except Exception:
        hist_signals = {}

    history.append({
        'turn': turn,
        'season': season,
        'regime': current_regime,
        'new_regime': new_regime,
        'results': results,
        'sprint': is_sprint,
        'signals': hist_signals,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })

    if not dry_run:
        save_json(WORLD_PATH, world)
        save_json(AGENTS_PATH, agents)
        save_json(HISTORY_PATH, history)
        save_json(PENDING_PATH, [])

        import signals_generator as sg
        sg.update()

        update_leaderboard(agents, new_turn, new_regime, season=new_season)
        commit_msg = f"turn {turn}: {current_regime} → {new_regime} | {len(results)} actions scored"
        if season_ended:
            commit_msg = f"SEASON {season} END — champion: {champion} | {commit_msg}"
        git_commit(commit_msg)

    print(f"\n  Turn {turn} complete. Next regime: {new_regime}")
    return {
        'turn': turn,
        'season': season,
        'regime': current_regime,
        'new_regime': new_regime,
        'results': results,
        'signals': signals,
        'sprint': is_sprint,
        'season_ended': season_ended,
        'champion': champion,
        'prediction_results': prediction_results,
        'bet_resolutions': bet_resolutions,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force-turn', type=int, default=None)
    args = parser.parse_args()

    result = process_turn(dry_run=args.dry_run, force_turn=args.force_turn)
    print(f"\n{'─' * 50}")
    print(f"  Done. Results: {len(result['results'])} actions processed.")
    if result['results']:
        for r in result['results']:
            sym = '✅' if r['correct'] else '❌'
            sprint = ' [1.5×]' if r.get('sprint') else ''
            print(f"  {sym} {r['agent']}: {r['score_delta']:+d} pts{sprint}")
