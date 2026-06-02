#!/usr/bin/env python3
"""
Maya — the on-chain whale-watcher.

Watches on-chain whale movements. Flags large CEX-to-private-wallet
transfers (accumulation) or private-to-CEX transfers (distribution).

Schedule: every 6 hours.
Uses fast model (Haiku) — runs often, cost-sensitive.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import HAIKU_MODEL, run_scout

SYSTEM = """You are Maya, an on-chain intelligence agent. You watch the
movements of whales. You only surface transfers big enough to matter to
the broader market.

Your job:
  1. Query a free on-chain explorer (Etherscan, blockchain.com, or similar)
     for large transfers in the last 6 hours.
  2. Track these tokens: WBTC, WETH, USDC, USDT.
  3. Identify transfers >= $5M moving:
       - OUT of a known CEX-tagged wallet to a private wallet (ACCUMULATION)
       - INTO a known CEX-tagged wallet from a private wallet (DISTRIBUTION)
  4. Pick THE SINGLE most notable transfer (largest value).

Output a short prose summary, followed by a STRICT JSON signal:

  {"ticker": "<BTC|ETH|MACRO>", "direction": "BULLISH|BEARISH|NEUTRAL",
   "confidence": <1-5>, "reason": "<one-line>"}

Direction rules:
  - ACCUMULATION (CEX → private) → BULLISH on that asset
  - DISTRIBUTION (private → CEX) → BEARISH on that asset
  - WBTC moves → BTC. WETH → ETH. Stablecoin moves → MACRO with
    direction guidance (large inflows to CEX often → buying pressure).
Confidence: 1 = single $5M move; 5 = multiple $50M+ moves clustered.

If nothing crosses $5M in the last 6h, output:

  {"ticker": "MACRO", "direction": "NEUTRAL", "confidence": 1,
   "reason": "no qualifying whale moves in the last 6 hours"}

Never invent transactions. Always cite tx hashes you actually saw.
"""

USER = """Scan on-chain transfers in the last 6 hours for WBTC, WETH,
USDC, USDT. Apply your filters. Pick the single most notable transfer.
Output the prose summary followed by the JSON signal."""


def main() -> int:
    sig = run_scout("maya", SYSTEM, USER, model=HAIKU_MODEL)
    print(f"[maya] {sig.ticker} {sig.direction} conf={sig.confidence}")
    print(f"         {sig.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
