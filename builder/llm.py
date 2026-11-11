"""Anthropic Messages API over urllib, with retry. Owner: C4. Only file that reads ANTHROPIC_API_KEY.

Request shape confirmed via the claude-api skill (curl/examples.md): POST https://api.anthropic.com/v1/messages
with headers x-api-key, anthropic-version: 2026-10-21, content-type: application/json. On 2026-10-21 any
temperature/top_p/top_k field is a 400, so none is sent (temperature = API default).
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

# Fast current Sonnet, from the claude-api skill "Current Models (cached: 2026-11-03)" table.
DEFAULT_MODEL = "claude-sonnet-5-5"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
RETRY_ERROR_TYPES = {"overloaded_error", "rate_limit_error", "api_error"}


def model_name() -> str:
    """env DRYRUN_MODEL or DEFAULT_MODEL."""
    return os.environ.get("DRYRUN_MODEL") or DEFAULT_MODEL


class APIError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"Anthropic API error {status}: {body}")
        self.status = status
        self.body = body


def _error_type(body: str) -> str:
    try:
        return json.loads(body).get("error", {}).get("type", "") or ""
    except (ValueError, AttributeError):
        return ""


def _retry_after(headers) -> float | None:
    if headers is None:
        return None
    v = headers.get("retry-after") if hasattr(headers, "get") else None
    if v is None:
        return None
    try:
        return max(0.0, float(v))
    except (TypeError, ValueError):
        return None


def _has_tool_blocks(messages: list) -> bool:
    for m in messages:
        c = m.get("content")
        if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result")
                                       for b in c):
            return True
    return False


class AnthropicLLM:
    def __init__(self, model: str | None = None, max_tokens: int = 8192, max_retries: int = 6,
                 *, sleep=time.sleep, urlopen=urllib.request.urlopen, base_delay: float = 1.0,
                 max_delay: float = 60.0, timeout: float = 600.0, rng: random.Random | None = None):
        self.model = model or model_name()
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self._sleep = sleep
        self._urlopen = urlopen
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self._rng = rng or random.Random()
        self.retries = 0   # total retries made, for logging

    def _body(self, system: list, messages: list, tools: list | None) -> dict:
        body = {"model": self.model, "max_tokens": self.max_tokens, "system": system, "messages": messages}
        if tools:
            body["tools"] = tools
        elif _has_tool_blocks(messages):
            # tools=None means "no more tool calls". History still holds tool_use/tool_result blocks, so keep
            # the same tool list (valid request, unchanged cache prefix) and forbid calls with tool_choice none.
            from builder.tools import TOOL_SCHEMAS
            body["tools"] = TOOL_SCHEMAS
            body["tool_choice"] = {"type": "none"}
        return body

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        backoff = min(self.max_delay, self.base_delay * (2 ** attempt))
        jittered = backoff * (0.5 + self._rng.random() * 0.5)
        if retry_after is not None:
            return max(retry_after, jittered)   # never sooner than the server asked
        return jittered

    def capture_key(self) -> None:
        """Move ANTHROPIC_API_KEY out of os.environ into this object, so the agent's tools (and anything that
        can read this process's environment, e.g. `ps eww $PPID`) never see it. run.py calls this at startup."""
        self._key = os.environ.pop("ANTHROPIC_API_KEY", None) or getattr(self, "_key", None)

    def create(self, system: list, messages: list, tools: list | None) -> dict:
        key = getattr(self, "_key", None) or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        data = json.dumps(self._body(system, messages, tools)).encode("utf-8")
        headers = {"x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"}
        attempt = 0
        while True:
            req = urllib.request.Request(API_URL, data=data, headers=headers, method="POST")
            status, body, resp_headers = None, "", None
            try:
                with self._urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                status, resp_headers = e.code, e.headers
                try:
                    body = e.read().decode("utf-8", "replace")
                except Exception:
                    body = ""
                retryable = status in RETRY_STATUS or status >= 500 or _error_type(body) in RETRY_ERROR_TYPES
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                status, body, retryable = 0, repr(e), True
            if not retryable or attempt >= self.max_retries:
                raise APIError(status, body)
            delay = self._delay(attempt, _retry_after(resp_headers))
            print(f"llm: retry {attempt + 1}/{self.max_retries} after {status} in {delay:.1f}s",
                  file=sys.stderr)
            self._sleep(delay)
            self.retries += 1
            attempt += 1

    @property
    def params(self) -> dict:
        """Logged into state.params (max_tokens, temperature: 'api-default', ...)."""
        return {"max_tokens": self.max_tokens, "temperature": "api-default", "thinking": "api-default",
                "anthropic_version": API_VERSION, "max_retries": self.max_retries}
