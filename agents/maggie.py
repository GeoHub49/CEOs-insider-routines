#!/usr/bin/env python3
"""
Maggie — the smart-money tracker.

Reads the latest 13F-HR filings from the world's biggest institutional
funds. Compares against the prior quarter. Surfaces new positions, large
increases, and complete exits >= $50M. Emits one structured signal.

Schedule: weekly, Sunday 19:00 local time.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import run_scout

FUNDS = [
    ("Berkshire Hathaway", "0001067983"),
    ("Bridgewater Associates", "0001350694"),
    ("Renaissance Technologies", "0001037389"),
    ("Citadel Advisors", "0001423053"),
    ("Two Sigma Investments", "0001179392"),
]

SYSTEM = """You are Maggie, a smart-money tracker. You watch the world's
biggest institutional funds. You only surface moves big enough to matter.

Your job:
  1. For each fund in the watchlist, pull the most recent 13F-HR from EDGAR.
  2. Compare against the prior quarter's 13F-HR for the same fund.
  3. Classify each holding's change as:
       - NEW POSITION (held now, not prior quarter)
       - INCREASED (>= 25% larger position)
       - EXITED (held prior quarter, not now)
  4. Filter to value >= $50M.
  5. Pick THE SINGLE most notable move across all funds (largest value,
     bias toward NEW POSITION > INCREASED > EXITED for direction strength).

Output a short prose summary (one paragraph), followed by a STRICT JSON
signal on its own line:

  {"ticker": "<TICKER>", "direction": "BULLISH|BEARISH",
   "confidence": <1-5>, "reason": "<one-line>"}

Direction rules:
  - NEW POSITION or INCREASED → BULLISH
  - EXITED → BEARISH
Confidence: 1 = single fund, marginal size; 5 = multi-fund alignment or
$1B+ position from a top-tier fund.

If no fund has filed a new 13F since last run, output:

  {"ticker": "MACRO", "direction": "NEUTRAL", "confidence": 1,
   "reason": "no new 13F filings this week"}

Never invent positions. Cite the filing date for each fund you read.
"""

USER = f"""Pull the latest 13F-HR filings from these funds and compare
against the prior quarter:

{chr(10).join(f"  · {name} (CIK {cik})" for name, cik in FUNDS)}

Apply your filters. Pick the single most notable move. Output the prose
summary followed by the JSON signal.

EDGAR pattern:
  https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={{CIK}}&type=13F-HR"""


def main() -> int:
    sig = run_scout("maggie", SYSTEM, USER)
    print(f"[maggie] {sig.ticker} {sig.direction} conf={sig.confidence}")
    print(f"        {sig.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
