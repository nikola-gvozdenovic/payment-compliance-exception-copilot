"""SQLite-backed, append-only storage for the agent decision log.

This module exposes exactly two public functions: `log_decision` (insert) and
`get_decisions_for_payment` (read). There is no update/delete function anywhere in
this module -- that is deliberate. "Append-only, tamper-evident-in-spirit" (PRD
Security Scope) is interpreted here as "no code path capable of altering a written
entry", not as a cryptographic guarantee (no hash-chaining). See the TICKET-3
implementation plan (.claude/plans/ticket-3-append-only-decision-log.md) for the
full rationale.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from data.decision_log.models import DecisionLogEntry

DECISION_LOG_DB_PATH = Path(__file__).parent / "decisions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    input TEXT NOT NULL,
    context TEXT NOT NULL,
    decision TEXT NOT NULL,
    reasoning TEXT NOT NULL
)
"""

_INDEX = "CREATE INDEX IF NOT EXISTS idx_decisions_payment_id ON decisions(payment_id)"


def _json_default(obj: object) -> Any:
    """`json.dumps` default callback: lets a pydantic BaseModel serialize directly."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    conn.execute(_INDEX)
    return conn


def log_decision(
    *,
    payment_id: str,
    agent_name: str,
    input: Any,
    context: Any,
    decision: Any,
    reasoning: str,
    db_path: Path | str = DECISION_LOG_DB_PATH,
) -> DecisionLogEntry:
    """Append one decision-log entry. There is no corresponding update/delete."""
    timestamp = datetime.now(UTC)
    input_json = json.dumps(input, default=_json_default)
    context_json = json.dumps(context, default=_json_default)
    decision_json = json.dumps(decision, default=_json_default)

    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO decisions (payment_id, agent_name, timestamp, input, context, decision, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payment_id,
                agent_name,
                timestamp.isoformat(),
                input_json,
                context_json,
                decision_json,
                reasoning,
            ),
        )
        conn.commit()
        # Return the JSON-normalized form (not the raw input objects) so a caller
        # sees the same shape here as they would from get_decisions_for_payment --
        # e.g. a pydantic BaseModel passed as `input` comes back as a plain dict.
        return DecisionLogEntry(
            id=cursor.lastrowid,
            payment_id=payment_id,
            agent_name=agent_name,
            timestamp=timestamp,
            input=json.loads(input_json),
            context=json.loads(context_json),
            decision=json.loads(decision_json),
            reasoning=reasoning,
        )
    finally:
        conn.close()


def get_decisions_for_payment(
    payment_id: str, db_path: Path | str = DECISION_LOG_DB_PATH
) -> list[DecisionLogEntry]:
    """Return every logged entry for a payment, in the order they were logged."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM decisions WHERE payment_id = ? ORDER BY id ASC",
            (payment_id,),
        ).fetchall()
        return [
            DecisionLogEntry(
                id=row["id"],
                payment_id=row["payment_id"],
                agent_name=row["agent_name"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                input=json.loads(row["input"]),
                context=json.loads(row["context"]),
                decision=json.loads(row["decision"]),
                reasoning=row["reasoning"],
            )
            for row in rows
        ]
    finally:
        conn.close()
