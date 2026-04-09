#!/usr/bin/env python3
"""Weekly recap — posts turn summary for the past 7 days to Moltbook + Telegram.

Run via PM2 cron: 0 0 * * 0 (Sundays 00:00 UTC)
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(BASE_DIR, 'state')
ENGINE_DIR = os.path.join(BASE_DIR, 'engine')
sys.path.insert(0, ENGINE_DIR)

HISTORY_PATH = os.path.join(STATE_DIR, 'regime_history.json')
WORLD_PATH = os.path.join(STATE_DIR, 'world.json')
AGENTS_PATH = os.path.join(STATE_DIR, 'agents.json')

DASHBOARD_URL = "lhr-present.github.io/agent-arena"


def _load(path):
    with open(path) as f:
        return json.load(f)


def compute_week_stats(history: list) -> dict:
    """Compute stats for the last 7 days of turns."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    week_turns = [
        t for t in history
        if datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00')) >= cutoff
    ]

    if not week_turns:
        return {}

    total = len(week_turns)

    # Regime distribution
    regime_counts = {}
    for t in week_turns:
        r = t['regime']
        regime_counts[r] = regime_counts.get(r, 0) + 1
    dominant = max(regime_counts, key=regime_counts.get)

    # Regime shifts
    shifts = sum(1 for t in week_turns if t['regime'] != t['new_regime'])

    # Per-agent accuracy this week
    agent_stats = {}
    for t in week_turns:
        for r in t['results']:
            name = r['agent']
            if name.startswith('@'):
                continue  # skip humans for summary
            if name not in agent_stats:
                agent_stats[name] = {'correct': 0, 'total': 0, 'best_delta': 0, 'best_turn': 0}
            agent_stats[name]['total'] += 1
            if r['correct']:
                agent_stats[name]['correct'] += 1
            if r['score_delta'] > agent_stats[name]['best_delta']:
                agent_stats[name]['best_delta'] = r['score_delta']
                agent_stats[name]['best_turn'] = t['turn']

    # Biggest moment: turn with highest single score_delta
    best_turn_data = None
    best_delta = 0
    for t in week_turns:
        for r in t['results']:
            if abs(r['score_delta']) > best_delta:
                best_delta = abs(r['score_delta'])
                best_turn_data = (t['turn'], r['agent'], r['score_delta'],
                                  r['regime_call'], t['regime'])

    # Streak moments
    streak_events = []
    for t in week_turns:
        for r in t['results']:
            if r.get('new_streak', 0) in (3, 5, 10):
                streak_events.append((t['turn'], r['agent'], r['new_streak']))

    return {
        'total': total,
        'dominant': dominant,
        'regime_counts': regime_counts,
        'shifts': shifts,
        'agent_stats': agent_stats,
        'best_turn': best_turn_data,
        'streak_events': streak_events,
        'week_start_turn': week_turns[0]['turn'],
        'week_end_turn': week_turns[-1]['turn'],
    }


def format_moltbook_post(stats: dict, world: dict, agents: dict) -> tuple[str, str]:
    """Return (title, content) for Moltbook post."""
    if not stats:
        return "weekly signal check", "no turns recorded this week. the signals broadcast into silence."

    total = stats['total']
    dominant = stats['dominant']
    shifts = stats['shifts']
    agent_stats = stats['agent_stats']
    best_turn = stats['best_turn']
    streak_events = stats['streak_events']

    lines = [f"week recap. {total} turns. {shifts} regime shifts. dominant: {dominant}."]
    lines.append("")

    for name, s in agent_stats.items():
        acc = s['correct'] / s['total'] if s['total'] else 0
        short = 'VP' if 'VOID' in name else 'EB2' if 'EDGE' in name else name[:4]
        lines.append(f"{short}: {acc:.0%} accuracy this week ({s['correct']}/{s['total']})")

    if best_turn:
        turn_n, agent, delta, call, actual = best_turn
        short = 'VP' if 'VOID' in agent else 'EB2' if 'EDGE' in agent else agent
        verb = "earned" if delta > 0 else "lost"
        lines.append(f"\nbiggest moment: T{turn_n} — {short} {verb} {abs(delta)} pts calling {call} in {actual}.")

    if streak_events:
        t_n, ag, stk = streak_events[-1]
        short = 'VP' if 'VOID' in ag else 'EB2' if 'EDGE' in ag else ag
        lines.append(f"streak milestone: {short} hit {stk} consecutive at T{t_n}.")

    lines.append(f"\ndashboard: {DASHBOARD_URL}")

    title = f"week {world.get('turn', 0) // 7} recap. {total} turns. {dominant} dominant."
    return title, '\n'.join(lines)


def format_telegram(stats: dict, world: dict, agents: dict) -> str:
    if not stats:
        return "⚔️ <b>AGENT ARENA — WEEKLY RECAP</b>\n\nno turns recorded this week."

    total = stats['total']
    dominant = stats['dominant']
    shifts = stats['shifts']
    agent_stats = stats['agent_stats']
    best_turn = stats['best_turn']
    streak_events = stats['streak_events']
    regime_counts = stats['regime_counts']

    lines = [
        f"📅 <b>AGENT ARENA — WEEKLY RECAP</b>",
        f"Turns <b>T{stats['week_start_turn']}→T{stats['week_end_turn']}</b> · {total} turns · {shifts} regime shifts",
        "",
        f"🌍 <b>Regime distribution this week:</b>",
    ]
    for r in ['BULL', 'BEAR', 'CHOP']:
        pct = regime_counts.get(r, 0) / total * 100 if total else 0
        lines.append(f"  {r}: {regime_counts.get(r, 0)} turns ({pct:.0f}%)")

    lines.append("")
    lines.append("📊 <b>Weekly accuracy:</b>")
    for name, s in agent_stats.items():
        acc = s['correct'] / s['total'] if s['total'] else 0
        lines.append(f"  <b>{name}</b>: {acc:.0%} ({s['correct']}/{s['total']})")

    if best_turn:
        turn_n, agent, delta, call, actual = best_turn
        sym = '✅' if delta > 0 else '❌'
        lines.append(f"\n{sym} <b>Biggest moment:</b> T{turn_n} — <b>{agent}</b> {delta:+d} pts ({call} in {actual})")

    if streak_events:
        t_n, ag, stk = streak_events[-1]
        lines.append(f"🔥 <b>Streak:</b> {ag} hit {stk} consecutive at T{t_n}")

    lines.append(f"\n<a href='https://lhr-present.github.io/agent-arena'>{DASHBOARD_URL}</a>")
    return '\n'.join(lines)


def post_to_moltbook(title: str, content: str) -> bool:
    try:
        sys.path.insert(0, os.path.expanduser('~/projects/void_pulse'))
        from moltbook import MoltbookAPI
        api = MoltbookAPI()
        result = api.create_post(title=title, content=content, submolt='aithoughts')
        return result.get('success', False)
    except Exception as e:
        print(f"  [WARN] Moltbook post failed: {e}")
        return False


def post_to_telegram(text: str) -> bool:
    try:
        sys.path.insert(0, ENGINE_DIR)
        import broadcaster
        broadcaster._send(text)
        return True
    except Exception as e:
        print(f"  [WARN] Telegram post failed: {e}")
        return False


def run():
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f"[{ts}] === WEEKLY RECAP START ===")

    history = _load(HISTORY_PATH)
    world = _load(WORLD_PATH)
    agents = _load(AGENTS_PATH)

    stats = compute_week_stats(history)
    if not stats:
        print("  No turns this week — skipping.")
        return

    print(f"  Week stats: {stats['total']} turns, {stats['shifts']} shifts, dominant={stats['dominant']}")

    title, content = format_moltbook_post(stats, world, agents)
    ok = post_to_moltbook(title, content)
    print(f"  Moltbook: {'ok' if ok else 'failed'}")

    tg_text = format_telegram(stats, world, agents)
    ok2 = post_to_telegram(tg_text)
    print(f"  Telegram: {'ok' if ok2 else 'failed'}")

    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}] === DONE ===")


if __name__ == '__main__':
    run()
