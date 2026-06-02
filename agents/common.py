"""
common.py — shared foundation for the 7 Insider agents.

Used by Eddie / Maggie / Frank / Maya / Janet (scouts), Sophie (consensus),
and Ross (dispatcher). Provides:

  - get_gemini()          Google Gemini client, reads GEMINI_API_KEY
  - run_scout()           Run a scout prompt → parse structured output → persist
  - read_window()         Read the rolling 7-day window of scout signals
  - record_signal()       Write a scout signal to the state store
  - record_consensus()    Write a consensus event to the state store
  - send_email()          Gmail SMTP via app password
  - send_telegram()       Optional Telegram bot delivery
  - log()                 Append-only log to ~/insider-routines/.state/logs/

State lives at ~/insider-routines/.state/state.db (SQLite).
Config lives at ~/insider-routines/.env (read at startup via python-dotenv).

The agents are intentionally small — they delegate the heavy lifting to
Gemini (web research, parsing) and just orchestrate the data flow.
"""

from __future__ import annotations

import json
import os
import smtplib
import sqlite3
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "Missing dependency: python-dotenv. Install with `pip install python-dotenv`.\n"
    )
    raise

try:
    import google.generativeai as genai  # type: ignore
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "Missing dependency: google-generativeai. Install with `pip install google-generativeai`.\n"
    )
    raise


# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path.home() / "insider-routines"
STATE = ROOT / ".state"
LOGS = STATE / "logs"
DB_PATH = STATE / "state.db"
ENV_PATH = ROOT / ".env"

# Load env on import — every agent boots through this module.
if ENV_PATH.exists():
    load_dotenv(ENV_PATH, encoding="utf-8", override=True)


# ── Models ───────────────────────────────────────────────────────────────────

DEFAULT_MODEL = os.environ.get("INSIDER_MODEL", "gemini-1.5-flash")
HAIKU_MODEL = os.environ.get("INSIDER_MODEL_FAST", "gemini-1.5-flash")
OPUS_MODEL = os.environ.get("INSIDER_MODEL_DEEP", "gemini-1.5-pro")


# ── Direction taxonomy ───────────────────────────────────────────────────────

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"
DIRECTIONS = (BULLISH, BEARISH, NEUTRAL)


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class Signal:
    """A single scout's structured output."""

    scout: str
    ticker: str  # ticker, asset symbol, or "MACRO"
    direction: str  # BULLISH | BEARISH | NEUTRAL
    confidence: int  # 1–5
    reason: str  # one-line plain-English reason
    raw: str  # full prompt output for audit


@dataclass
class ConsensusEvent:
    """Sophie's output when ≥3 scouts agree."""

    ticker: str
    direction: str
    scouts: list[str]
    reasons: list[str]
    timestamp: datetime


# ── State store ──────────────────────────────────────────────────────────────


def _ensure_dirs() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)


def _conn() -> sqlite3.Connection:
    _ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scout TEXT NOT NULL,
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            reason TEXT NOT NULL,
            raw TEXT NOT NULL,
            ts TEXT NOT NULL
        )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS consensus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,
            scouts TEXT NOT NULL,
            reasons TEXT NOT NULL,
            ts TEXT NOT NULL,
            dispatched INTEGER DEFAULT 0
        )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts)""")
    return conn


def record_signal(sig: Signal) -> None:
    """Append a scout signal to the state store."""
    with _conn() as c:
        c.execute(
            "INSERT INTO signals (scout, ticker, direction, confidence, reason, raw, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sig.scout,
                sig.ticker,
                sig.direction,
                sig.confidence,
                sig.reason,
                sig.raw,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def read_window(days: int = 7) -> list[Signal]:
    """Return all scout signals in the last `days` days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT scout, ticker, direction, confidence, reason, raw "
            "FROM signals WHERE ts >= ? ORDER BY ts DESC",
            (cutoff,),
        ).fetchall()
    return [Signal(*r) for r in rows]


def record_consensus(ev: ConsensusEvent) -> int:
    """Write a consensus event. Returns the row id for Ross to track dispatch."""
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO consensus (ticker, direction, scouts, reasons, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                ev.ticker,
                ev.direction,
                json.dumps(ev.scouts),
                json.dumps(ev.reasons),
                ev.timestamp.isoformat(),
            ),
        )
        return int(cur.lastrowid or 0)


def pending_consensus() -> list[tuple[int, ConsensusEvent]]:
    """Ross reads this — events not yet dispatched."""
    with _conn() as c:
        rows = c.execute(
            "SELECT id, ticker, direction, scouts, reasons, ts FROM consensus WHERE dispatched = 0"
        ).fetchall()
    out: list[tuple[int, ConsensusEvent]] = []
    for r in rows:
        out.append(
            (
                int(r[0]),
                ConsensusEvent(
                    ticker=r[1],
                    direction=r[2],
                    scouts=json.loads(r[3]),
                    reasons=json.loads(r[4]),
                    timestamp=datetime.fromisoformat(r[5]),
                ),
            )
        )
    return out


def mark_dispatched(row_id: int) -> None:
    with _conn() as c:
        c.execute("UPDATE consensus SET dispatched = 1 WHERE id = ?", (row_id,))


# ── Gemini client ────────────────────────────────────────────────────────────


def get_gemini(model: str | None = None) -> "genai.GenerativeModel":
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Add it to ~/insider-routines/.env"
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model or DEFAULT_MODEL)


def run_scout(
    scout_name: str,
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 2048,
) -> Signal:
    """Run a scout's prompt against Gemini. Parse the structured trailer. Persist.

    Scout prompts MUST end with a strict JSON block of the form:

        {"ticker": "<TICKER>", "direction": "BULLISH|BEARISH|NEUTRAL",
         "confidence": <1-5>, "reason": "<one line>"}

    This module parses the LAST JSON object in the response.
    """
    client = get_gemini(model)
    # Gemini takes system instruction at model level; combine for simplicity.
    full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
    response = client.generate_content(
        full_prompt,
        generation_config={"max_output_tokens": max_tokens},
    )
    raw = response.text.strip()

    payload = _extract_last_json(raw)
    if payload is None:
        # No usable signal this run — record a NEUTRAL placeholder.
        sig = Signal(
            scout=scout_name,
            ticker="MACRO",
            direction=NEUTRAL,
            confidence=1,
            reason="no qualifying signal this run",
            raw=raw,
        )
    else:
        sig = Signal(
            scout=scout_name,
            ticker=str(payload.get("ticker", "MACRO")).upper(),
            direction=_normalise_direction(payload.get("direction", NEUTRAL)),
            confidence=int(payload.get("confidence", 1) or 1),
            reason=str(payload.get("reason", "")).strip()[:240],
            raw=raw,
        )
    record_signal(sig)
    log(
        scout_name,
        f"signal: {sig.ticker} {sig.direction} conf={sig.confidence} :: {sig.reason}",
    )
    return sig


def _extract_last_json(text: str) -> dict[str, Any] | None:
    """Find the last `{...}` JSON object in text. Tolerant of prose around it."""
    depth = 0
    start = -1
    candidates: list[str] = []
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidates.append(text[start : i + 1])
                start = -1
    for c in reversed(candidates):
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _normalise_direction(d: Any) -> str:
    s = str(d).upper().strip()
    return s if s in DIRECTIONS else NEUTRAL


# ── Delivery ─────────────────────────────────────────────────────────────────


def send_email(subject: str, body: str) -> None:
    user = os.environ.get("GMAIL_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("GMAIL_TO", user)
    if not user or not pw:
        raise RuntimeError(
            "GMAIL_USER / GMAIL_APP_PASSWORD not set. Add them to ~/insider-routines/.env"
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.send_message(msg)


def send_telegram(text: str) -> bool:
    """Optional. Returns True if delivered, False if skipped."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    import urllib.request
    import urllib.parse

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": chat, "text": text, "parse_mode": "Markdown"}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


# ── Logging ──────────────────────────────────────────────────────────────────


def log(scope: str, message: str) -> None:
    """Append-only log per scope (= agent name)."""
    _ensure_dirs()
    line = f"{datetime.now(timezone.utc).isoformat()} [{scope}] {message}\n"
    (LOGS / f"{scope.lower()}.log").open("a", encoding="utf-8").write(line)


# ── Pretty-print helpers (for terminal smoke runs) ───────────────────────────


def render_consensus(ev: ConsensusEvent) -> str:
    """Plain-text body for email + Telegram."""
    head = f"SOPHIE CONSENSUS — {ev.direction} on {ev.ticker}"
    rule = "=" * len(head)
    body = [head, rule, f"Time: {ev.timestamp.isoformat(timespec='minutes')}", ""]
    body.append(f"{len(ev.scouts)} of 5 scouts agree:")
    for scout, reason in zip(ev.scouts, ev.reasons):
        body.append(f"  · {scout:<10} {reason}")
    body.append("")
    body.append(
        textwrap.fill(
            "This is informational, not a trade instruction. Ross did not "
            "place a trade. The decision is yours.",
            width=72,
        )
    )
    return "\n".join(body)
