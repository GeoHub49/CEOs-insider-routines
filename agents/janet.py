#!/usr/bin/env python3
"""
Janet — the portfolio-drift accountant.

Compares the user's current portfolio against their target allocation.
Flags positions that have drifted > 5 percentage points. Emits one signal.

Schedule: daily, 17:00 local time.

Reads two files (user-supplied during onboarding):
  ~/insider-routines/config/portfolio_target.json   {ticker: target_pct}
  ~/insider-routines/config/portfolio_current.json  {ticker: current_value_usd}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    BEARISH,
    BULLISH,
    NEUTRAL,
    Signal,
    log,
    record_signal,
)

CONFIG = Path.home() / "insider-routines" / "config"
TARGET = CONFIG / "portfolio_target.json"
CURRENT = CONFIG / "portfolio_current.json"

DRIFT_THRESHOLD_PP = 5.0  # percentage-point drift before Janet flags


def main() -> int:
    if not TARGET.exists() or not CURRENT.exists():
        sig = Signal(
            scout="janet",
            ticker="MACRO",
            direction=NEUTRAL,
            confidence=1,
            reason=(
                "portfolio_target.json / portfolio_current.json missing — "
                "skip Janet for now"
            ),
            raw="config files missing",
        )
        record_signal(sig)
        log("janet", sig.reason)
        print(f"[janet] {sig.reason}")
        return 0

    target: dict[str, float] = json.loads(TARGET.read_text())
    current_value: dict[str, float] = json.loads(CURRENT.read_text())
    total = sum(current_value.values()) or 1.0
    current_pct = {k: 100.0 * v / total for k, v in current_value.items()}

    drifts = []
    for ticker, target_pct in target.items():
        cur = current_pct.get(ticker, 0.0)
        drift = cur - target_pct  # +drift = overweight, -drift = underweight
        if abs(drift) >= DRIFT_THRESHOLD_PP:
            drifts.append((ticker, target_pct, cur, drift))

    if not drifts:
        sig = Signal(
            scout="janet",
            ticker="MACRO",
            direction=NEUTRAL,
            confidence=1,
            reason="portfolio within tolerance",
            raw=json.dumps({"current_pct": current_pct}),
        )
    else:
        # The biggest drift wins. Overweight = BEARISH on that ticker
        # (you should trim), underweight = BULLISH (you should add).
        drifts.sort(key=lambda d: abs(d[3]), reverse=True)
        ticker, tgt, cur, drift = drifts[0]
        direction = BEARISH if drift > 0 else BULLISH
        sig = Signal(
            scout="janet",
            ticker=ticker.upper(),
            direction=direction,
            confidence=min(5, 1 + int(abs(drift) // 5)),
            reason=(
                f"{ticker} drifted {drift:+.1f}pp (target {tgt:.1f}% → "
                f"current {cur:.1f}%) — {'trim' if drift > 0 else 'add'}"
            ),
            raw=json.dumps(
                {"drifts": [list(d) for d in drifts], "current_pct": current_pct}
            ),
        )

    record_signal(sig)
    log("janet", f"signal: {sig.ticker} {sig.direction} :: {sig.reason}")
    print(f"[janet] {sig.ticker} {sig.direction} conf={sig.confidence}")
    print(f"        {sig.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
