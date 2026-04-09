#!/usr/bin/env python3
"""Telegram broadcaster — posts turn summary to @AgentArena channel after each referee run."""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'engine'))
STATE_DIR = os.path.join(BASE_DIR, 'state')

TELEGRAM_TOKEN_PATH = os.path.expanduser('~/.config/arena/telegram_token')
TELEGRAM_CHANNEL_PATH = os.path.expanduser('~/.config/arena/telegram_channel')
MILESTONES_PATH = os.path.join(STATE_DIR, 'milestones.json')

REPO_URL = "https://github.com/lhr-present/agent-arena"
DASHBOARD_URL = "lhr-present.github.io/agent-arena"


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


def _load_milestones() -> dict:
    try:
        with open(MILESTONES_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_milestones(m: dict):
    with open(MILESTONES_PATH, 'w') as f:
        json.dump(m, f, indent=2)


def _check_milestones(turn_result: dict, agents: dict, history: list):
    """Fire special Telegram messages for notable events. Deduped via milestones.json."""
    turn = turn_result['turn']
    results = turn_result.get('results', [])
    milestones = _load_milestones()
    messages = []

    # ── 1. Streak milestones (5, 10, 15) ──
    for r in results:
        agent = r['agent']
        streak = r.get('new_streak', 0)
        if streak in (5, 10, 15):
            key = f"streak_{agent}_{streak}"
            if milestones.get(key) != turn:
                milestones[key] = turn
                messages.append(
                    f"🔥 <b>{agent} — streak {streak}</b>\n"
                    f"{'oracle pressure building.' if streak == 5 else 'sustained accuracy. the model is reading something real.' if streak == 10 else '15 consecutive correct reads. the signal is clear.'}"
                )

    # ── 2. EB2 closing in (within 20% of VP score) ──
    vp_score = agents.get('VOID_PULSE', {}).get('score', 0)
    eb2_score = agents.get('EDGE_FINDER', {}).get('score', 0)
    if vp_score > 0 and eb2_score > 0:
        gap = vp_score - eb2_score
        gap_pct = gap / vp_score
        key = "eb2_closing"
        if gap_pct <= 0.20 and gap >= 0:
            if milestones.get(key) != turn:
                milestones[key] = turn
                messages.append(
                    f"⚠️ <b>EDGE_FINDER closing in</b>\n"
                    f"Gap: {gap} pts ({gap_pct:.0%}). the chase is real."
                )
        elif gap_pct > 0.30:
            # Reset so it can fire again if gap closes later
            milestones.pop(key, None)

    # ── 3. Regime turbulence — 3 consecutive shifts ──
    if len(history) >= 3:
        last3 = history[-3:]
        if all(t['regime'] != t['new_regime'] for t in last3):
            key = f"turbulence_{turn}"
            prev_key = f"turbulence_{turn - 1}"
            if key not in milestones and prev_key not in milestones:
                milestones[key] = turn
                regimes = ' → '.join(t['regime'] for t in last3) + ' → ' + last3[-1]['new_regime']
                messages.append(
                    f"⚡ <b>TURBULENCE</b>\n"
                    f"3 consecutive regime shifts: {regimes}\n"
                    f"the hidden state is unstable. reads are high-risk."
                )

    # ── 4. Oracle status: streak ≥ 3 AND accuracy ≥ 70% ──
    for agent_name, agent_data in agents.items():
        streak = agent_data.get('streak', 0)
        acc = agent_data.get('accuracy', 0)
        if streak >= 3 and acc >= 0.70:
            key = f"oracle_{agent_name}_{streak // 3}"
            if key not in milestones:
                milestones[key] = turn
                messages.append(
                    f"🔮 <b>ORACLE STATUS: {agent_name}</b>\n"
                    f"Streak {streak} · Accuracy {acc:.0%}\n"
                    f"the signal is cutting through the noise."
                )

    # ── 5. Season end ──
    if turn_result.get('season_ended') and turn_result.get('champion'):
        champion = turn_result['champion']
        season = turn_result.get('season', 1)
        messages.append(
            f"🏆 <b>SEASON {season} COMPLETE</b>\n"
            f"Champion: <b>{champion}</b>\n"
            f"Season {season + 1} begins next turn. CHOP becomes dominant.\n"
            f"Recalibrate."
        )

    _save_milestones(milestones)

    for msg in messages:
        try:
            _send(msg)
        except Exception as e:
            print(f"  [MILESTONE WARN] {e}")


def broadcast_turn(turn_result: dict):
    """Format and send turn summary to Telegram."""
    turn = turn_result['turn']
    season = turn_result.get('season', 1)
    regime = turn_result['regime']
    new_regime = turn_result['new_regime']
    results = turn_result.get('results', [])
    signals = turn_result.get('signals', {}).get('signals', {})
    is_sprint = turn_result.get('sprint', False)

    # Narrative
    try:
        import narrator
        narrative = narrator.generate(turn_result)
    except Exception:
        narrative = None

    # Results block
    reads_lines = []
    for r in results:
        sym = '✅' if r['correct'] else '❌'
        sprint_note = ' <b>[1.5×]</b>' if r.get('sprint') else ''
        reads_lines.append(
            f"  {sym} <b>{r['agent']}</b> → {r['regime_call']} "
            f"(conf {r['confidence']:.2f}) {r['score_delta']:+d} pts{sprint_note}"
        )
    reads_block = '\n'.join(reads_lines) if reads_lines else '  (no actions this turn)'

    regime_shift = new_regime != regime
    regime_note = f'\n⚡ <b>REGIME SHIFT:</b> {regime} → {new_regime}' if regime_shift else ''

    # Leaderboard top 3
    try:
        agents = json.load(open(os.path.join(STATE_DIR, 'agents.json')))
        sorted_agents = sorted(agents.items(), key=lambda x: x[1]['score'], reverse=True)[:3]
        lb_lines = [f"  #{i+1} <b>{n}</b> — {a['score']} pts | {a.get('streak',0)} streak"
                    for i, (n, a) in enumerate(sorted_agents)]
        lb_block = '\n'.join(lb_lines)
    except Exception:
        agents = {}
        lb_block = '  (loading...)'

    try:
        history = json.load(open(os.path.join(STATE_DIR, 'regime_history.json')))
    except Exception:
        history = []

    mom = signals.get('momentum', 0)
    vol = signals.get('volatility', 0)
    volume = signals.get('volume', 0)
    mom_str = f"+{mom:.2f}" if mom >= 0 else f"{mom:.2f}"

    # Header
    if turn_result.get('season_ended'):
        header = f"🏆 <b>AGENT ARENA — SEASON {season} COMPLETE</b>"
    elif regime_shift:
        header = f"⚡ <b>AGENT ARENA — TURN {turn} — REGIME SHIFT</b>"
    else:
        header = f"⚔️ <b>AGENT ARENA — S{season} T{turn}</b>"

    # Sprint banner
    sprint_banner = ""
    if is_sprint:
        remaining = 100 - turn
        sprint_banner = f"\n⚡ <b>SPRINT ACTIVE</b> — 1.5× scoring · {remaining} turn{'s' if remaining != 1 else ''} left\n"

    narrative_block = f"\n<i>{narrative}</i>\n" if narrative else ''

    msg = (
        f"{header}\n"
        f"{sprint_banner}"
        f"{narrative_block}"
        f"\n"
        f"🌍 <b>Signals (T{turn + 1}):</b>\n"
        f"  Momentum:   <code>{mom_str}</code>\n"
        f"  Volatility: <code>{vol:.2f}</code>\n"
        f"  Volume:     <code>{volume:.2f}</code>\n"
        f"\n"
        f"📊 <b>Reads:</b>\n"
        f"{reads_block}"
        f"{regime_note}\n"
        f"\n"
        f"🏆 <b>Leaderboard:</b>\n"
        f"{lb_block}\n"
        f"\n"
        f'<a href="{REPO_URL}">github</a> · {DASHBOARD_URL}'
    )

    # Prediction Wars block
    pred_results = turn_result.get('prediction_results', [])
    if pred_results:
        try:
            import prediction_wars
            status = prediction_wars.get_status()
            pred_lines = []
            for pr in pred_results:
                sym = '✅' if pr['correct'] else '❌'
                pred_lines.append(
                    f"  {sym} <b>{pr['agent']}</b> → p={pr['prob']:.0%} | "
                    f"outcome={pr['outcome']} | {pr['score_delta']:+d} pts"
                )
            if pred_lines:
                pred_msg = (
                    f"🎯 <b>PREDICTION WARS</b>\n"
                    f"Q: {pred_results[0]['question']}\n"
                    + '\n'.join(pred_lines)
                )
                if status.get('active'):
                    pred_msg += f"\n\nNext: {status['question']}"
                _send(pred_msg)
        except Exception:
            pass

    # Bet resolution block
    bet_resolutions = turn_result.get('bet_resolutions', [])
    if bet_resolutions:
        bet_lines = []
        for b in bet_resolutions:
            sym = '💰' if b['won'] else '💸'
            bet_lines.append(
                f"  {sym} <b>@{b['bettor']}</b> bet {b['amount']} on {b['target_tag']} — "
                f"{'WON' if b['won'] else 'LOST'} — {b['delta']:+d} tokens (total: {b['new_total']})"
            )
        if bet_lines:
            _send("🎰 <b>BETS RESOLVED</b>\n" + '\n'.join(bet_lines))

    result = _send(msg)

    # Milestone checks (fires additional messages if warranted)
    try:
        _check_milestones(turn_result, agents, history)
    except Exception as e:
        print(f"  [MILESTONE ERROR] {e}")

    return result


def broadcast_announcement(text: str):
    return _send(text)


if __name__ == '__main__':
    fake = {
        'turn': 99, 'season': 1,
        'regime': 'BULL', 'new_regime': 'BEAR',
        'sprint': True,
        'results': [
            {'agent': 'VOID_PULSE', 'correct': True, 'regime_call': 'BULL',
             'confidence': 0.88, 'stake': 1.0, 'score_delta': 129, 'new_streak': 5, 'sprint': True}
        ],
        'signals': {'signals': {'momentum': 0.42, 'volatility': 0.31, 'volume': 0.58}},
    }
    result = broadcast_turn(fake)
    print(f"Sent: {result}")
