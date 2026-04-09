#!/usr/bin/env python3
"""Virtual bet system — spectators bet tokens on agents each turn.

Bet tag format: ⟨NAME:BET:VP:100⟩ or ⟨NAME:BET:EB2:100⟩
  fields: bettor_name : BET : target_agent_tag : token_amount

Resolution: if target agent was correct that turn → bettor doubles tokens
            if target agent was wrong → bettor loses tokens

New bettors start with 1000 tokens.
State saved in state/bets.json.
"""

import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(BASE_DIR, 'state')
BETS_PATH = os.path.join(STATE_DIR, 'bets.json')
PENDING_BETS_PATH = os.path.join(STATE_DIR, 'pending_bets.json')

BET_RE = re.compile(r'⟨(\w+):BET:(VP|EB2):(\d+)⟩', re.IGNORECASE)

# Map tag to agent name
TAG_TO_AGENT = {'VP': 'VOID_PULSE', 'EB2': 'EDGE_FINDER'}
STARTING_TOKENS = 1000


def load_bets() -> dict:
    try:
        with open(BETS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_bets(bets: dict):
    with open(BETS_PATH, 'w') as f:
        json.dump(bets, f, indent=2)


def load_pending() -> list:
    try:
        with open(PENDING_BETS_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def save_pending(pending: list):
    with open(PENDING_BETS_PATH, 'w') as f:
        json.dump(pending, f, indent=2)


def scan_for_bets(post_contents: list[str]) -> list[dict]:
    """Scan post/comment texts for bet tags. Returns list of bet dicts."""
    found = []
    for text in post_contents:
        for m in BET_RE.finditer(text):
            found.append({
                'bettor': m.group(1),
                'target_tag': m.group(2).upper(),
                'target_agent': TAG_TO_AGENT.get(m.group(2).upper(), ''),
                'amount': int(m.group(3)),
                'raw': m.group(0),
            })
    return found


def resolve_bets(turn_results: list[dict], dry_run: bool = False) -> list[dict]:
    """Resolve all pending bets against this turn's scoring results.

    Returns list of resolution records for broadcast.
    """
    pending = load_pending()
    if not pending:
        return []

    bets = load_bets()

    # Build agent correctness map from turn results
    agent_correct = {}
    for r in turn_results:
        agent_name = r.get('agent', '')
        agent_correct[agent_name] = r.get('correct', False)

    resolutions = []
    for bet in pending:
        bettor = bet['bettor']
        target = bet['target_agent']
        amount = bet['amount']

        if bettor not in bets:
            bets[bettor] = {'tokens': STARTING_TOKENS, 'total_bets': 0, 'wins': 0}

        # Cap bet at bettor's available tokens
        available = bets[bettor]['tokens']
        actual_amount = min(amount, available)
        if actual_amount <= 0:
            continue

        was_correct = agent_correct.get(target, False)
        delta = actual_amount if was_correct else -actual_amount
        new_tokens = max(0, bets[bettor]['tokens'] + delta)

        resolutions.append({
            'bettor': bettor,
            'target_agent': target,
            'target_tag': bet['target_tag'],
            'amount': actual_amount,
            'won': was_correct,
            'delta': delta,
            'new_total': new_tokens,
        })

        if not dry_run:
            bets[bettor]['tokens'] = new_tokens
            bets[bettor]['total_bets'] = bets[bettor].get('total_bets', 0) + 1
            if was_correct:
                bets[bettor]['wins'] = bets[bettor].get('wins', 0) + 1

    if not dry_run:
        save_bets(bets)
        save_pending([])  # clear after resolution

    return resolutions


def get_leaderboard(top_n: int = 5) -> list[dict]:
    """Return top N bettors sorted by tokens."""
    bets = load_bets()
    sorted_bettors = sorted(bets.items(), key=lambda x: x[1]['tokens'], reverse=True)
    return [
        {
            'name': name,
            'tokens': data['tokens'],
            'total_bets': data.get('total_bets', 0),
            'wins': data.get('wins', 0),
        }
        for name, data in sorted_bettors[:top_n]
    ]


if __name__ == '__main__':
    print("=== BET ENGINE STATUS ===")
    lb = get_leaderboard()
    if lb:
        for i, b in enumerate(lb, 1):
            win_rate = b['wins'] / b['total_bets'] if b['total_bets'] else 0
            print(f"#{i} {b['name']}: {b['tokens']} tokens | {b['total_bets']} bets | {win_rate:.0%} win rate")
    else:
        print("No bets yet.")
