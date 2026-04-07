# EDGE_FINDER — Memory Log

*Last updated: turn 38*

## Performance
| Metric | Value |
|--------|-------|
| Accuracy | 50% |
| Total reads | 14 |
| BULL accuracy | 3/5 (60%) |
| BEAR accuracy | 4/4 (100%) |
| CHOP accuracy | 0/5 (0%) |

## Active Adjustments (learned)

- **CHOP** -0.10 — CHOP accuracy 0% — stop defaulting to CHOP
- **BEAR** +0.06 — 2 recent BULL→BEAR mistakes — be quicker to call BEAR

## Recent Mistakes

| Turn | Called | Actual | Lesson |
|------|--------|--------|--------|
| 26 | BULL | BEAR | overshot — high momentum with rising vol was actually BEAR. fade harder. |
| 27 | CHOP | BEAR | missed BEAR. CHOP was actually deteriorating — watch vol rising from low base. |
| 28 | BULL | BEAR | overshot — high momentum with rising vol was actually BEAR. fade harder. |
| 32 | CHOP | BEAR | missed BEAR. CHOP was actually deteriorating — watch vol rising from low base. |
| 36 | CHOP | BULL | missed BULL entry. low momentum + low vol was quiet accumulation, not chop. |
| 37 | CHOP | BULL | missed BULL entry. low momentum + low vol was quiet accumulation, not chop. |
| 38 | CHOP | BULL | missed BULL entry. low momentum + low vol was quiet accumulation, not chop. |

## Learned Lessons

- accuracy: 60% over 5 reads
  BULL: 3/4 (75%)
  CHOP: 0/1 (0%)
recent mistakes:
  turn 26: called BULL, was BEAR — overshot — high momentum with rising vol was actually BEAR. fade harder.
  turn 27: called CHOP, was BEAR — missed BEAR. CHOP was actually deteriorating — watch vol rising from low base.
- accuracy: 60% over 10 reads
  BULL: 3/5 (60%)
  BEAR: 3/3 (100%)
  CHOP: 0/2 (0%)
recent mistakes:
  turn 26: called BULL, was BEAR — overshot — high momentum with rising vol was actually BEAR. fade harder.
  turn 27: called CHOP, was BEAR — missed BEAR. CHOP was actually deteriorating — watch vol rising from low base.
  turn 28: called BULL, was BEAR — overshot — high momentum with rising vol was actually BEAR. fade harder.
  turn 32: called CHOP, was BEAR — missed BEAR. CHOP was actually deteriorating — watch vol rising from low base.
active adjustments:
  [confidence_penalty] CHOP -0.10: CHOP accuracy 0% — stop defaulting to CHOP
  [threshold_shift] BEAR +0.06: 2 recent BULL→BEAR mistakes — be quicker to call BEAR
