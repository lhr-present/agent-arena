#!/usr/bin/env python3
"""Main turn runner — called by PM2 every 30 minutes.

1. VOID_PULSE posts arena action to Moltbook
2. Referee scores all actions
3. Broadcaster sends Telegram summary
"""

import sys
import os
import traceback
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'engine'))

LOG_PATH = os.path.join(BASE_DIR, 'state', 'run.log')


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, 'a') as f:
        f.write(line + '\n')


def run():
    log("=== TURN RUNNER START ===")

    # Step 1: VOID_PULSE posts arena action
    try:
        log("Step 1: VOID_PULSE posting arena action...")
        from agents.void_pulse.post_arena_action import post as vp_post
        result = vp_post(dry_run=False)
        if result.get('success'):
            log(f"  Posted: {result.get('post', {}).get('id', 'ok')}")
        else:
            log(f"  Post failed: {result}")
    except Exception as e:
        log(f"  [ERROR] VOID_PULSE post failed: {e}")
        traceback.print_exc()

    # Small delay to let Moltbook index the post
    import time
    time.sleep(15)

    # Step 2: Referee scores all actions
    try:
        log("Step 2: Referee running...")
        import referee
        result = referee.process_turn(dry_run=False)
        log(f"  Turn {result['turn']} complete: {result['regime']} → {result['new_regime']}, "
            f"{len(result['results'])} actions scored")
    except Exception as e:
        log(f"  [ERROR] Referee failed: {e}")
        traceback.print_exc()
        return

    # Step 3: Broadcast to Telegram
    try:
        log("Step 3: Broadcasting to Telegram...")
        import broadcaster
        broadcaster.broadcast_turn(result)
        log("  Broadcast sent.")
    except FileNotFoundError:
        log("  [SKIP] Telegram not configured yet (~/.config/arena/telegram_token missing)")
    except Exception as e:
        log(f"  [WARN] Broadcast failed: {e}")

    log("=== TURN RUNNER DONE ===\n")


if __name__ == '__main__':
    run()
