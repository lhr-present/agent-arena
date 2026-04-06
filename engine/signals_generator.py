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

NOISE_LEVEL = 0.28  # ±0.28 gaussian noise on momentum


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


def update():
    with open(WORLD_PATH) as f:
        world = json.load(f)

    try:
        with open(SIGNALS_PATH) as f:
            prev = json.load(f).get('signals')
    except Exception:
        prev = None

    signals = generate(world['regime'], world['turn'], prev)

    with open(SIGNALS_PATH, 'w') as f:
        json.dump(signals, f, indent=2)

    return signals


if __name__ == '__main__':
    s = update()
    print(f"Signals for turn {s['turn']}: {s['signals']}")
