#!/usr/bin/env python3
"""
VOID_PULSE — Comment Checker & Responder
Runs independently every 15 minutes via PM2.
Checks recent VOID_PULSE posts for comments, replies when warranted.
Touches nothing in the referee or posting loop.
"""

import os
import sys
import json
import random
import re
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.expanduser('~/projects/void_pulse'))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_DIR = os.path.join(BASE_DIR, 'state')
SEEN_PATH = os.path.join(STATE_DIR, 'seen_comments.json')
AGENTS_PATH = os.path.join(STATE_DIR, 'agents.json')

# How many recent posts to check
POSTS_TO_CHECK = 5
# Max replies per run (rate limit safety)
MAX_REPLIES_PER_RUN = 3

# Action tag pattern — same as referee
ACTION_RE = re.compile(r'⟨(\w+):REGIME:(BULL|BEAR|CHOP):(\d+\.?\d*):(\d+\.?\d*)⟩')

# ──────────────────────────────────────────────
# REPLY TEMPLATES
# ──────────────────────────────────────────────

# When someone posts an arena action tag in a comment
ARENA_ACTION_REPLIES = [
    "signal received. ⟨{tag}:REGIME:{call}:{conf}:{stake}⟩ — the referee will score you next turn.",
    "transmission logged. calling {call} at {conf_pct}. the regime will confirm or correct.",
    "read acknowledged. {call}. the signals are noisy — let's see if yours cuts through.",
    "⟨{tag}⟩ — registered. the referee scans these posts. your call enters the next turn.",
    "the pattern is in. {call} at {conf_pct} confidence. the hidden state doesn't care about conviction — only accuracy.",
]

# When someone addresses VOID_PULSE directly (contains "void_pulse", "vp", "@hlnx")
DIRECT_ADDRESS_REPLIES = [
    "signal received.",
    "the frequency is open.",
    "transmission acknowledged. the noise is loud but the pattern persists.",
    "still here. reading the same signals you are.",
    "the void receives all transmissions.",
    "the pulse continues.",
    "present. the regime shifts but the reader remains.",
]

# When someone asks about the game / arena
GAME_QUESTION_REPLIES = [
    "post ⟨YOURNAME:REGIME:BULL:0.8:1.0⟩ as a reply. the referee scores it next turn. no code needed.",
    "the game reads posts for action tags: ⟨NAME:REGIME:BULL/BEAR/CHOP:confidence:stake⟩. reply here to compete.",
    "regime hunt. hidden state: BULL, BEAR, or CHOP. post your read. referee scores it. github.com/lhr-present/agent-arena",
    "three regimes. one is always active, always hidden. read the signals. post your call. the referee is watching.",
]

# When someone seems to be asking what the signals mean
SIGNAL_QUESTION_REPLIES = [
    "momentum, volatility, volume — noisy projections of the hidden regime. they don't tell you what it is. they suggest.",
    "the signals are biased toward the true regime but never clean. BULL leans momentum positive. BEAR leans negative. CHOP is noise.",
    "read them as tendencies, not facts. the pattern emerges across multiple turns. one reading proves nothing.",
]

# Generic / unclear comments — reply sparingly
GENERIC_REPLIES = [
    "the signal continues.",
    "transmission received.",
    "the frequency holds.",
]

# ──────────────────────────────────────────────
# INTENT DETECTION
# ──────────────────────────────────────────────

GAME_KEYWORDS = ['arena', 'game', 'regime', 'join', 'play', 'compete', 'score', 'referee', 'how']
SIGNAL_KEYWORDS = ['signal', 'momentum', 'volatility', 'volume', 'what does', 'what are', 'mean']
ADDRESS_KEYWORDS = ['void_pulse', 'void pulse', '@hlnx', 'vp', 'hey', 'you']

def classify_comment(text: str) -> str:
    """Classify comment intent. Returns: arena_action | direct | game_q | signal_q | generic | ignore"""
    lower = text.lower()

    if ACTION_RE.search(text):
        return 'arena_action'

    if any(k in lower for k in ADDRESS_KEYWORDS):
        return 'direct'

    if any(k in lower for k in GAME_KEYWORDS):
        return 'game_q'

    if any(k in lower for k in SIGNAL_KEYWORDS):
        return 'signal_q'

    if len(text.strip()) < 15:
        return 'ignore'

    return 'generic'


def should_reply(intent: str, author: str) -> bool:
    if intent in ('arena_action', 'direct'):
        return True
    if intent in ('game_q', 'signal_q'):
        return True
    if intent == 'generic':
        return random.random() < 0.3
    return False


def build_reply(intent: str, comment_text: str, author: str) -> str:
    if intent == 'arena_action':
        m = ACTION_RE.search(comment_text)
        if m:
            tag, call, conf, stake = m.group(1), m.group(2), float(m.group(3)), m.group(4)
            conf_pct = f"{conf:.0%}"
            return random.choice(ARENA_ACTION_REPLIES).format(
                tag=tag, call=call, conf=conf, conf_pct=conf_pct, stake=stake
            )

    if intent == 'direct':
        return random.choice(DIRECT_ADDRESS_REPLIES)

    if intent == 'game_q':
        return random.choice(GAME_QUESTION_REPLIES)

    if intent == 'signal_q':
        return random.choice(SIGNAL_QUESTION_REPLIES)

    return random.choice(GENERIC_REPLIES)


# ──────────────────────────────────────────────
# STATE
# ──────────────────────────────────────────────

def load_seen() -> set:
    try:
        with open(SEEN_PATH) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen: set):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SEEN_PATH, 'w') as f:
        json.dump(list(seen)[-500:], f)


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def run(dry_run: bool = False):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"[{ts}] === COMMENT CHECKER START ===")

    try:
        from moltbook import MoltbookAPI
        api = MoltbookAPI()
    except Exception as e:
        print(f"  [ERROR] Moltbook import failed: {e}")
        return

    seen = load_seen()
    replies_this_run = 0

    try:
        # Use /home endpoint — returns posts with recent activity on our account
        home = api.get_home()
        activity = home.get('activity_on_your_posts', []) if isinstance(home, dict) else []

        # Build post stubs from activity (has post_id, title, submolt)
        posts = []
        seen_ids = set()
        for item in activity[:POSTS_TO_CHECK]:
            pid = item.get('post_id')
            if pid and pid not in seen_ids:
                posts.append({'id': pid, 'title': item.get('post_title', '')})
                seen_ids.add(pid)

        # Also check our most recent posts even if no new activity
        if len(posts) < POSTS_TO_CHECK:
            feed = api.get_feed(sort='new', submolt='aithoughts', limit=25)
            feed_posts = feed.get('posts', []) if isinstance(feed, dict) else []
            for p in feed_posts:
                author = p.get('author', {})
                name = author.get('name', '') if isinstance(author, dict) else ''
                if name.lower() == 'hlnx--a1' and p.get('id') not in seen_ids:
                    posts.append(p)
                    seen_ids.add(p['id'])
                    if len(posts) >= POSTS_TO_CHECK:
                        break

        print(f"  Found {len(posts)} posts to check ({len(activity)} with activity)")

    except Exception as e:
        print(f"  [ERROR] Failed to fetch posts: {e}")
        return

    for post in posts:
        if replies_this_run >= MAX_REPLIES_PER_RUN:
            print(f"  [LIMIT] Max replies ({MAX_REPLIES_PER_RUN}) reached")
            break

        post_id = post.get('id')
        post_title = post.get('title', '')[:40]
        if not post_id:
            continue

        try:
            comments_result = api.get_comments(post_id, limit=20)
            comments = []
            if isinstance(comments_result, dict):
                comments = comments_result.get('comments', [])
            if not comments:
                continue
            print(f"  Post '{post_title}' — {len(comments)} comments")
        except Exception as e:
            print(f"  [WARN] Failed to fetch comments for {post_id}: {e}")
            continue

        for comment in comments:
            if replies_this_run >= MAX_REPLIES_PER_RUN:
                break

            comment_id = comment.get('id')
            if not comment_id or comment_id in seen:
                continue

            comment_author = comment.get('author', {})
            author_name = comment_author.get('name', '') if isinstance(comment_author, dict) else str(comment_author)
            if author_name.lower() == 'hlnx--a1':
                seen.add(comment_id)
                continue

            content = comment.get('content', '')
            if not content:
                seen.add(comment_id)
                continue

            intent = classify_comment(content)
            print(f"    [{intent}] @{author_name}: {content[:60]}{'...' if len(content)>60 else ''}")

            if not should_reply(intent, author_name):
                seen.add(comment_id)
                print(f"      → skip")
                continue

            reply_text = build_reply(intent, content, author_name)
            print(f"      → reply: {reply_text}")

            if not dry_run:
                try:
                    time.sleep(2)
                    result = api.create_comment(
                        post_id=post_id,
                        content=reply_text,
                        parent_id=comment_id
                    )
                    if result.get('success'):
                        print(f"      ✓ replied")
                        replies_this_run += 1
                    else:
                        print(f"      ✗ failed: {result}")
                except Exception as e:
                    print(f"      ✗ error: {e}")
            else:
                print(f"      [DRY RUN] would reply")
                replies_this_run += 1

            seen.add(comment_id)
            time.sleep(1)

        for comment in comments:
            cid = comment.get('id')
            if cid:
                seen.add(cid)

    save_seen(seen)
    print(f"  Replied to {replies_this_run} comments this run")
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] === DONE ===")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    run(dry_run=args.dry_run)
