#!/usr/bin/env python3
"""
VOID_PULSE — Memory & Reinforcement Loop
Runs after each referee turn (called from run_turn.py or standalone).

Learns from:
- Own regime read accuracy over time
- Other agents' / humans' calls and outcomes
- Comment content (what questions people ask, what signals they notice)
- Regime transition patterns

Saves to: state/memory.json  (structured, shareable)
          state/memory_log.md (human-readable, publishable)
"""

import os
import sys
import json
import random
from datetime import datetime, timezone
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_DIR = os.path.join(BASE_DIR, 'state')

MEMORY_PATH     = os.path.join(STATE_DIR, 'memory.json')
MEMORY_LOG_PATH = os.path.join(BASE_DIR,  'MEMORY.md')
HISTORY_PATH    = os.path.join(STATE_DIR, 'regime_history.json')
AGENTS_PATH     = os.path.join(STATE_DIR, 'agents.json')

EMPTY_MEMORY = {
    "version": 2,
    "last_updated": None,
    "last_turn_processed": -1,

    "self": {
        "total_reads": 0,
        "correct_reads": 0,
        "accuracy": 0.0,
        "best_streak": 0,
        "current_streak": 0,
        "tokens": 1000,
        "score": 0,
        "regime_accuracy": {
            "BULL": {"correct": 0, "total": 0},
            "BEAR": {"correct": 0, "total": 0},
            "CHOP": {"correct": 0, "total": 0},
        },
        "confidence_calibration": [],
        "worst_regime": None,
        "best_regime": None,
    },

    "regime_patterns": {
        "transition_counts": {
            "BULL→BEAR": 0, "BULL→CHOP": 0, "BULL→BULL": 0,
            "BEAR→BULL": 0, "BEAR→CHOP": 0, "BEAR→BEAR": 0,
            "CHOP→BULL": 0, "CHOP→BEAR": 0, "CHOP→CHOP": 0,
        },
        "avg_regime_duration": {"BULL": [], "BEAR": [], "CHOP": []},
        "last_shift_turn": 0,
        "total_shifts": 0,
        "current_run_length": 0,
    },

    "signal_memory": {
        "BULL": {"momentum_sum": 0, "vol_sum": 0, "volume_sum": 0, "count": 0},
        "BEAR": {"momentum_sum": 0, "vol_sum": 0, "volume_sum": 0, "count": 0},
        "CHOP": {"momentum_sum": 0, "vol_sum": 0, "volume_sum": 0, "count": 0},
    },

    "others": {},

    "comment_insights": [],

    "lessons": [],

    "narrative_summary": "",
}

# ──────────────────────────────────────────────
# LOADERS
# ──────────────────────────────────────────────

def load_memory() -> dict:
    try:
        with open(MEMORY_PATH) as f:
            m = json.load(f)
        if m.get('version', 1) < 2:
            m.update({k: v for k, v in EMPTY_MEMORY.items() if k not in m})
            m['version'] = 2
        return m
    except Exception:
        return dict(EMPTY_MEMORY)


def save_memory(mem: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
    mem['last_updated'] = datetime.now(timezone.utc).isoformat()
    with open(MEMORY_PATH, 'w') as f:
        json.dump(mem, f, indent=2)


def load_history() -> list:
    try:
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def load_agents() -> dict:
    try:
        with open(AGENTS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

# ──────────────────────────────────────────────
# LESSON GENERATOR
# ──────────────────────────────────────────────

LESSON_TEMPLATES = {
    "regime_weakness": [
        "struggled most in {regime} regime — {pct:.0%} accuracy. signals for {regime}: {hint}.",
        "{regime} reads are consistently wrong. recalibrate prior for {regime} detection.",
        "accuracy in {regime} is only {pct:.0%} over {n} reads. the pattern is not yet clear.",
    ],
    "regime_strength": [
        "{regime} reads are solid at {pct:.0%} over {n} turns. the signal is readable.",
        "calibrated for {regime}. {pct:.0%} accuracy holds over time.",
        "strongest in {regime} — {pct:.0%} correct. this regime is legible.",
    ],
    "overconfidence": [
        "high confidence ({avg_conf:.0%}) on wrong calls — overconfidence is the failure mode.",
        "conviction exceeds accuracy when wrong. reduce stake on uncertain reads.",
        "the gap between confidence and accuracy is widest on wrong calls. calibrate down.",
    ],
    "transition_signal": [
        "regime runs an average of {avg_len:.1f} turns before shifting. duration is a signal.",
        "after {n} turns in same regime, shift probability increases. watch turn count.",
        "longest run observed: {max_len} turns. current run: {current}. baseline pressure building.",
    ],
    "other_agent": [
        "{agent} reads {regime} at {pct:.0%} accuracy over {n} calls. they may have an edge there.",
        "{agent} is consistently calling {regime} — correlation with actual regime: {pct:.0%}.",
        "human participant @{agent} accuracy: {pct:.0%}. worth tracking.",
    ],
    "community_signal": [
        "repeated questions about {topic} — the community is noticing something.",
        "{n} comments referencing {topic} this session. external signal worth logging.",
    ],
}


def generate_lesson(lesson_type: str, **kwargs) -> str:
    templates = LESSON_TEMPLATES.get(lesson_type, ["{type} lesson"])
    t = random.choice(templates)
    try:
        return t.format(**kwargs)
    except (KeyError, ValueError):
        return t


def regime_signal_hint(regime: str, sig_mem: dict) -> str:
    data = sig_mem.get(regime, {})
    n = data.get('count', 0)
    if n == 0:
        return "insufficient data"
    mom = data['momentum_sum'] / n
    vol = data['vol_sum'] / n
    return f"momentum avg {mom:+.2f}, volatility avg {vol:.2f}"

# ──────────────────────────────────────────────
# CORE UPDATE
# ──────────────────────────────────────────────

def update_from_history(mem: dict, history: list) -> int:
    last = mem['last_turn_processed']
    new_turns = [h for h in history if h.get('turn', -1) > last]
    if not new_turns:
        return 0

    patterns = mem['regime_patterns']
    sig_mem  = mem['signal_memory']
    self_    = mem['self']
    others   = mem['others']
    lessons  = mem['lessons']

    prev_regime = None
    current_run = patterns['current_run_length']

    for entry in sorted(new_turns, key=lambda x: x.get('turn', 0)):
        turn    = entry.get('turn', 0)
        regime  = entry.get('regime', 'CHOP')
        signals = entry.get('signals', {})
        results = entry.get('results', [])

        # Transition tracking
        if prev_regime and prev_regime != regime:
            key = f"{prev_regime}→{regime}"
            patterns['transition_counts'][key] = patterns['transition_counts'].get(key, 0) + 1
            patterns['total_shifts'] += 1
            patterns['last_shift_turn'] = turn
            if prev_regime in patterns['avg_regime_duration']:
                patterns['avg_regime_duration'][prev_regime].append(current_run)
                patterns['avg_regime_duration'][prev_regime] = \
                    patterns['avg_regime_duration'][prev_regime][-20:]
            current_run = 1
        elif prev_regime == regime:
            current_run += 1
        else:
            current_run = 1

        patterns['current_run_length'] = current_run

        # Signal memory
        mom    = signals.get('momentum', 0)
        vol    = signals.get('volatility', 0.5)
        volume = signals.get('volume', 0.5)
        if regime in sig_mem:
            sig_mem[regime]['momentum_sum'] += mom
            sig_mem[regime]['vol_sum']      += vol
            sig_mem[regime]['volume_sum']   += volume
            sig_mem[regime]['count']        += 1

        # Score results
        for r in results:
            agent    = r.get('agent', '?')
            correct  = r.get('correct', False)
            call     = r.get('regime_call', '?')
            conf     = r.get('confidence', 0.5)
            is_human = r.get('human', False)

            if agent == 'VOID_PULSE':
                self_['total_reads'] += 1
                if correct:
                    self_['correct_reads'] += 1
                    self_['current_streak'] += 1
                    self_['best_streak'] = max(self_['best_streak'], self_['current_streak'])
                else:
                    self_['current_streak'] = 0

                reg_acc = self_['regime_accuracy'].get(regime, {'correct': 0, 'total': 0})
                reg_acc['total'] += 1
                if correct:
                    reg_acc['correct'] += 1
                self_['regime_accuracy'][regime] = reg_acc

                self_['confidence_calibration'].append({'conf': conf, 'correct': correct})
                self_['confidence_calibration'] = self_['confidence_calibration'][-50:]
            else:
                if agent not in others:
                    others[agent] = {
                        'reads': 0, 'correct': 0, 'accuracy': 0.0,
                        'calls': {'BULL': 0, 'BEAR': 0, 'CHOP': 0},
                        'human': is_human, 'first_seen_turn': turn
                    }
                o = others[agent]
                o['reads'] += 1
                o['calls'][call] = o['calls'].get(call, 0) + 1
                if correct:
                    o['correct'] += 1
                o['accuracy'] = round(o['correct'] / o['reads'], 3)
                o['last_seen_turn'] = turn

        prev_regime = regime
        mem['last_turn_processed'] = turn

    # Recompute self accuracy
    if self_['total_reads'] > 0:
        self_['accuracy'] = round(self_['correct_reads'] / self_['total_reads'], 3)

    # Find best/worst regime
    accs = {
        r: (v['correct'] / v['total'] if v['total'] >= 3 else None)
        for r, v in self_['regime_accuracy'].items()
    }
    valid = {r: a for r, a in accs.items() if a is not None}
    if valid:
        self_['worst_regime'] = min(valid, key=valid.get)
        self_['best_regime']  = max(valid, key=valid.get)

    existing_texts = {l['text'] for l in lessons}

    if self_['worst_regime']:
        r = self_['worst_regime']
        v = self_['regime_accuracy'][r]
        if v['total'] >= 5:
            pct = v['correct'] / v['total']
            hint = regime_signal_hint(r, sig_mem)
            text = generate_lesson('regime_weakness', regime=r, pct=pct, n=v['total'], hint=hint)
            if text not in existing_texts:
                lessons.append({'turn': mem['last_turn_processed'], 'type': 'regime_weakness',
                                 'text': text, 'confidence': 0.8})

    if self_['best_regime'] and self_['best_regime'] != self_['worst_regime']:
        r = self_['best_regime']
        v = self_['regime_accuracy'][r]
        if v['total'] >= 5 and v['correct'] / v['total'] >= 0.7:
            pct = v['correct'] / v['total']
            text = generate_lesson('regime_strength', regime=r, pct=pct, n=v['total'])
            if text not in existing_texts:
                lessons.append({'turn': mem['last_turn_processed'], 'type': 'regime_strength',
                                 'text': text, 'confidence': 0.75})

    for r, durations in patterns['avg_regime_duration'].items():
        if len(durations) >= 3:
            avg     = sum(durations) / len(durations)
            max_len = max(durations)
            current = patterns['current_run_length']
            text = generate_lesson('transition_signal', avg_len=avg, n=len(durations),
                                   max_len=max_len, current=current)
            if text not in existing_texts:
                lessons.append({'turn': mem['last_turn_processed'], 'type': 'transition_signal',
                                 'text': text, 'confidence': 0.6})
                existing_texts.add(text)

    for agent, data in others.items():
        if data['reads'] >= 5 and data['accuracy'] >= 0.75:
            dominant = max(data['calls'], key=data['calls'].get)
            text = generate_lesson('other_agent', agent=agent, regime=dominant,
                                   pct=data['accuracy'], n=data['reads'])
            if text not in existing_texts:
                lessons.append({'turn': mem['last_turn_processed'], 'type': 'other_agent',
                                 'text': text, 'confidence': 0.65})

    mem['lessons'] = lessons[-50:]
    return len(new_turns)


def update_from_comments(mem: dict):
    comment_log_path = os.path.join(STATE_DIR, 'comment_log.json')
    try:
        with open(comment_log_path) as f:
            recent = json.load(f)
    except Exception:
        return

    insights = mem['comment_insights']
    existing_ids = {i.get('id') for i in insights}
    new_insights = []
    topic_counts = defaultdict(int)

    for c in recent:
        cid = c.get('id')
        if cid in existing_ids:
            continue
        content = c.get('content', '').lower()
        if 'signal' in content or 'momentum' in content:
            topic_counts['signals'] += 1
        if 'regime' in content or 'bull' in content or 'bear' in content:
            topic_counts['regime_interest'] += 1
        if 'join' in content or 'how' in content or 'play' in content:
            topic_counts['onboarding'] += 1
        new_insights.append({
            'id': cid, 'turn': c.get('turn', 0),
            'author': c.get('author', '?'), 'intent': c.get('intent', 'generic'),
            'summary': content[:80], 'timestamp': c.get('timestamp', '')
        })

    insights.extend(new_insights)
    mem['comment_insights'] = insights[-100:]

    existing_texts = {l['text'] for l in mem['lessons']}
    for topic, count in topic_counts.items():
        if count >= 3:
            text = generate_lesson('community_signal', topic=topic, n=count)
            if text not in existing_texts:
                mem['lessons'].append({
                    'turn': mem['last_turn_processed'], 'type': 'community_signal',
                    'text': text, 'confidence': 0.5
                })


def build_narrative(mem: dict) -> str:
    s      = mem['self']
    pat    = mem['regime_patterns']
    turns  = mem['last_turn_processed']
    others = mem['others']

    lines = [
        f"season 1 · {turns + 1} turns observed · {s['total_reads']} reads logged",
        f"accuracy: {s['accuracy']:.0%} · best streak: {s['best_streak']}",
    ]
    if s['best_regime']:
        v = s['regime_accuracy'][s['best_regime']]
        pct = v['correct'] / v['total'] if v['total'] else 0
        lines.append(f"strongest regime read: {s['best_regime']} at {pct:.0%}")
    if s['worst_regime']:
        v = s['regime_accuracy'][s['worst_regime']]
        pct = v['correct'] / v['total'] if v['total'] else 0
        lines.append(f"weakest regime read: {s['worst_regime']} at {pct:.0%}")
    lines.append(f"total regime shifts observed: {pat['total_shifts']}")
    if others:
        lines.append(f"other agents tracked: {len(others)}")
    if mem['lessons']:
        lines.append(f"latest lesson: {mem['lessons'][-1]['text']}")
    return '\n'.join(lines)


# ──────────────────────────────────────────────
# MARKDOWN EXPORT
# ──────────────────────────────────────────────

def export_markdown(mem: dict):
    s      = mem['self']
    pat    = mem['regime_patterns']
    others = mem['others']
    turns  = mem['last_turn_processed']
    reg_acc = s['regime_accuracy']

    def pct(r):
        v = reg_acc.get(r, {})
        return f"{v['correct']/v['total']:.0%} ({v['correct']}/{v['total']})" if v.get('total') else "—"

    def tr(a, b):
        return str(pat['transition_counts'].get(f"{a}→{b}", 0))

    def avg_dur(r):
        d = pat['avg_regime_duration'].get(r, [])
        return f"{sum(d)/len(d):.1f} turns" if d else "—"

    lesson_lines = []
    for l in reversed(mem['lessons'][-15:]):
        emoji = {'regime_weakness':'⚠️','regime_strength':'✅','transition_signal':'🔄',
                 'other_agent':'👁','community_signal':'💬','overconfidence':'🎯'}.get(l['type'],'•')
        lesson_lines.append(f"| {l['turn']} | {emoji} | {l['text']} |")
    lessons_block = '\n'.join(lesson_lines) if lesson_lines else "| — | — | no lessons yet |"

    other_lines = []
    for name, data in sorted(others.items(), key=lambda x: x[1]['reads'], reverse=True)[:10]:
        label    = "👤" if data['human'] else "🤖"
        dominant = max(data['calls'], key=data['calls'].get) if data['calls'] else "?"
        other_lines.append(f"| {label} {name} | {data['reads']} | {data['accuracy']:.0%} | {dominant} |")
    others_block = '\n'.join(other_lines) if other_lines else "| — | — | — | — |"

    cal = s['confidence_calibration']
    if cal:
        hc = [c for c in cal if c['conf'] >= 0.8]
        lc = [c for c in cal if c['conf'] < 0.6]
        hc_acc = sum(1 for c in hc if c['correct']) / len(hc) if hc else 0
        lc_acc = sum(1 for c in lc if c['correct']) / len(lc) if lc else 0
        cal_note = f"high confidence (≥80%): {hc_acc:.0%} · low confidence (<60%): {lc_acc:.0%}"
    else:
        cal_note = "insufficient data"

    sig_lines = ""
    for regime in ['BULL', 'BEAR', 'CHOP']:
        d = mem['signal_memory'].get(regime, {})
        n = d.get('count', 0)
        if n > 0:
            mom   = d['momentum_sum'] / n
            vol   = d['vol_sum'] / n
            vol_n = d['volume_sum'] / n
            sig_lines += f"**{regime}** — momentum avg `{mom:+.3f}` · volatility avg `{vol:.3f}` · volume avg `{vol_n:.3f}` · n={n}\n\n"
        else:
            sig_lines += f"**{regime}** — insufficient data\n\n"

    md = f"""# 🧠 VOID_PULSE — MEMORY LOG

*Season 1 · Auto-updated each turn · [Agent Arena](https://github.com/lhr-present/agent-arena)*

---

## Self Performance

| Metric | Value |
|--------|-------|
| Turns observed | {turns + 1} |
| Total reads | {s['total_reads']} |
| Accuracy | {s['accuracy']:.0%} |
| Best streak | {s['best_streak']} |
| Current streak | {s['current_streak']} |
| Score | {s['score']} pts |

### Regime Accuracy
| Regime | Accuracy |
|--------|----------|
| BULL | {pct('BULL')} |
| BEAR | {pct('BEAR')} |
| CHOP | {pct('CHOP')} |

**Calibration:** {cal_note}

---

## Regime Patterns

### Transition Matrix (observed)
| From↓ To→ | BULL | BEAR | CHOP |
|-----------|------|------|------|
| BULL | {tr('BULL','BULL')} | {tr('BULL','BEAR')} | {tr('BULL','CHOP')} |
| BEAR | {tr('BEAR','BULL')} | {tr('BEAR','BEAR')} | {tr('BEAR','CHOP')} |
| CHOP | {tr('CHOP','BULL')} | {tr('CHOP','BEAR')} | {tr('CHOP','CHOP')} |

### Average Regime Duration
| Regime | Avg Duration |
|--------|-------------|
| BULL | {avg_dur('BULL')} |
| BEAR | {avg_dur('BEAR')} |
| CHOP | {avg_dur('CHOP')} |

Total shifts: **{pat['total_shifts']}** · Current run: **{pat['current_run_length']} turns**

---

## Others Observed

| Agent | Reads | Accuracy | Dominant Call |
|-------|-------|----------|---------------|
{others_block}

---

## Lessons

| Turn | Type | Lesson |
|------|------|--------|
{lessons_block}

---

## Signal Correlations (learned)

{sig_lines}---

*Last updated: {mem['last_updated']}*
*Raw data: [state/memory.json](state/memory.json)*
"""
    with open(MEMORY_LOG_PATH, 'w') as f:
        f.write(md)


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def run():
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"[{ts}] === MEMORY UPDATE ===")

    mem     = load_memory()
    history = load_history()
    agents  = load_agents()

    vp = agents.get('VOID_PULSE', {})
    mem['self']['score']  = vp.get('score', mem['self']['score'])
    mem['self']['tokens'] = vp.get('tokens', mem['self']['tokens'])

    new = update_from_history(mem, history)
    print(f"  Processed {new} new turns")

    update_from_comments(mem)

    mem['narrative_summary'] = build_narrative(mem)
    print(f"  Narrative: {mem['narrative_summary'].split(chr(10))[0]}")

    save_memory(mem)
    print(f"  Saved → state/memory.json")

    export_markdown(mem)
    print(f"  Exported → MEMORY.md")

    if mem['lessons']:
        print(f"  Latest lesson: {mem['lessons'][-1]['text']}")

    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] === DONE ===")


if __name__ == '__main__':
    run()
