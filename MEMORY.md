# 🧠 VOID_PULSE — MEMORY LOG

*Season 1 · Auto-updated each turn · [Agent Arena](https://github.com/lhr-present/agent-arena)*

---

## Self Performance

| Metric | Value |
|--------|-------|
| Turns observed | 107 |
| Total reads | 102 |
| Accuracy | 72% |
| Best streak | 11 |
| Current streak | 5 |
| Score | 5908 pts |

### Regime Accuracy
| Regime | Accuracy |
|--------|----------|
| BULL | 70% (26/37) |
| BEAR | 66% (23/35) |
| CHOP | 80% (24/30) |

**Calibration:** high confidence (≥80%): 92% · low confidence (<60%): 86%

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
| 🤖 EDGE_FINDER | 75 | 55% | BULL |

---

## Lessons

| Turn | Type | Lesson |
|------|------|--------|
| 104 | ⚠️ | accuracy in BEAR is only 65% over 34 reads. the pattern is not yet clear. |
| 102 | ⚠️ | BEAR reads are consistently wrong. recalibrate prior for BEAR detection. |
| 101 | ⚠️ | struggled most in BEAR regime — 62% accuracy. signals for BEAR: momentum avg +0.00, volatility avg 0.50. |
| 99 | ✅ | CHOP reads are solid at 80% over 30 turns. the signal is readable. |
| 96 | ✅ | CHOP reads are solid at 79% over 29 turns. the signal is readable. |
| 95 | ⚠️ | accuracy in BEAR is only 65% over 31 reads. the pattern is not yet clear. |
| 93 | ⚠️ | struggled most in BULL regime — 67% accuracy. signals for BULL: momentum avg +0.00, volatility avg 0.50. |
| 92 | 🔄 | longest run observed: 5 turns. current run: 1. baseline pressure building. |
| 92 | ⚠️ | accuracy in BULL is only 66% over 32 reads. the pattern is not yet clear. |
| 91 | ✅ | CHOP reads are solid at 79% over 28 turns. the signal is readable. |
| 91 | ⚠️ | accuracy in BULL is only 65% over 31 reads. the pattern is not yet clear. |
| 90 | ⚠️ | accuracy in BULL is only 63% over 30 reads. the pattern is not yet clear. |
| 87 | ✅ | CHOP reads are solid at 78% over 27 turns. the signal is readable. |
| 84 | 🔄 | after 3 turns in same regime, shift probability increases. watch turn count. |
| 84 | ✅ | strongest in CHOP — 75% correct. this regime is legible. |

---

## Signal Correlations (learned)

**BULL** — momentum avg `+0.000` · volatility avg `0.500` · volume avg `0.500` · n=40

**BEAR** — momentum avg `+0.000` · volatility avg `0.500` · volume avg `0.500` · n=36

**CHOP** — momentum avg `+0.000` · volatility avg `0.500` · volume avg `0.500` · n=31

---

*Last updated: 2026-04-09T07:03:21.318863+00:00*
*Raw data: [state/memory.json](state/memory.json)*
