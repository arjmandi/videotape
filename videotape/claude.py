"""Claude as a service: the Messages API over plain HTTP, which scripts/words-test and the reader share, and the
reader, which sees a key's picture and reports every line of text on it, which look like controls, which are drawn
marked, and each chart.

The API (platform.claude.com/docs/en/api/messages): POST https://api.anthropic.com/v1/messages, and
/v1/messages/count_tokens, which is free, with the headers x-api-key and anthropic-version. The model is pinned, so a
request names no fallback model, and a refusal fails. This model always thinks, and its thinking is billed as output
tokens. The key goes only into the x-api-key header, and is scrubbed from any error."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from videotape import frames
from videotape.atomic import write_atomically
from videotape.checks import Free, Purse, Read, Spot
from videotape.errors import ModelError, ScreenplayError
from videotape.frames import Box, Frame
from videotape.ledger import now
from videotape.screenplay import Chart
from videotape.wan import tokens

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


def _urlopen(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=900) as response:
        return response.read()


def post(url: str, body: dict, key: str, send: Send, what: str) -> dict:
    """One request, sent once. The key goes only into the x-api-key header, and is scrubbed from any error. A request
    that fails, or answers with something other than an object, is a ModelError: VT401, a call that failed."""
    asked = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "x-api-key": key, "anthropic-version": VERSION})
    try:
        answered = send(asked)
    except urllib.error.HTTPError as error:
        failure = f"{what} failed with HTTP {error.code}: {error.read().decode(errors='replace')[:500]}"
        raise ModelError(failure.replace(key, f"<{KEY}>")) from None
    except OSError as error:
        raise ModelError(f"{what} failed: {error}".replace(key, f"<{KEY}>")) from None
    try:
        raw = json.loads(answered)
    except ValueError:
        raise ModelError(f"{what} answered with something other than JSON: {answered[:300]!r}") from None
    if not isinstance(raw, dict):
        raise ModelError(f"{what} answered with something other than an object: {answered[:300]!r}")
    return raw


def counted(body: dict, key: str, send: Send) -> int:
    """The request's input tokens, from the token counting endpoint, which is free."""
    raw = post(COUNT, {"model": body["model"], "messages": body["messages"]}, key, send, "the count")
    tokens = raw.get("input_tokens")
    if isinstance(tokens, bool) or not isinstance(tokens, int):
        raise ModelError(f"the count answered without input_tokens: {json.dumps(raw)[:300]}")
    return tokens


def call(body: dict, key: str, send: Send, what: str = "the call") -> Reply:
    """The paid call. A reply that billed tokens is returned whole or not, so that its cost reaches the ledger."""
    raw = post(API, body, key, send, what)
    try:
        tokens = {kind: int(raw["usage"][kind]) for kind in USD_PER_MILLION}
        text = "".join(block["text"] for block in raw["content"] if block["type"] == "text").strip()
        return Reply(text, raw["model"], tokens, raw["stop_reason"], raw)
    except (KeyError, TypeError, ValueError):
        raise ModelError(f"{what} answered with something other than a message: {json.dumps(raw)[:300]}") from None


# The reader.

MAX_TOKENS = 8192
"""The most output a read may take, thinking included, which the estimate charges in full."""
PROMPT = """This is the last frame of a short video of one screen of an app, {width} by {height} pixels. Report every \
piece of text you can see on it, each separate line or label as its own entry, in reading order: top to bottom, then \
left to right. Copy its text exactly as it is lettered, keeping its case, its punctuation and any misspelling, and do \
not correct it to what it ought to say. Give its box in pixels of this image: x and y of its top left corner, then its \
width and height. When the text sits on a button, a tile, a tab, a slot or a row that looks pressable, the box covers \
the whole of that control and control is true. marked is true when the entry is drawn as the selected or current one \
among its neighbours: lit, highlighted, inverted, underlined or filled where the others are not. Then, for each chart \
on the screen, give its title, its labels in order from left to right, and the value at each label as a number: the \
number lettered at the bar or point, or else the bar's height or the point's position read against the axis. A screen \
with no chart has an empty list of charts."""
_BOX = {"type": "object", "properties": {axis: {"type": "integer"} for axis in "xywh"}, "required": ["x", "y", "w", "h"],
        "additionalProperties": False}
_LINE = {"type": "object", "properties": {"text": {"type": "string"}, "box": _BOX, "control": {"type": "boolean"},
                                          "marked": {"type": "boolean"}},
         "required": ["text", "box", "control", "marked"], "additionalProperties": False}
_POINT = {"type": "object", "properties": {"label": {"type": "string"}, "value": {"type": "number"}},
          "required": ["label", "value"], "additionalProperties": False}
_CHART = {"type": "object", "properties": {"title": {"type": "string"}, "points": {"type": "array", "items": _POINT}},
          "required": ["title", "points"], "additionalProperties": False}
SCHEMA = {"type": "object", "properties": {"lines": {"type": "array", "items": _LINE},
                                           "charts": {"type": "array", "items": _CHART}},
          "required": ["lines", "charts"], "additionalProperties": False}
"""What a read answers with, which the API holds the reply to: structured output over output_config.format."""
PATCH = 28
"""platform.claude.com/docs/en/build-with-claude/vision, read 2026-11-15: an image costs ceil(width / 28) times
ceil(height / 28) tokens, and claude-opus-5-5 downscales nothing under 2,576 pixels on the long edge, which a key's
picture is well under."""


def estimate(width: int, height: int) -> float:
    """The most one read of a picture this size costs: its image tokens, the prompt's and the schema's at the input
    price, and every output token the read may take at the output price."""
    image = -(-width // PATCH) * -(-height // PATCH)
    words = tokens(PROMPT.format(width=width, height=height)) + tokens(json.dumps(SCHEMA))
    return price({"input_tokens": image + words, "output_tokens": MAX_TOKENS})


def request(frame: Frame) -> dict:
    """One read: the picture as a PNG, then the prompt, answered in the schema's shape."""
    picture = {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                           "data": base64.b64encode(frames.png(frame)).decode()}}
    return {"model": MODEL, "max_tokens": MAX_TOKENS,
            "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
            "messages": [{"role": "user", "content": [picture, {"type": "text", "text": PROMPT.format(
                width=frame.width, height=frame.height)}]}]}


def read(reply: str, width: int, height: int) -> Read:
    """What a reply reports, as a Read: a spot per line with a box kept within the picture, the boxes of the lines
    drawn marked, and each chart. A line with no words is left out."""
    try:
        told = json.loads(reply)
        spots, marked = [], []
        for line in told["lines"]:
            box = line["box"]
            x, y = min(max(int(box["x"]), 0), width), min(max(int(box["y"]), 0), height)
            kept = Box(x, y, min(max(int(box["w"]), 0), width - x), min(max(int(box["h"]), 0), height - y))
            if not isinstance(line["text"], str) or not line["text"].strip():
                continue
            spots.append(Spot(line["text"].strip(), kept, line["control"] is True))
            if line["marked"] is True:
                marked.append(kept)
        charts = tuple(Chart(chart["title"], tuple(point["label"] for point in chart["points"]),
                             tuple(float(point["value"]) for point in chart["points"])) for chart in told["charts"])
    except (ValueError, KeyError, TypeError):
        raise ModelError(f"{MODEL} answered with something other than a read: {reply[:300]!r}") from None
    return Read(MODEL, tuple(spots), tuple(marked), charts)


class ClaudeReader:
    """Claude, run as a service, which reads every line of a picture with its box, says which look like controls and
    which are drawn marked, and reports each chart. A read is paid, so the tape caches each reply in looks/, by the
    model, the prompt and the picture's hash, and a render run again pays for none of them."""

    name = MODEL
    key = KEY
    paid = True

    def __init__(self, tape: Path, send: Send | None = None) -> None:
        key = os.environ.get(KEY, "").strip()
        if not key:
            raise ScreenplayError("VT104", ".env", f"{self.name}, a reader of this model's eye, needs {KEY}, and it is "
                                  "not in the environment or .env", f"copy .env.example to .env and set {KEY} there, or "
                                  "export it")
        if not key.isprintable():
            raise ScreenplayError("VT104", ".env", f"{KEY} holds a character an HTTP header cannot carry, such as a "
                                  "line break", f"set {KEY} to the API key alone, in .env or the environment")
        # The sender is looked up when the reader is built, so a test that stands in for the network stands in here.
        self._key, self._send = key, send or _urlopen
        self.looks = tape / "looks"

    @staticmethod
    def most(width: int, height: int) -> float:
        return estimate(width, height)

    def see(self, frame: Frame, purse: Purse = Free()) -> Read:
        fields = [MODEL, PROMPT, SCHEMA, MAX_TOKENS, EFFORT, frame.width, frame.height, hashlib.sha256(frame.rgb).hexdigest()]
        path = self.looks / f"{hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()}.json"
        if not path.exists():
            reply = self._ask(frame, purse)
            seen = read(reply.text, frame.width, frame.height)
            self.looks.mkdir(parents=True, exist_ok=True)
            write_atomically(path, lambda partial: partial.write_text(json.dumps(
                {"model": reply.model, "reply": reply.text, "tokens": reply.tokens, "usd": round(reply.usd, 6)},
                indent=2) + "\n"))
            return seen
        return read(json.loads(path.read_text())["reply"], frame.width, frame.height)

    def _ask(self, frame: Frame, purse: Purse) -> Reply:
        """One paid read: its most cost is reserved before it is sent, and its bill, when it was billed, settles it
        after, whole reply or not."""
        most = estimate(frame.width, frame.height)
        purse.reserve(most)
        line = None
        try:
            reply = call(request(frame), self._key, self._send, f"{self.name}'s read")
            line = bill("read", reply)
            if reply.stop != "end_turn" or not reply.text:
                raise ModelError(f"{self.name}'s read stopped with {reply.stop!r} after {len(reply.text)} characters, "
                                 f"not a whole read; it cost ${reply.usd:.4f}")
        finally:
            purse.settle(line, most)
        return reply
