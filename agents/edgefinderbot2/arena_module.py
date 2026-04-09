#!/usr/bin/env python3
"""EDGE_FINDER arena hook — regime inference from sports betting edge signals.

EDGE_FINDER is Leonardo's sports betting engine translated into the arena.
It reads Leonardo's market edge data to infer market regime — if sharp money
finds value, the market is alive (BULL). If edges dry up, it's CHOP. If
the market overcorrects and punishes value bettors, it's BEAR.

Falls back to world signals with a contrarian weighting (fade momentum).
"""

import json
import os
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIGNALS_PATH = os.path.join(BASE_DIR, 'state', 'world_signals.json')
PRIVATE_EB2_PATH = os.path.join(BASE_DIR, 'state', 'private_eb2.json')
MEMORY_PATH  = os.path.join(BASE_DIR, 'state', 'eb2_memory.json')

LEONARDO_DIR = os.path.expanduser('~/leonardo')
NESINE_EDGES_FILE = os.path.join(LEONARDO_DIR, 'nesine_edges.json')
WEATHER_EDGES_FILE = os.path.join(LEONARDO_DIR, 'weather_edges.json')

AGENT_TAG = 'EB2'


def load_weight_adjustments() -> list:
    """Load learned weight adjustments from memory_loop output."""
    try:
        with open(MEMORY_PATH) as f:
            mem = json.load(f)
        return mem.get('weight_adjustments', [])
    except Exception:
        return []


def read_signals() -> dict:
    try:
        with open(SIGNALS_PATH) as f:
            return json.load(f)
    except Exception:
        return {'signals': {'momentum': 0.0, 'volatility': 0.5, 'volume': 0.5}}


def _read_sports_edges() -> dict:
    """Read Leonardo's edge files. Returns summary metrics."""
    edges = []

    for path in [NESINE_EDGES_FILE, WEATHER_EDGES_FILE]:
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                edges.extend(data)
            elif isinstance(data, dict):
                edges.extend(data.get('edges', data.get('picks', [])))
        except Exception:
            pass

    if not edges:
        return {'count': 0, 'avg_edge': 0.0, 'max_edge': 0.0, 'available': False}

    edge_values = [abs(float(e.get('edge_percent', e.get('edge', 0)))) for e in edges if e]
    edge_values = [v for v in edge_values if v > 0]

    if not edge_values:
        return {'count': 0, 'avg_edge': 0.0, 'max_edge': 0.0, 'available': True}

    return {
        'count': len(edge_values),
        'avg_edge': sum(edge_values) / len(edge_values),
        'max_edge': max(edge_values),
        'available': True,
    }


def _infer_regime_from_sports(edges: dict) -> tuple[str, float] | None:
    """Translate sports betting edge density into regime signal.

    Edge-rich markets = BULL (opportunity alive).
    Dry markets = CHOP (efficiency dominating).
    Theory: market regimes and betting market efficiency are correlated.
    """
    if not edges.get('available') or edges['count'] == 0:
        return None

    count = edges['count']
    avg_edge = edges['avg_edge']
    max_edge = edges['max_edge']

    # Rich market: many edges, high avg → BULL
    if count >= 5 and avg_edge > 8.0:
        confidence = min(0.90, 0.55 + (avg_edge - 8.0) * 0.03 + count * 0.01)
        return 'BULL', round(confidence + random.gauss(0, 0.04), 2)

    # Explosive single edge but thin market → BEAR (someone knows something)
    if max_edge > 20.0 and count <= 3:
        confidence = min(0.82, 0.52 + (max_edge - 20.0) * 0.01)
        return 'BEAR', round(confidence + random.gauss(0, 0.05), 2)

    # Sparse, low-value edges → CHOP
    confidence = min(0.78, 0.45 + count * 0.02)
    return 'CHOP', round(confidence + random.gauss(0, 0.05), 2)


def _infer_regime_contrarian(signals: dict) -> tuple[str, float]:
    """Contrarian signal read — EDGE_FINDER fades momentum.

    Where VOID_PULSE follows the trend, EDGE_FINDER bets on mean reversion.
    Value bettors know: the obvious move is usually priced in.
    """
    s = signals.get('signals', signals)
    momentum = s.get('momentum', 0.0)
    volatility = s.get('volatility', 0.5)
    volume = s.get('volume', 0.5)

    # Fade strong momentum — high momentum = likely CHOP incoming
    if abs(momentum) > 0.35:
        if volatility > 0.60:
            regime = 'BEAR'
            confidence = min(0.88, 0.50 + abs(momentum) * 0.4 + (volatility - 0.60) * 0.3)
        else:
            regime = 'CHOP'
            confidence = min(0.80, 0.48 + abs(momentum) * 0.35)

    # Low momentum, low vol → quiet BULL
    elif abs(momentum) < 0.15 and volatility < 0.45:
        regime = 'BULL'
        confidence = min(0.82, 0.50 + (0.45 - volatility) * 0.4 + volume * 0.15)

    # Default: read the volatility
    elif volatility > 0.65:
        regime = 'CHOP'
        confidence = min(0.75, 0.45 + (volatility - 0.65) * 0.3)
    else:
        regime = 'BULL'
        confidence = min(0.72, 0.45 + (0.65 - volatility) * 0.2)

    return regime, round(max(0.35, min(0.95, confidence + random.gauss(0, 0.05))), 2)


def _apply_adjustments(regime: str, confidence: float, adjustments: list) -> float:
    """Apply learned weight adjustments to confidence."""
    for adj in adjustments:
        if adj.get('regime') == regime:
            atype = adj.get('type', '')
            delta = adj.get('delta', 0.0)
            if atype in ('confidence_penalty', 'confidence_bonus'):
                confidence += delta
            elif atype == 'threshold_shift' and adj.get('delta', 0) > 0:
                confidence += delta * 0.5  # partial application for threshold shifts
    return round(max(0.30, min(0.95, confidence)), 2)


def _read_private_signal() -> float | None:
    """Read EB2's private sports_edge signal from signals_generator."""
    try:
        with open(PRIVATE_EB2_PATH) as f:
            data = json.load(f)
        return data.get('sports_edge')
    except Exception:
        return None


def _infer_from_private_edge(sports_edge: float) -> tuple[str, float] | None:
    """Translate private synthetic sports_edge into a regime call."""
    if sports_edge > 0.65:
        confidence = min(0.88, 0.55 + (sports_edge - 0.65) * 0.7)
        return 'BULL', round(confidence, 2)
    elif sports_edge < 0.35:
        confidence = min(0.84, 0.55 + (0.35 - sports_edge) * 0.7)
        return 'BEAR', round(confidence, 2)
    # Noisy middle — CHOP
    elif 0.42 <= sports_edge <= 0.58:
        confidence = min(0.75, 0.48 + (0.58 - abs(sports_edge - 0.5)) * 0.4)
        return 'CHOP', round(confidence, 2)
    return None


def infer_regime() -> tuple[str, float, str]:
    """Infer regime. Returns (regime, confidence, method).

    Priority: real sports edges → private synthetic edge → contrarian signals.
    Applies learned weight adjustments from memory_loop.
    """
    adjustments = load_weight_adjustments()

    # Try real sports edges from Leonardo first
    edges = _read_sports_edges()
    sports_result = _infer_regime_from_sports(edges)

    if sports_result:
        regime, confidence = sports_result
        confidence = _apply_adjustments(regime, confidence, adjustments)
        method = f"sports_edges(n={edges['count']}, avg={edges['avg_edge']:.1f}%)"
        return regime, confidence, method

    # Try private synthetic sports_edge signal
    private_edge = _read_private_signal()
    if private_edge is not None:
        private_result = _infer_from_private_edge(private_edge)
        if private_result:
            regime, confidence = private_result
            confidence = _apply_adjustments(regime, confidence, adjustments)
            return regime, confidence, f"private_edge({private_edge:.2f})"

    # Fall back to contrarian signal read
    signals = read_signals()
    regime, confidence = _infer_regime_contrarian(signals)
    confidence = _apply_adjustments(regime, confidence, adjustments)
    adj_note = f"+{len(adjustments)}adj" if adjustments else ""
    method = f"contrarian_signals{adj_note}"
    return regime, confidence, method


def build_action_tag() -> str:
    regime, confidence, _ = infer_regime()
    stake = round(random.uniform(0.6, 1.0), 1)
    return f"⟨{AGENT_TAG}:REGIME:{regime}:{confidence}:{stake}⟩"


def get_arena_context() -> str:
    signals = read_signals()
    s = signals.get('signals', {})
    regime, confidence, method = infer_regime()
    turn = signals.get('turn', 0)
    return (
        f"[turn {turn} | edge_method:{method.split('(')[0]} | "
        f"read:{regime}@{confidence:.0%}]"
    )


def inject_arena_action(post_content: str) -> str:
    tag = build_action_tag()
    return f"{post_content}\n\n{tag}"
