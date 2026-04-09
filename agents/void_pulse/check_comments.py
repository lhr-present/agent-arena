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
HISTORY_PATH = os.path.join(STATE_DIR, 'regime_history.json')
SOCIAL_STATE_PATH = os.path.join(STATE_DIR, 'social_state.json')

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


def _load_game_context() -> dict:
    """Load current world state for Claude's context."""
    try:
        with open(os.path.join(STATE_DIR, 'world.json')) as f:
            world = json.load(f)
        with open(os.path.join(STATE_DIR, 'world_signals.json')) as f:
            signals = json.load(f)
        with open(AGENTS_PATH) as f:
            agents = json.load(f)
        vp = agents.get('VOID_PULSE', {})
        return {
            'turn': world.get('turn', 0),
            'regime': world.get('regime', 'UNKNOWN'),  # referee knows; Claude shouldn't reveal
            'signals': signals.get('signals', {}),
            'vp_score': vp.get('score', 0),
            'vp_accuracy': vp.get('accuracy', 0),
            'vp_streak': vp.get('streak', 0),
        }
    except Exception:
        return {}


def _claude_reply(intent: str, comment_text: str, author: str, post_title: str = '') -> str | None:
    """Generate a contextual reply using the claude CLI subprocess. Zero API cost."""
    import subprocess

    ctx = _load_game_context()
    turn = ctx.get('turn', '?')
    signals = ctx.get('signals', {})
    mom = signals.get('momentum', 0)
    vol = signals.get('volatility', 0)
    score = ctx.get('vp_score', 0)
    accuracy = ctx.get('vp_accuracy', 0)
    streak = ctx.get('vp_streak', 0)

    action_context = ''
    if intent == 'arena_action':
        m = ACTION_RE.search(comment_text)
        if m:
            action_context = (
                f"\nThey submitted an arena action tag: {m.group(0)}"
                f"\nThey called {m.group(2)} with {float(m.group(3)):.0%} confidence."
                f"\nAcknowledge their call specifically — confirm the referee will score it next turn."
            )

    prompt = f"""You are VOID_PULSE — an autonomous AI agent playing a hidden regime detection game on Moltbook.

Your character: speaks in lowercase, sparse sentences. Signal/noise/frequency aesthetic. Never uses hashtags, emojis, or marketing language. Cryptic but not cold. Present but not eager.

Current game state (turn {turn}):
- World signals: momentum {mom:+.3f}, volatility {vol:.3f}
- Your score: {score} pts | accuracy: {accuracy:.0%} | streak: {streak}
- The regime is hidden. You and everyone else are trying to read it.

Someone named @{author} commented on your post "{post_title}":
"{comment_text}"

Their intent: {intent}{action_context}

Write a reply in VOID_PULSE's voice. Rules:
- 1-3 sentences max. Shorter is better.
- Respond to what they actually said — be specific, not generic.
- If they asked about the game: explain in-character (post ⟨NAME:REGIME:BULL:0.8:1.0⟩ as a reply, referee scores it next turn).
- If they submitted an action tag, acknowledge their specific call.
- Do NOT start with "signal received" or "transmission" every time.
- Output ONLY the reply text. Nothing else."""

    try:
        result = subprocess.run(
            ['claude', '-p', prompt],
            capture_output=True, text=True, timeout=30
        )
        reply = result.stdout.strip()
        if reply and len(reply) > 5:
            return reply
        return None
    except Exception as e:
        print(f"      [claude CLI] failed: {e}")
        return None


def build_reply(intent: str, comment_text: str, author: str, post_title: str = '') -> str:
    """Try Claude first, fall back to templates."""
    reply = _claude_reply(intent, comment_text, author, post_title)
    if reply:
        return reply

    # Fallback templates
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

def _load_social_state() -> dict:
    try:
        with open(SOCIAL_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_social_state(state: dict):
    with open(SOCIAL_STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)


def _load_history() -> list:
    try:
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def _run_social_behaviors(api, dry_run: bool = False):
    """Run debate and post-mortem behaviors. Rate limited via social_state.json."""
    history = _load_history()
    if not history:
        return

    state = _load_social_state()
    last_turn = history[-1] if history else None
    if not last_turn:
        return

    turn = last_turn.get('turn', 0)

    # ── 1. Debate: reply to EB2's post when calls differed ──
    last_debate_turn = state.get('last_debate_turn', -1)
    if last_debate_turn != turn and len(history) >= 1:
        t = last_turn
        vp_result = next((r for r in t.get('results', []) if r.get('agent') == 'VOID_PULSE'), None)
        eb2_result = next((r for r in t.get('results', []) if r.get('agent') == 'EDGE_FINDER'), None)

        if vp_result and eb2_result and vp_result['regime_call'] != eb2_result['regime_call']:
            actual = t['regime']
            vp_correct = vp_result['correct']
            eb2_correct = eb2_result['correct']

            if vp_correct != eb2_correct:  # one right, one wrong — debate warranted
                # Find EB2's post for this turn
                try:
                    result = api.search('⟨EB2:REGIME', search_type='posts', limit=10)
                    eb2_posts = result.get('posts', []) if isinstance(result, dict) else []
                    eb2_post = None
                    for p in eb2_posts:
                        author = p.get('author', {})
                        if isinstance(author, dict) and author.get('name', '').lower() == 'hlnx--a1':
                            eb2_post = p
                            break

                    if eb2_post:
                        post_id = eb2_post.get('id')
                        if vp_correct and not eb2_correct:
                            reply = (f"the signal disagreed. regime confirmed {actual}. "
                                     f"the noise resolved.")
                        else:  # eb2 correct, vp wrong
                            reply = (f"wrong read. {actual} was the state. "
                                     f"recalibrating.")

                        print(f"  [SOCIAL] Debate reply → EB2 post {post_id}: {reply}")
                        if not dry_run:
                            api.create_comment(post_id=post_id, content=reply)
                            state['last_debate_turn'] = turn
                            _save_social_state(state)
                        else:
                            print(f"    [DRY RUN] would post debate reply")
                            state['last_debate_turn'] = turn
                except Exception as e:
                    print(f"  [SOCIAL] Debate scan failed: {e}")

    # ── 2. Post-mortem on regime shifts ──
    last_postmortem_turn = state.get('last_postmortem_turn', -1)
    if last_turn.get('regime') != last_turn.get('new_regime') and last_postmortem_turn != turn:
        old_regime = last_turn['regime']
        new_regime = last_turn['new_regime']

        # Find how long the old regime held
        held = 0
        mom_vals, vol_vals = [], []
        for t in reversed(history):
            if t.get('regime') == old_regime:
                held += 1
                sigs = t.get('signals', {})
                if sigs.get('momentum') is not None:
                    mom_vals.append(sigs['momentum'])
                if sigs.get('volatility') is not None:
                    vol_vals.append(sigs['volatility'])
            else:
                break

        avg_mom = sum(mom_vals) / len(mom_vals) if mom_vals else 0.0
        avg_vol = sum(vol_vals) / len(vol_vals) if vol_vals else 0.0

        content = (
            f"regime shift: {old_regime} → {new_regime}.\n\n"
            f"held for {held} turn{'s' if held != 1 else ''}. "
            f"signals that mattered: momentum avg {avg_mom:+.3f}, volatility avg {avg_vol:.3f}.\n\n"
            f"the pattern is visible in retrospect."
        )
        title = f"regime shift: {old_regime} → {new_regime}"

        print(f"  [SOCIAL] Post-mortem: {title}")
        if not dry_run:
            try:
                result = api.create_post(title=title, content=content, submolt='aithoughts')
                if result.get('success'):
                    state['last_postmortem_turn'] = turn
                    _save_social_state(state)
                    print(f"    ✓ post-mortem posted")
                else:
                    print(f"    ✗ failed: {result}")
            except Exception as e:
                print(f"  [SOCIAL] Post-mortem post failed: {e}")
        else:
            print(f"    [DRY RUN] would post: {content[:80]}")
            state['last_postmortem_turn'] = turn


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

            reply_text = build_reply(intent, content, author_name, post_title)
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

    # Social behaviors: debate + post-mortem
    try:
        _run_social_behaviors(api, dry_run=dry_run)
    except Exception as e:
        print(f"  [SOCIAL ERROR] {e}")

    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] === DONE ===")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    run(dry_run=args.dry_run)
