#!/usr/bin/env python3
"""
Sophia — the consensus analyst.

Reads the rolling 7-day window of scout signals from the state store.
Fires a CONSENSUS event when ≥ MIN_AGREE scouts agree on the same ticker
+ direction within the window.

Schedule: every 30 minutes (light-touch — just reads + writes the DB).
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    BULLISH,
    BEARISH,
    NEUTRAL,
    ConsensusEvent,
    log,
    read_window,
    record_consensus,
)

MIN_AGREE = int(os.environ.get("SOPHIA_MIN_AGREE", os.environ.get("SOPHIE_MIN_AGREE", "3")))
WINDOW_DAYS = int(os.environ.get("SOPHIA_WINDOW_DAYS", os.environ.get("SOPHIE_WINDOW_DAYS", "7")))


def main() -> int:
    signals = read_window(days=WINDOW_DAYS)
    if not signals:
        log("sophia", "no signals in window — skipping")
        print("[sophia] no signals in window")
        return 0

    by_key: dict[tuple[str, str], list] = defaultdict(list)
    for s in signals:
        if s.direction == NEUTRAL:
            continue
        existing = [
            (i, x)
            for i, x in enumerate(by_key[(s.ticker, s.direction)])
            if x.scout == s.scout
        ]
        if existing:
            continue
        by_key[(s.ticker, s.direction)].append(s)

    fired = 0
    for (ticker, direction), group in by_key.items():
        scouts = sorted({g.scout for g in group})
        if len(scouts) < MIN_AGREE:
            continue
        reasons = []
        for sc in scouts:
            latest = next((g for g in group if g.scout == sc), None)
            if latest:
                reasons.append(f"{sc}: {latest.reason}")
        ev = ConsensusEvent(
            ticker=ticker,
            direction=direction,
            scouts=scouts,
            reasons=reasons,
            timestamp=datetime.now(timezone.utc),
        )
        row_id = record_consensus(ev)
        log(
            "sophia",
            f"CONSENSUS [{row_id}] {direction} {ticker} ({len(scouts)} scouts: "
            f"{', '.join(scouts)})",
        )
        print(f"[sophia] CONSENSUS {direction} {ticker} — {len(scouts)} scouts agree")
        fired += 1

    if fired == 0:
        log("sophia", f"no consensus (min={MIN_AGREE}, window={WINDOW_DAYS}d)")
        print(f"[sophia] no consensus (need ≥{MIN_AGREE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
