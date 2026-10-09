"""Model-agnostic LLM client interface (PRD Section 6.2).

Every concrete model client (the default local Ollama client arrives in
TICKET-5; a hosted model can be swapped in later) implements this one-method
protocol, so agent logic never depends on a specific provider.

Agents must never call an `LLMClient` directly. The only sanctioned path to a
model is `guardrails.PromptGateway`, which checks every prompt and every
response for raw PII before letting it through (TICKET-8).
"""

from typing import Protocol


class LLMClient(Protocol):
    """Anything that can turn a prompt string into a completion string."""

    def complete(self, prompt: str) -> str: ...
