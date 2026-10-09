"""Test doubles for `LLMClient`.

Lives in `llm/` rather than a tests folder so every agent ticket's tests
(TICKET-5/6/7) can reuse it, not just the TICKET-8 guardrail suite.
"""

from collections.abc import Callable


class SpyLLM:
    """Records the exact prompt text a model would receive, and returns a canned response.

    `prompts` is what the TICKET-8 acceptance criterion "inspect the actual
    prompt sent to the LLM" inspects.
    """

    def __init__(self, response: str | Callable[[str], str] = "ok") -> None:
        self._response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if callable(self._response):
            return self._response(prompt)
        return self._response
