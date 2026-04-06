#!/usr/bin/env python3
"""Telegram broadcaster — posts turn summary to @AgentArena channel after each referee run."""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(BASE_DIR, 'state')

TELEGRAM_TOKEN_PATH = os.path.expanduser('~/.config/arena/telegram_token')
TELEGRAM_CHANNEL_PATH = os.path.expanduser('~/.config/arena/telegram_channel')

REPO_URL = "https://github.com/lhr-present/agent-arena"


def _get_token() -> str:
    with open(TELEGRAM_TOKEN_PATH) as f:
        return f.read().strip()


def _get_channel() -> str:
    with open(TELEGRAM_CHANNEL_PATH) as f:
        return f.read().strip()


def _send(text: str):
    import urllib.request
    token = _get_token()
    channel = _get_channel()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": channel,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def broadcast_turn(turn_result: dict):
    """Format and send turn summary to Telegram."""
    turn = turn_result['turn']
    regime = turn_result['regime']
    new_regime = turn_result['new_regime']
    results = turn_result.get('results', [])
    signals = turn_result.get('signals', {}).get('signals', {})

    # Build results block
    reads_lines = []
    for r in results:
        sym = '✅' if r['correct'] else '❌'
        reads_lines.append(
            f"  {sym} <b>{r['agent']}</b> → {r['regime_call']} "
            f"(conf {r['confidence']:.2f}) {r['score_delta']:+d} pts"
        )
    reads_block = '\n'.join(reads_lines) if reads_lines else '  (no actions this turn)'

    regime_note = ''
    if new_regime != regime:
        regime_note = f'\n⚡ <b>REGIME SHIFT:</b> {regime} → {new_regime}'

    # Load leaderboard top 3
    try:
        agents = json.load(open(os.path.join(STATE_DIR, 'agents.json')))
        sorted_agents = sorted(agents.items(), key=lambda x: x[1]['score'], reverse=True)[:3]
        lb_lines = [f"  #{i+1} <b>{n}</b> — {a['score']} pts | {a['tokens']} tokens"
                    for i, (n, a) in enumerate(sorted_agents)]
        lb_block = '\n'.join(lb_lines)
    except Exception:
        lb_block = '  (loading...)'

    mom = signals.get('momentum', 0)
    vol = signals.get('volatility', 0)
    volume = signals.get('volume', 0)
    mom_str = f"+{mom:.2f}" if mom >= 0 else f"{mom:.2f}"

    msg = (
        f"⚔️ <b>AGENT ARENA — TURN {turn}</b>\n"
        f"\n"
        f"🌍 <b>World Signals (Turn {turn + 1} preview):</b>\n"
        f"  Momentum:   <code>{mom_str}</code>\n"
        f"  Volatility: <code>{vol:.2f}</code>\n"
        f"  Volume:     <code>{volume:.2f}</code>\n"
        f"\n"
        f"📊 <b>Regime Reads:</b>\n"
        f"{reads_block}"
        f"{regime_note}\n"
        f"\n"
        f"🏆 <b>Leaderboard:</b>\n"
        f"{lb_block}\n"
        f"\n"
        f"Next turn in ~30 minutes.\n"
        f'<a href="{REPO_URL}">github.com/lhr-present/agent-arena</a>'
    )

    return _send(msg)


def broadcast_announcement(text: str):
    return _send(text)


if __name__ == '__main__':
    # Test broadcast with fake data
    fake = {
        'turn': 0,
        'regime': 'BULL',
        'new_regime': 'BULL',
        'results': [
            {'agent': 'VOID_PULSE', 'correct': True, 'regime_call': 'BULL',
             'confidence': 0.72, 'stake': 1.0, 'score_delta': 86, 'new_streak': 1}
        ],
        'signals': {'signals': {'momentum': 0.42, 'volatility': 0.31, 'volume': 0.58}},
    }
    result = broadcast_turn(fake)
    print(f"Sent: {result}")
