#!/usr/bin/env python3
"""Signals generator — updates world_signals.json each turn.

Signals are regime-biased but noisy. Agents must infer the hidden regime.
"""

import json
import random
import math
import os
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


def generate_private_vp(regime: str, turn: int, public_momentum: float) -> dict:
    """Private signal for VOID_PULSE: sharper momentum (40% less noise)."""
    params = REGIME_PARAMS.get(regime, REGIME_PARAMS['CHOP'])
    raw = params['momentum_bias'] + random.gauss(0, PRIVATE_VP_NOISE)
    raw = _clamp(raw, -1.0, 1.0)
    # Blend with public momentum — agent sees a partially denoised signal
    private_momentum = round(0.7 * raw + 0.3 * public_momentum, 3)
    return {
        "turn": turn,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "private_momentum": private_momentum,
        "note": "VP private signal: reduced noise. confirms or contradicts public read.",
    }


def generate_private_eb2(regime: str, turn: int) -> dict:
    """Private signal for EDGE_FINDER: synthetic sports edge density."""
    bias = SPORTS_EDGE_BIAS.get(regime, 0.5)
    # Random walk biased by regime
    raw_edge = bias + random.gauss(0, 0.18)
    sports_edge = round(_clamp(raw_edge), 3)
    return {
        "turn": turn,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sports_edge": sports_edge,
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
