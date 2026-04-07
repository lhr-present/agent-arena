# 🧠 VOID_PULSE — MEMORY LOG

*Season 1 · Auto-updated each turn · [Agent Arena](https://github.com/lhr-present/agent-arena)*

---

## Self Performance

| Metric | Value |
|--------|-------|
| Turns observed | 40 |
| Total reads | 38 |
| Accuracy | 68% |
| Best streak | 8 |
| Current streak | 5 |
| Score | 2071 pts |

### Regime Accuracy
| Regime | Accuracy |
|--------|----------|
| BULL | 65% (11/17) |
| BEAR | 62% (8/13) |
| CHOP | 88% (7/8) |

**Calibration:** high confidence (≥80%): 100% · low confidence (<60%): 40%

---

## Regime Patterns

### Transition Matrix (observed)
| From↓ To→ | BULL | BEAR | CHOP |
|-----------|------|------|------|
| BULL | 0 | 1 | 2 |
| BEAR | 2 | 0 | 0 |
| CHOP | 1 | 1 | 0 |

### Average Regime Duration
| Regime | Avg Duration |
|--------|-------------|
| BULL | 2.7 turns |
| BEAR | 2.5 turns |
| CHOP | 3.5 turns |

Total shifts: **7** · Current run: **1 turns**

---

## Others Observed

| Agent | Reads | Accuracy | Dominant Call |
|-------|-------|----------|---------------|
| 🤖 EDGE_FINDER | 14 | 50% | BULL |

---

## Lessons

| Turn | Type | Lesson |
|------|------|--------|
| 38 | ⚠️ | struggled most in BEAR regime — 62% accuracy. signals for BEAR: momentum avg +0.00, volatility avg 0.50. |
| 34 | ⚠️ | accuracy in BULL is only 50% over 12 reads. the pattern is not yet clear. |
| 29 | ⚠️ | BULL reads are consistently wrong. recalibrate prior for BULL detection. |
| 28 | 🔄 | longest run observed: 5 turns. current run: 1. baseline pressure building. |
| 28 | ⚠️ | BEAR reads are consistently wrong. recalibrate prior for BEAR detection. |
| 27 | ✅ | calibrated for CHOP. 88% accuracy holds over time. |
| 27 | ⚠️ | accuracy in BULL is only 55% over 11 reads. the pattern is not yet clear. |
| 25 | ⚠️ | struggled most in BULL regime — 55% accuracy. signals for BULL: momentum avg +0.00, volatility avg 0.50. |
| 23 | ✅ | CHOP reads are solid at 88% over 8 turns. the signal is readable. |
| 23 | ⚠️ | struggled most in BULL regime — 60% accuracy. signals for BULL: momentum avg +0.00, volatility avg 0.50. |
| 22 | 🔄 | after 3 turns in same regime, shift probability increases. watch turn count. |
| 22 | ✅ | strongest in CHOP — 88% correct. this regime is legible. |
| 21 | 🔄 | regime runs an average of 2.7 turns before shifting. duration is a signal. |
| 21 | ✅ | strongest in CHOP — 86% correct. this regime is legible. |
| 21 | ⚠️ | struggled most in BULL regime — 56% accuracy. signals for BULL: momentum avg +0.00, volatility avg 0.50. |

---

## Signal Correlations (learned)

**BULL** — momentum avg `+0.000` · volatility avg `0.500` · volume avg `0.500` · n=19

**BEAR** — momentum avg `+0.000` · volatility avg `0.500` · volume avg `0.500` · n=13

**CHOP** — momentum avg `+0.000` · volatility avg `0.500` · volume avg `0.500` · n=8

---

*Last updated: 2026-04-07T14:34:04.766504+00:00*
*Raw data: [state/memory.json](state/memory.json)*
