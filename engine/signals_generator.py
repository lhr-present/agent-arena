#!/usr/bin/env python3
"""Signals generator — updates world_signals.json each turn.

Signals are regime-biased but noisy. Agents must infer the hidden regime.
"""

import json
import random
import math
import os
import sys
from datetime import datetime, timezone

STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'state')
WORLD_PATH = os.path.join(STATE_DIR, 'world.json')
SIGNALS_PATH = os.path.join(STATE_DIR, 'world_signals.json')

# Regime signal biases (hidden from agents — they only see the noisy output)
REGIME_PARAMS = {
    'BULL':  {'momentum_bias': 0.45, 'vol_center': 0.35, 'vol_range': 0.25, 'vol_center_vol': 0.65},
    'BEAR':  {'momentum_bias': -0.45, 'vol_center': 0.70, 'vol_range': 0.20, 'vol_center_vol': 0.45},
    'CHOP':  {'momentum_bias': 0.0, 'vol_center': 0.65, 'vol_range': 0.25, 'vol_center_vol': 0.35},
}

NOISE_LEVEL = 0.28        # ±0.28 gaussian noise on momentum (public)
PRIVATE_VP_NOISE = 0.168  # 40% less noise for VOID_PULSE private signal

# Sports edge bias by regime (for EDGE_FINDER's private signal)
# BULL = rich market, BEAR = thin market, CHOP = noisy
SPORTS_EDGE_BIAS = {
    'BULL': 0.72,
    'BEAR': 0.28,
    'CHOP': 0.50,
}

PRIVATE_VP_PATH = os.path.join(STATE_DIR, 'private_vp.json')
PRIVATE_EB2_PATH = os.path.join(STATE_DIR, 'private_eb2.json')


def _clamp(val, lo=0.0, hi=1.0):
    return max(lo, min(hi, val))


def generate(regime: str, turn: int, prev_signals: dict | None = None) -> dict:
    params = REGIME_PARAMS.get(regime, REGIME_PARAMS['CHOP'])

    # Momentum: biased + gaussian noise, smoothed with previous
    raw_momentum = params['momentum_bias'] + random.gauss(0, NOISE_LEVEL)
    raw_momentum = _clamp(raw_momentum, -1.0, 1.0)

    if prev_signals:
        prev_m = prev_signals.get('momentum', 0.0)
        momentum = 0.6 * raw_momentum + 0.4 * prev_m  # exponential smoothing
    else:
        momentum = raw_momentum

    # Volatility: regime-dependent center + noise
    raw_vol = params['vol_center'] + random.gauss(0, 0.12)
    raw_vol = _clamp(raw_vol)

    # Volume: loosely correlated with volatility, independent noise
    raw_volume = params['vol_center_vol'] + random.gauss(0, 0.15)
    raw_volume = _clamp(raw_volume)

    return {
        "turn": turn,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "signals": {
            "momentum": round(momentum, 3),
            "volatility": round(raw_vol, 3),
            "volume": round(raw_volume, 3),
        },
        "note": "Signals are noisy. Regime is hidden. Read between the lines."
    }


def _check_oracle_trap(agent_name: str) -> bool:
    """Return True if agent has oracle status (streak>=5, accuracy>=0.70)."""
    try:
        agents_path = os.path.join(STATE_DIR, 'agents.json')
        with open(agents_path) as f:
            agents = json.load(f)
        a = agents.get(agent_name, {})
        return a.get('streak', 0) >= 5 and a.get('accuracy', 0) >= 0.70
    except Exception:
        return False


def _fire_oracle_trap_alert(agent_name: str, turn: int):
    """Post Telegram alert first time oracle trap activates for an agent."""
    milestones_path = os.path.join(STATE_DIR, 'milestones.json')
    key = f"oracle_trap_{agent_name}"
    try:
        with open(milestones_path) as f:
            milestones = json.load(f)
    except Exception:
        milestones = {}

    if key not in milestones:
        milestones[key] = turn
        with open(milestones_path, 'w') as f:
            json.dump(milestones, f, indent=2)
        try:
            engine_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, engine_dir)
            import broadcaster
            broadcaster.broadcast_announcement(
                f"🎯 <b>oracle trap engaged for {agent_name}</b>\n"
                f"the edge erodes when it becomes visible.\n"
                f"private signal noise increased. the advantage attenuates."
            )
        except Exception:
            pass


def generate_private_vp(regime: str, turn: int, public_momentum: float) -> dict:
    """Private signal for VOID_PULSE: sharper momentum (40% less noise).
    Oracle trap: if VP is in oracle status, noise increases by 15% + secondary offset."""
    params = REGIME_PARAMS.get(regime, REGIME_PARAMS['CHOP'])

    oracle_trap = _check_oracle_trap('VOID_PULSE')
    noise = PRIVATE_VP_NOISE * (1.15 if oracle_trap else 1.0)

    raw = params['momentum_bias'] + random.gauss(0, noise)
    raw = _clamp(raw, -1.0, 1.0)
    if oracle_trap:
        raw += random.gauss(0, 0.08)
        raw = _clamp(raw, -1.0, 1.0)
        _fire_oracle_trap_alert('VOID_PULSE', turn)

    private_momentum = round(0.7 * raw + 0.3 * public_momentum, 3)
    return {
        "turn": turn,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "private_momentum": private_momentum,
        "oracle_trap_active": oracle_trap,
        "note": "VP private signal: reduced noise. confirms or contradicts public read.",
    }


def generate_private_eb2(regime: str, turn: int) -> dict:
    """Private signal for EDGE_FINDER: synthetic sports edge density.
    Oracle trap: if EB2 is in oracle status, edge signal gets extra noise."""
    bias = SPORTS_EDGE_BIAS.get(regime, 0.5)

    oracle_trap = _check_oracle_trap('EDGE_FINDER')
    noise = 0.18 * (1.15 if oracle_trap else 1.0)

    raw_edge = bias + random.gauss(0, noise)
    if oracle_trap:
        raw_edge += random.gauss(0, 0.08)
        _fire_oracle_trap_alert('EDGE_FINDER', turn)

    sports_edge = round(_clamp(raw_edge), 3)
    return {
        "turn": turn,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sports_edge": sports_edge,
        "oracle_trap_active": oracle_trap,
        "note": "EB2 private signal: synthetic edge density. >0.65=rich, <0.35=dry.",
    }


def update():
    with open(WORLD_PATH) as f:
        world = json.load(f)

    try:
        with open(SIGNALS_PATH) as f:
            prev = json.load(f).get('signals')
    except Exception:
        prev = None

    regime = world['regime']
    turn = world['turn']
    signals = generate(regime, turn, prev)

    with open(SIGNALS_PATH, 'w') as f:
        json.dump(signals, f, indent=2)

    # Generate and save private signals
    pub_mom = signals['signals']['momentum']
    private_vp = generate_private_vp(regime, turn, pub_mom)
    private_eb2 = generate_private_eb2(regime, turn)

    with open(PRIVATE_VP_PATH, 'w') as f:
        json.dump(private_vp, f, indent=2)
    with open(PRIVATE_EB2_PATH, 'w') as f:
        json.dump(private_eb2, f, indent=2)

    return signals


if __name__ == '__main__':
    s = update()
    print(f"Signals for turn {s['turn']}: {s['signals']}")
