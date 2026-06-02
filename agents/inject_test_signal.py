#!/usr/bin/env python3
"""One-shot test helper — injects a fake BULLISH signal so Sophie fires."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Signal, record_signal, BULLISH

sig = Signal(
    scout="eddie",
    ticker="AAPL",
    direction=BULLISH,
    confidence=4,
    reason="TEST: CEO bought $500k AAPL open-market (inject_test_signal.py)",
    raw="test injection",
)
record_signal(sig)
print(f"[test] injected {sig.direction} {sig.ticker} for {sig.scout}")
