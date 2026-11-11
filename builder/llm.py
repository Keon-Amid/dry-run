"""Anthropic Messages API over urllib, with retry. Owner: C4. Only file that reads ANTHROPIC_API_KEY."""
from __future__ import annotations

DEFAULT_MODEL = ""   # C4: fill from the claude-api skill (fast current Sonnet)


def model_name() -> str:
    """env DRYRUN_MODEL or DEFAULT_MODEL."""
    raise NotImplementedError


class AnthropicLLM:
    def __init__(self, model: str | None = None, max_tokens: int = 8192, max_retries: int = 6):
        raise NotImplementedError

    def create(self, system: list, messages: list, tools: list | None) -> dict:
        raise NotImplementedError

    @property
    def params(self) -> dict:
        """Logged into state.params (max_tokens, temperature: 'api-default', ...)."""
        raise NotImplementedError
