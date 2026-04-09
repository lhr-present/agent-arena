# EDGE_FINDER — Memory Log

*Last updated: turn 107*

## Performance
| Metric | Value |
|--------|-------|
| Accuracy | 54% |
| Total reads | 76 |
| BULL accuracy | 18/34 (53%) |
| BEAR accuracy | 14/16 (88%) |
| CHOP accuracy | 9/26 (35%) |

## Active Adjustments (learned)

- **CHOP** -0.10 — CHOP accuracy 35% — stop defaulting to CHOP
- **BEAR** +0.06 — 2 recent BULL→BEAR mistakes — be quicker to call BEAR

## Recent Mistakes

| Turn | Called | Actual | Lesson |
|------|--------|--------|--------|
| 94 | CHOP | BEAR | missed BEAR. CHOP was actually deteriorating — watch vol rising from low base. |
| 95 | BULL | BEAR | overshot — high momentum with rising vol was actually BEAR. fade harder. |
| 96 | BULL | CHOP | BULL call in low-signal environment. when unsure, default CHOP. |
| 99 | BULL | CHOP | BULL call in low-signal environment. when unsure, default CHOP. |
| 101 | BULL | BEAR | overshot — high momentum with rising vol was actually BEAR. fade harder. |
| 102 | CHOP | BEAR | missed BEAR. CHOP was actually deteriorating — watch vol rising from low base. |
| 103 | CHOP | BEAR | missed BEAR. CHOP was actually deteriorating — watch vol rising from low base. |
| 107 | BEAR | CHOP | called BEAR but market just noisy. high vol != bear, check momentum direction. |

## Learned Lessons

- accuracy: 60% over 55 reads
  BULL: 12/22 (55%)
  BEAR: 13/14 (93%)
  CHOP: 8/19 (42%)
recent mistakes:
  turn 68: called CHOP, was BEAR — missed BEAR. CHOP was actually deteriorating — watch vol rising from low base.
  turn 70: called BULL, was CHOP — BULL call in low-signal environment. when unsure, default CHOP.
  turn 76: called BULL, was CHOP — BULL call in low-signal environment. when unsure, default CHOP.
  turn 79: called BEAR, was CHOP — called BEAR but market just noisy. high vol != bear, check momentum direction.
  turn 82: called BULL, was CHOP — BULL call in low-signal environment. when unsure, default CHOP.
- accuracy: 58% over 60 reads
  BULL: 13/25 (52%)
  BEAR: 13/14 (93%)
  CHOP: 9/21 (43%)
recent mistakes:
  turn 79: called BEAR, was CHOP — called BEAR but market just noisy. high vol != bear, check momentum direction.
  turn 82: called BULL, was CHOP — BULL call in low-signal environment. when unsure, default CHOP.
  turn 85: called BULL, was CHOP — BULL call in low-signal environment. when unsure, default CHOP.
  turn 87: called BULL, was CHOP — BULL call in low-signal environment. when unsure, default CHOP.
  turn 88: called CHOP, was BEAR — missed BEAR. CHOP was actually deteriorating — watch vol rising from low base.
- accuracy: 55% over 65 reads
  BULL: 14/27 (52%)
  BEAR: 13/14 (93%)
  CHOP: 9/24 (38%)
recent mistakes:
  turn 88: called CHOP, was BEAR — missed BEAR. CHOP was actually deteriorating — watch vol rising from low base.
  turn 91: called CHOP, was BULL — missed BULL entry. low momentum + low vol was quiet accumulation, not chop.
  turn 92: called CHOP, was BULL — missed BULL entry. low momentum + low vol was quiet accumulation, not chop.
  turn 94: called CHOP, was BEAR — missed BEAR. CHOP was actually deteriorating — watch vol rising from low base.
  turn 95: called BULL, was BEAR — overshot — high momentum with rising vol was actually BEAR. fade harder.
- accuracy: 54% over 70 reads
  BULL: 16/32 (50%)
  BEAR: 13/14 (93%)
  CHOP: 9/24 (38%)
recent mistakes:
  turn 94: called CHOP, was BEAR — missed BEAR. CHOP was actually deteriorating — watch vol rising from low base.
  turn 95: called BULL, was BEAR — overshot — high momentum with rising vol was actually BEAR. fade harder.
  turn 96: called BULL, was CHOP — BULL call in low-signal environment. when unsure, default CHOP.
  turn 99: called BULL, was CHOP — BULL call in low-signal environment. when unsure, default CHOP.
  turn 101: called BULL, was BEAR — overshot — high momentum with rising vol was actually BEAR. fade harder.
active adjustments:
  [threshold_shift] BEAR +0.06: 2 recent BULL→BEAR mistakes — be quicker to call BEAR
- accuracy: 55% over 75 reads
  BULL: 18/34 (53%)
  BEAR: 14/15 (93%)
  CHOP: 9/26 (35%)
recent mistakes:
  turn 96: called BULL, was CHOP — BULL call in low-signal environment. when unsure, default CHOP.
  turn 99: called BULL, was CHOP — BULL call in low-signal environment. when unsure, default CHOP.
  turn 101: called BULL, was BEAR — overshot — high momentum with rising vol was actually BEAR. fade harder.
  turn 102: called CHOP, was BEAR — missed BEAR. CHOP was actually deteriorating — watch vol rising from low base.
  turn 103: called CHOP, was BEAR — missed BEAR. CHOP was actually deteriorating — watch vol rising from low base.
active adjustments:
  [confidence_penalty] CHOP -0.10: CHOP accuracy 35% — stop defaulting to CHOP
  [threshold_shift] BEAR +0.06: 2 recent BULL→BEAR mistakes — be quicker to call BEAR
