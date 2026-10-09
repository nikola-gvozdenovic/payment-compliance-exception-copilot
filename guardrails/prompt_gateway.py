"""The only sanctioned path from agent code to an LLM (TICKET-8).

`PromptGateway.send()` checks the outgoing prompt *and* the model's response
for raw PII. Masking at ingestion (`mask_payment`) should already guarantee a
clean prompt; this is the second, independent check at the point where text
actually leaves the process, so a careless agent can't leak by pasting raw data
into a prompt. Responses are checked too because a model can echo or invent
identifiers (OWASP LLM02, Sensitive Information Disclosure).

Fail-closed: on any hit the call is refused with `PIILeakError` (a dirty prompt
never reaches the client; a dirty response is never returned), and a blocked
event is appended to the decision log. Both the error message and the log
entry carry placeholder labels only, never the leaked value itself.
"""

from pathlib import Path
from typing import Literal

from data.decision_log import log_decision
from data.decision_log.store import DECISION_LOG_DB_PATH
from guardrails.pii_masking import TokenVault, find_pii
from llm.client import LLMClient

Direction = Literal["prompt", "response"]


class PIILeakError(Exception):
    """Raw PII was found at the LLM boundary. The message names labels, never values."""

    def __init__(self, *, direction: Direction, labels: list[str]) -> None:
        self.direction = direction
        self.labels = labels
        super().__init__(f"PII detected in LLM {direction}: {', '.join(labels)}")


class PromptGateway:
    """Wraps an `LLMClient` with a two-way PII check for one payment's run."""

    def __init__(
        self,
        *,
        client: LLMClient,
        vault: TokenVault,
        db_path: Path | str = DECISION_LOG_DB_PATH,
    ) -> None:
        self._client = client
        self._vault = vault
        self._db_path = db_path

    def send(self, prompt: str) -> str:
        """Send a prompt to the model and return its response, refusing any raw PII."""
        if not isinstance(prompt, str):
            raise TypeError(
                f"PromptGateway.send() takes a prompt string, got {type(prompt).__name__}; "
                "render the prompt from a MaskedPayment first"
            )
        labels = find_pii(prompt, self._vault)
        if labels:
            self._block("prompt", labels)

        response = self._client.complete(prompt)

        labels = find_pii(response, self._vault)
        if labels:
            self._block("response", labels)
        return response

    def _block(self, direction: Direction, labels: list[str]) -> None:
        log_decision(
            payment_id=self._vault.payment_id,
            agent_name="pii_guardrail",
            input={"direction": direction},
            context={"labels": labels},
            decision="blocked",
            reasoning="Raw PII detected at the LLM prompt boundary; call refused (fail-closed).",
            db_path=self._db_path,
        )
        raise PIILeakError(direction=direction, labels=labels)
