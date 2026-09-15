"""Pydantic model for a single append-only decision-log entry."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DecisionLogEntry(BaseModel):
    """One immutable record of an agent's input, context, decision, and reasoning."""

    id: int
    payment_id: str
    agent_name: str
    timestamp: datetime
    input: Any
    context: Any
    decision: Any
    reasoning: str
