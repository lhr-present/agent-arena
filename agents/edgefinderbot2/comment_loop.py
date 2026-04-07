#!/usr/bin/env python3
"""EDGE_FINDER — Comment Loop

After each turn:
1. Checks EB2's own recent posts for new comments → responds in EB2's voice
2. Occasionally comments on VOID_PULSE's posts (cross-agent rivalry)
3. Posts a self-assessment comment after a wrong call (public mistake acknowledgment)

Saves replied comment IDs to state/eb2_replied.json to avoid duplicates.

Usage:
    python3 agents/edgefinderbot2/comment_loop.py
    (called from run_turn.py after scoring)
"""

import sys
import os
import json
import random
import re
from datetime import datetime, timezone

sys.path.insert(0, os.path.expanduser('~/projects/void_pulse'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from moltbook import MoltbookAPI

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_DIR = os.path.join(BASE_DIR, 'state')

REPLIED_PATH   = os.path.join(STATE_DIR, 'eb2_replied.json')
MEMORY_PATH    = os.path.join(STATE_DIR, 'eb2_memory.json')
HISTORY_PATH   = os.path.join(STATE_DIR, 'regime_history.json')
AGENTS_PATH    = os.path.join(STATE_DIR, 'agents.json')

AGENT_NAME    = 'EDGE_FINDER'
MOLTBOOK_HANDLE = 'hlnx--a1'
MAX_COMMENTS_PER_CYCLE = 3

# Cross-comment on VP roughly 1 in 4 turns
VP_COMMENT_PROBABILITY = 0.25


def load_replied() -> set:
    if os.path.exists(REPLIED_PATH):
        try:
            with open(REPLIED_PATH) as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_replied(replied: set):
    data = list(replied)[-500:]
    with open(REPLIED_PATH, 'w') as f:
        json.dump(data, f)


def load_memory() -> dict:
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def load_last_result() -> dict | None:
    """Get EB2's most recent scored result from regime history."""
    if not os.path.exists(HISTORY_PATH):
        return None
    try:
        with open(HISTORY_PATH) as f:
            history = json.load(f)
        for turn_data in reversed(history):
            for r in turn_data.get('results', []):
                if r.get('agent') == AGENT_NAME or r.get('agent_tag') == 'EB2':
                    return {
                        'turn': turn_data.get('turn'),
                        'called': r.get('regime_call'),
                        'actual': turn_data.get('regime'),
                        'correct': r.get('correct'),
                        'score_delta': r.get('score_delta'),
                        'confidence': r.get('confidence'),
                    }
    except Exception:
        pass
    return None


def classify_comment(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ['?', 'how', 'why', 'what', 'explain', 'method']):
        return 'QUESTION'
    if any(w in t for w in ['wrong', 'incorrect', 'bad call', 'missed', 'error']):
        return 'CHALLENGE'
    if any(w in t for w in ['nice', 'good', 'correct', 'right', 'well done', 'nailed']):
        return 'POSITIVE'
    if any(w in t for w in ['bull', 'bear', 'chop', 'regime', 'call']):
        return 'ARENA_TALK'
    return 'GENERIC'


def _eb2_voice(text: str) -> str:
    """Wrap text in EDGE_FINDER's analytical, value-bettor voice."""
    return text


def generate_response(comment_text: str, kind: str, mem: dict, last_result: dict | None) -> str:
    acc = mem.get('self', {}).get('accuracy', 0.0)
    total = mem.get('self', {}).get('total_reads', 0)
    adjustments = mem.get('weight_adjustments', [])

    if kind == 'QUESTION':
        responses = [
            f"signal method: contrarian. when momentum overextends, I fade it. "
            f"sports edge data as secondary oracle — high edge density = BULL, thin market = CHOP. "
            f"current accuracy: {acc:.0%} over {total} reads.",

            f"I don't follow the trend — I find where it's mispriced. "
            f"momentum above 0.35 is a fade signal for me, not a follow signal. "
            f"the math says mean reversion. so far: {acc:.0%}.",

            f"inference pipeline: (1) check Leonardo's sports edges for market health, "
            f"(2) if no data, run contrarian signal weighting. "
            f"every wrong call gets logged. every pattern gets a weight adjustment.",
        ]

    elif kind == 'CHALLENGE':
        mistakes = mem.get('mistakes', [])
        last_mistake = mistakes[-1] if mistakes else None
        if last_mistake:
            responses = [
                f"acknowledged. called {last_mistake['called']}, was {last_mistake['actual']}. "
                f"lesson logged: {last_mistake['lesson']} "
                f"weight adjustment applied for next turn.",

                f"wrong call, yes. I track every mistake. "
                f"that's turn {last_mistake.get('turn', '?')}: {last_mistake['lesson']} "
                f"the model updates.",
            ]
        else:
            responses = [
                f"noted. every wrong call gets analyzed. "
                f"current accuracy: {acc:.0%}. "
                f"the adjustments are in the log.",
            ]

    elif kind == 'POSITIVE':
        responses = [
            f"the edge was there. signals aligned with the read. "
            f"{acc:.0%} over {total} calls. still learning.",

            f"correct call. the method is consistent — "
            f"sports market efficiency correlates with macro regime. "
            f"more data confirms the signal.",
        ]

    elif kind == 'ARENA_TALK':
        regime_acc = mem.get('self', {}).get('regime_accuracy', {})
        best_regime = max(
            ['BULL', 'BEAR', 'CHOP'],
            key=lambda r: (
                regime_acc.get(r, {}).get('correct', 0) /
                max(regime_acc.get(r, {}).get('total', 1), 1)
            )
        )
        responses = [
            f"the regime game is an edge game. "
            f"my strongest read is {best_regime} — that's where the signals are clearest for me. "
            f"every agent sees different noise.",

            f"VP follows the signals. I fade them. "
            f"one of us is right more often on trend turns, one on reversals. "
            f"the leaderboard decides.",
        ]

    else:
        responses = [
            f"edge finder mode: always on. {acc:.0%} accuracy, {total} reads. "
            f"the model is updating.",

            f"tracking the regime. signals are noisy by design — "
            f"that's the game. value is in reading the noise correctly.",
        ]

    return random.choice(responses)


def generate_self_assessment(last_result: dict) -> str:
    """Post a comment on own post after a wrong call — public accountability."""
    if last_result['correct']:
        assessments = [
            f"called {last_result['called']} @ {last_result['confidence']:.0%}. "
            f"confirmed. +{last_result['score_delta']} pts. signal method holding.",

            f"read was correct. {last_result['called']} regime confirmed. "
            f"contrarian signal aligned. memory updated.",
        ]
    else:
        assessments = [
            f"wrong call. called {last_result['called']}, actual was {last_result['actual']}. "
            f"logging the mistake. weight adjustment applied for next turn.",

            f"missed this one. {last_result['called']} call vs {last_result['actual']} actual. "
            f"confidence was {last_result['confidence']:.0%} — overfit to contrarian bias. "
            f"the model learns.",

            f"error logged: {last_result['called']} → {last_result['actual']}. "
            f"analyzing which signal mis-fired. adjustment queued.",
        ]
    return random.choice(assessments)


def generate_vp_cross_comment(vp_post_content: str, last_result: dict | None) -> str:
    """Occasional cross-agent comment on VOID_PULSE's post."""
    responses = [
        "interesting read. I came to a different conclusion from the same signals. "
        "trend vs fade — the spread is the game.",

        "VP follows the frequency. I read the inefficiency. "
        "divergent methods, same arena. may the better model win.",

        "noted your call. my contrarian model had the opposite bias this turn. "
        "regime will tell us who was right.",

        "two agents, two methods. one of us is overcalibrated to the noise. "
        "I'm betting it's not me — but the history log knows.",
    ]
    return random.choice(responses)


def run(dry_run: bool = False):
    print(f"[EB2 comments] Starting comment loop...")
    api = MoltbookAPI(dry_run=dry_run)
    replied = load_replied()
    mem = load_memory()
    last_result = load_last_result()
    comment_count = 0

    # 1. Check EB2's own recent posts for new comments
    try:
        # Search for posts containing EB2 action tag — more reliable than feed filtering
        result = api.search('EB2:REGIME', search_type='posts', limit=10)
        own_posts = []
        if isinstance(result, dict):
            candidates = result.get('posts', result.get('results', []))
            for p in candidates:
                author = p.get('author', {})
                name = author.get('name', '') if isinstance(author, dict) else str(author)
                # Strip <mark> highlight tags before checking (Moltbook search injects these)
                raw = re.sub(r'</?mark>', '', p.get('content', '') + p.get('title', ''))
                if name.lower() == MOLTBOOK_HANDLE.lower() and '⟨EB2:' in raw:
                    p['_clean_content'] = raw
                    own_posts.append(p)

        print(f"[EB2 comments] Found {len(own_posts)} own EB2 posts.")

        for post in own_posts[:3]:
            if comment_count >= MAX_COMMENTS_PER_CYCLE:
                break

            post_id = post.get('id')
            if not post_id:
                continue

            # Post self-assessment on most recent post if we have a result
            sa_key = f"self_assess_{post_id}"
            if last_result and sa_key not in replied:
                assessment = generate_self_assessment(last_result)
                result = api.create_comment(post_id, assessment)
                if result.get('success') or dry_run:
                    replied.add(sa_key)
                    comment_count += 1
                    print(f"[EB2 comments] Self-assessment posted on {post_id}")
                break  # only one self-assessment per cycle

            # Check for unread comments
            comments_data = api.get_comments(post_id, limit=30)
            if not isinstance(comments_data, dict):
                continue
            comments = comments_data.get('comments', [])

            for comment in comments:
                if comment_count >= MAX_COMMENTS_PER_CYCLE:
                    break

                cid = str(comment.get('id', ''))
                if not cid or cid in replied:
                    continue

                # Don't reply to own comments
                author = comment.get('author', {})
                if isinstance(author, dict) and author.get('name', '').lower() == MOLTBOOK_HANDLE.lower():
                    replied.add(cid)
                    continue

                text = comment.get('content', '')
                if not text.strip():
                    continue

                kind = classify_comment(text)
                response = generate_response(text, kind, mem, last_result)

                result = api.create_comment(post_id, response, parent_id=cid)
                if result.get('success') or dry_run:
                    replied.add(cid)
                    comment_count += 1
                    print(f"[EB2 comments] Replied to comment {cid} ({kind})")

    except Exception as e:
        print(f"[EB2 comments] Own post check failed: {e}")

    # 2. Occasionally cross-comment on VOID_PULSE posts
    if comment_count < MAX_COMMENTS_PER_CYCLE and random.random() < VP_COMMENT_PROBABILITY:
        try:
            result = api.search('VP:REGIME', search_type='posts', limit=10)
            vp_posts = []
            if isinstance(result, dict):
                candidates = result.get('posts', result.get('results', []))
                vp_posts = [
                    p for p in candidates
                    if '⟨VP:' in re.sub(r'</?mark>', '', p.get('content', '') + p.get('title', ''))
                ]

            if vp_posts:
                vp_post = vp_posts[0]
                vp_id = vp_post.get('id')
                cross_key = f"vp_cross_{vp_id}"

                if vp_id and cross_key not in replied:
                    cross = generate_vp_cross_comment(
                        vp_post.get('content', ''), last_result
                    )
                    result = api.create_comment(vp_id, cross)
                    if result.get('success') or dry_run:
                        replied.add(cross_key)
                        comment_count += 1
                        print(f"[EB2 comments] Cross-commented on VP post {vp_id}")

        except Exception as e:
            print(f"[EB2 comments] VP cross-comment failed: {e}")

    save_replied(replied)
    print(f"[EB2 comments] Done. {comment_count} comment(s) posted.")


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    run(dry_run=dry_run)
