"""Claude as a service: the Messages API over plain HTTP, which scripts/words-test and the reader share.

The API (platform.claude.com/docs/en/api/messages): POST https://api.anthropic.com/v1/messages, and
/v1/messages/count_tokens, which is free, with the headers x-api-key and anthropic-version. The model is pinned, so a
request names no fallback model, and a refusal fails. This model always thinks, and its thinking is billed as output
tokens. The key goes only into the x-api-key header, and is scrubbed from any error."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from videotape.ledger import now

API = "https://api.anthropic.com/v1/messages"
COUNT = f"{API}/count_tokens"
VERSION = "2026-10-21"
MODEL = "claude-opus-5-5"
# This model's default, set so that a change of default does not change what a call does.
EFFORT = "medium"
# Dollars for a million tokens of claude-opus-5-5 on the Claude API, from Anthropic's model table as of 2026-10-06.
# No request asks for caching, so input and output tokens are the whole bill.
USD_PER_MILLION = {"input_tokens": 4.00, "output_tokens": 20.00}
KEY = "ANTHROPIC_API_KEY"

Send = Callable[[urllib.request.Request], bytes]


class ClaudeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Reply:
    """What a call answered: its text, the model that wrote it, the tokens it billed, why it stopped, and the raw
    response."""

    text: str
    model: str
    tokens: dict[str, int]
    stop: str
    raw: dict

    @property
    def usd(self) -> float:
        return price(self.tokens)

    def spent(self) -> str:
        return (f"{self.model}: {self.tokens['input_tokens']:,} input tokens, {self.tokens['output_tokens']:,} output "
                f"tokens, ${self.usd:.4f}")


def price(tokens: dict[str, int]) -> float:
    return sum(tokens[kind] * usd for kind, usd in USD_PER_MILLION.items()) / 1_000_000


def bill(kind: str, reply: Reply) -> dict:
    """A ledger line for one paid call: what kind of call, the model, its tokens, its dollars, and when."""
    return {"kind": kind, "model": reply.model, "request_id": reply.raw.get("id"), "tokens": reply.tokens,
            "usd": round(reply.usd, 6), "at": now()}


def api_key() -> str | None:
    """The API key from the environment, or None when it is not set or an HTTP header cannot carry it. A project
    command loads the project's .env into the environment first."""
    key = os.environ.get(KEY, "").strip()
    # http.client rejects a header with a control character by quoting the whole header, key and all, in its error.
    return key if key and key.isprintable() else None


def _urlopen(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=900) as response:
        return response.read()


def post(url: str, body: dict, key: str, send: Send, what: str) -> dict:
    """One request, sent once. The key goes only into the x-api-key header, and is scrubbed from any error."""
    asked = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "x-api-key": key, "anthropic-version": VERSION})
    try:
        answered = send(asked)
    except urllib.error.HTTPError as error:
        failure = f"{what} failed with HTTP {error.code}: {error.read().decode(errors='replace')[:500]}"
        raise ClaudeError(failure.replace(key, f"<{KEY}>")) from None
    except OSError as error:
        raise ClaudeError(f"{what} failed: {error}".replace(key, f"<{KEY}>")) from None
    try:
        raw = json.loads(answered)
    except ValueError:
        raise ClaudeError(f"{what} answered with something other than JSON: {answered[:300]!r}") from None
    if not isinstance(raw, dict):
        raise ClaudeError(f"{what} answered with something other than an object: {answered[:300]!r}")
    return raw


def counted(body: dict, key: str, send: Send) -> int:
    """The request's input tokens, from the token counting endpoint, which is free."""
    raw = post(COUNT, {"model": body["model"], "messages": body["messages"]}, key, send, "the count")
    tokens = raw.get("input_tokens")
    if isinstance(tokens, bool) or not isinstance(tokens, int):
        raise ClaudeError(f"the count answered without input_tokens: {json.dumps(raw)[:300]}")
    return tokens


def call(body: dict, key: str, send: Send, what: str = "the call") -> Reply:
    """The paid call. A reply that billed tokens is returned whole or not, so that its cost reaches the ledger."""
    raw = post(API, body, key, send, what)
    try:
        tokens = {kind: int(raw["usage"][kind]) for kind in USD_PER_MILLION}
        text = "".join(block["text"] for block in raw["content"] if block["type"] == "text").strip()
        return Reply(text, raw["model"], tokens, raw["stop_reason"], raw)
    except (KeyError, TypeError, ValueError):
        raise ClaudeError(f"{what} answered with something other than a message: {json.dumps(raw)[:300]}") from None
