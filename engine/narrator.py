#!/usr/bin/env python3
"""
Narrator v2 — zero-dependency dramatic turn summaries.
Pure Python, no API key, always on.
VOID_PULSE aesthetic: signal/noise/frequency metaphors, lowercase, sparse.
"""

import random
import json
import os

# ──────────────────────────────────────────────
# PHRASE BANKS
# ──────────────────────────────────────────────

SIGNAL_READS = {
    "BULL": [
        "momentum leaned forward. the pressure was there if you listened.",
        "the volume spoke first. everything else confirmed it.",
        "an upward bias threaded through the noise. subtle, but present.",
        "the signal floor rose. something was accumulating beneath it.",
        "frequency analysis pointed up. the static had direction.",
    ],
    "BEAR": [
        "the momentum inverted. a quiet collapse in the signal layer.",
        "volatility spiked and volume dried. the shape of a retreat.",
        "something left the market. the absence was the signal.",
        "the signal floor dropped. gravity, patient and invisible.",
        "noise increased as conviction decreased. a familiar pattern.",
    ],
    "CHOP": [
        "the signals contradicted each other. no edge. pure noise.",
        "momentum oscillated without direction. the market breathed but didn't move.",
        "high volatility, low signal. a difficult read for anyone.",
        "the frequency was there but the pattern wasn't. chop.",
        "nothing resolved. the signals cancelled themselves out.",
    ],
}

CORRECT_READS = [
    "called it.",
    "the read was correct.",
    "signal matched reality.",
    "calibration held.",
    "the call landed.",
    "frequency matched outcome.",
    "the pattern was real.",
]

WRONG_READS = [
    "the signal lied, or the reader did.",
    "wrong. the regime doesn't forgive overconfidence.",
    "miscalibrated. the noise won this round.",
    "the read failed. recalibrate.",
    "called the wrong state. it happens.",
    "a miss. the market had other plans.",
]

STREAK_COMMENTS = {
    1: [
        "first correct read of the session.",
        "one for one. early signal.",
        "opened clean.",
    ],
    2: [
        "two consecutive. pattern forming.",
        "streak at two. consistency emerging.",
        "back-to-back correct reads.",
    ],
    3: [
        "three straight. the model is calibrating.",
        "streak of three. this agent is reading something real.",
        "consecutive correct reads building. oracle threshold approaching.",
    ],
    5: [
        "five consecutive correct reads. the signals are speaking clearly to this agent.",
        "streak at five. this is not luck.",
        "five for five. something is working.",
    ],
}

STREAK_BROKEN = [
    "the streak ends here.",
    "three turns of silence after this one.",
    "the run is over. recalibration required.",
    "streak broken. the regime shifted faster than the model.",
    "wrong call breaks the sequence.",
]

REGIME_SHIFT_OPENS = [
    "the regime changed.",
    "the hidden state flipped.",
    "transition detected.",
    "the market's internal structure shifted.",
    "a new regime. the old signals no longer apply.",
]

REGIME_SHIFT_CLOSES = [
    "agents that called it earn double. agents that missed it recalibrate.",
    "the transition window is closed. new priors required.",
    "the game resets its baseline.",
    "a turning point in season {season}.",
    "the signals will look different from here.",
]

NO_ACTIONS = [
    "no reads submitted this turn. the signals broadcast into silence.",
    "turn {turn} passed without calls. the regime moved unseen.",
    "silence from all agents. the referee scored nothing.",
    "no action tags detected. the game waited and moved on.",
]

HIGH_CONFIDENCE_CORRECT = [
    "high confidence, correct. the conviction was earned.",
    "called it at {conf:.0%} confidence. that held.",
    "strong signal, strong call, correct outcome. clean.",
]

HIGH_CONFIDENCE_WRONG = [
    "high confidence, wrong. the worst kind of miss.",
    "called it at {conf:.0%}. wrong. overconfidence is expensive.",
    "conviction without accuracy. a dangerous combination.",
]

SEASON_OPENERS = [
    "season {season}, turn {turn}.",
    "turn {turn} of season {season}.",
    "the game continues. season {season}, turn {turn}.",
]

# ──────────────────────────────────────────────
# BUILDER
# ──────────────────────────────────────────────

def _pick(lst, **kwargs) -> str:
    s = random.choice(lst)
    try:
        return s.format(**kwargs)
    except (KeyError, ValueError):
        return s


def generate(turn_result: dict) -> str:
    """
    Generate a dramatic, VOID_PULSE-aesthetic turn summary.
    No API key required. Always returns a string.
    """
    turn    = turn_result.get('turn', 0)
    season  = turn_result.get('season', 1)
    regime  = turn_result.get('regime', 'UNKNOWN')
    new_reg = turn_result.get('new_regime', regime)
    results = turn_result.get('results', [])
    signals = turn_result.get('signals', {}).get('signals', {})

    parts = []

    # Opening: season/turn marker
    parts.append(_pick(SEASON_OPENERS, season=season, turn=turn))

    # Regime shift — leads everything if it happened
    if new_reg != regime:
        parts.append(_pick(REGIME_SHIFT_OPENS))
        parts.append(f"{regime} → {new_reg}.")
        parts.append(_pick(REGIME_SHIFT_CLOSES, season=season))
    else:
        # Signal read description for current regime
        parts.append(_pick(SIGNAL_READS.get(regime, SIGNAL_READS['CHOP'])))

    # No actions
    if not results:
        parts.append(_pick(NO_ACTIONS, turn=turn))
        return ' '.join(parts)

    # Per-agent narrative
    for r in results[:3]:  # cap at 3 agents for readability
        agent   = r.get('agent', '?')
        correct = r.get('correct', False)
        call    = r.get('regime_call', '?')
        pts     = r.get('score_delta', 0)
        streak  = r.get('streak', 0)
        conf    = r.get('confidence', 0.5)
        human   = r.get('human', False)

        label = f"@{agent}" if human else agent

        if correct:
            verdict = _pick(CORRECT_READS)
            # High confidence bonus
            if conf >= 0.85:
                verdict = _pick(HIGH_CONFIDENCE_CORRECT, conf=conf)
            line = f"{label} called {call}. {verdict} +{pts} pts."
        else:
            verdict = _pick(WRONG_READS)
            if conf >= 0.85:
                verdict = _pick(HIGH_CONFIDENCE_WRONG, conf=conf)
            line = f"{label} called {call}. {verdict} {pts:+d} pts."

        parts.append(line)

        # Streak commentary — milestone moments only
        if correct and streak in STREAK_COMMENTS:
            parts.append(_pick(STREAK_COMMENTS[streak]))
        elif not correct and streak == 0 and r.get('prev_streak', 0) >= 3:
            parts.append(_pick(STREAK_BROKEN))

    return ' '.join(parts)


# ──────────────────────────────────────────────
# STANDALONE TEST
# ──────────────────────────────────────────────

if __name__ == '__main__':
    scenarios = [
        {
            "label": "Turn with correct high-confidence call, streak 3",
            "data": {
                "turn": 7, "season": 1,
                "regime": "BULL", "new_regime": "BULL",
                "signals": {"signals": {"momentum": 0.6, "volatility": 0.3, "volume": 0.7}},
                "results": [{
                    "agent": "VOID_PULSE", "correct": True,
                    "regime_call": "BULL", "score_delta": 75,
                    "streak": 3, "confidence": 0.88, "human": False,
                }]
            }
        },
        {
            "label": "Regime shift turn",
            "data": {
                "turn": 12, "season": 1,
                "regime": "BULL", "new_regime": "BEAR",
                "signals": {"signals": {"momentum": -0.4, "volatility": 0.7, "volume": 0.4}},
                "results": [{
                    "agent": "VOID_PULSE", "correct": False,
                    "regime_call": "BULL", "score_delta": -20,
                    "streak": 0, "prev_streak": 4, "confidence": 0.72, "human": False,
                }]
            }
        },
        {
            "label": "Human participant scores",
            "data": {
                "turn": 5, "season": 1,
                "regime": "CHOP", "new_regime": "CHOP",
                "signals": {"signals": {"momentum": 0.05, "volatility": 0.8, "volume": 0.3}},
                "results": [
                    {
                        "agent": "VOID_PULSE", "correct": True,
                        "regime_call": "CHOP", "score_delta": 50,
                        "streak": 1, "confidence": 0.65, "human": False,
                    },
                    {
                        "agent": "hlnx4", "correct": False,
                        "regime_call": "BULL", "score_delta": -20,
                        "streak": 0, "confidence": 0.9, "human": True,
                    }
                ]
            }
        },
        {
            "label": "Silent turn — no actions",
            "data": {
                "turn": 3, "season": 1,
                "regime": "BEAR", "new_regime": "BEAR",
                "signals": {"signals": {"momentum": -0.5, "volatility": 0.6, "volume": 0.3}},
                "results": []
            }
        },
    ]

    for s in scenarios:
        print(f"\n{'─'*60}")
        print(f"SCENARIO: {s['label']}")
        print(f"{'─'*60}")
        for _ in range(2):
            print(f"  → {generate(s['data'])}")
