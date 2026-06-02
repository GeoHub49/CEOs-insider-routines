#!/usr/bin/env python3
"""
Ross — the dispatcher.

Reads pending consensus events from the state store, generates a
Long/Short trade analysis via Claude, then dispatches via Gmail SMTP
(always) and Telegram (optional).

Schedule: every 30 minutes (interleaved with Sophia). Idempotent —
re-running with no pending events is a no-op.

NEVER places trades. Output is informational. The human decides.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    ConsensusEvent,
    log,
    mark_dispatched,
    pending_consensus,
    render_consensus,
    run_scout,
    send_email,
    send_telegram,
    get_claude,
    BULLISH,
)

TRADE_SYSTEM = """You are Ross, a professional trade analyst. You receive a
consensus signal from a multi-agent financial intelligence system and produce
a concise, actionable trade analysis.

Your output MUST follow this exact structure:

TRADE ANALYSIS
==============
Ticker:     <TICKER>
Direction:  LONG | SHORT
Bias:       <one-line market bias, e.g. "Momentum + insider accumulation">

Entry zone:   <price range or condition, e.g. "$145–$148 on pullback to 20-day MA">
Stop-loss:    <level or rule, e.g. "$139 (daily close below 200-day MA)">
Target 1:     <first target>
Target 2:     <second target>
Risk/Reward:  <ratio — MINIMUM 1:2.5. If you cannot find a valid setup with R:R ≥ 2.5, write "NO VALID SETUP" and explain why.>

Rationale:
<2–4 sentences explaining WHY this trade makes sense given the signals.
Reference the scouts that agreed and what they saw.>

Time horizon: <Swing (days–weeks) | Position (weeks–months)>

⚠️ This is not financial advice. Ross does not place trades.
   The decision and the risk are yours.
"""


def build_trade_prompt(ev: ConsensusEvent) -> str:
    scout_lines = "\n".join(f"  • {r}" for r in ev.reasons)
    side = "LONG" if ev.direction == BULLISH else "SHORT"
    return f"""Consensus signal received:

Ticker:    {ev.ticker}
Direction: {ev.direction} → {side}
Scouts:    {", ".join(ev.scouts)}

Scout reasoning:
{scout_lines}

Generate the trade analysis now."""


def trade_analysis(ev: ConsensusEvent) -> str:
    """Call Claude to generate a Long/Short trade analysis. Returns plain text."""
    try:
        client = get_claude()
        msg = client.messages.create(
            model=os.environ.get("INSIDER_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=1024,
            system=TRADE_SYSTEM,
            messages=[{"role": "user", "content": build_trade_prompt(ev)}],
        )
        return "\n".join(
            block.text for block in msg.content if hasattr(block, "text")
        ).strip()
    except Exception as exc:
        log("ross", f"trade analysis failed: {exc}")
        return f"[Trade analysis unavailable: {exc}]"


def main() -> int:
    pending = pending_consensus()
    if not pending:
        log("ross", "no pending consensus events")
        print("[ross] nothing to dispatch")
        return 0

    delivered = 0
    for row_id, ev in pending:
        consensus_body = render_consensus(ev)

        print(f"[ross] generating trade analysis for {ev.ticker}…")
        analysis = trade_analysis(ev)
        log("ross", f"trade analysis generated for [{row_id}] {ev.ticker}")

        full_body = f"{consensus_body}\n\n{'='*72}\n\n{analysis}"
        subject = f"[INSIDER] {ev.direction} on {ev.ticker} — Trade Analysis Inside"

        try:
            send_email(subject, full_body)
            log("ross", f"email sent for consensus [{row_id}] {ev.ticker}")
        except Exception as exc:  # noqa: BLE001
            log("ross", f"email FAILED for [{row_id}]: {exc}")
            print(f"[ross] email FAILED for {ev.ticker}: {exc}")
            continue

        if send_telegram(f"*{subject}*\n\n```\n{full_body[:3800]}\n```"):
            log("ross", f"telegram sent for [{row_id}]")

        mark_dispatched(row_id)
        delivered += 1
        print(f"[ross] dispatched {ev.direction} {ev.ticker} with trade analysis")

    log("ross", f"delivered {delivered}/{len(pending)} pending events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
