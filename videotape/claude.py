"""Claude as a service: the Messages API over plain HTTP, which scripts/words-test, the reader and the judge share;
the reader, which sees a key's picture and reports every line of text on it, which look like controls, which are
drawn marked, and each chart; and the judge, which sees frames spread across a move and says of each whether it shows
two pictures overlaid, as the middle of a dissolve does.

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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from videotape import frames
from videotape.atomic import write_atomically
from videotape.checks import FRAMES, Dissolve, Free, Purse, Read, Spot
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


def paid(body: dict, key: str, send: Send, kind: str, most: float, purse: Purse, what: str) -> Reply:
    """One paid call under a purse: its most cost is reserved before it is sent, and its bill, when it was billed,
    settles it after, whole reply or not. kind names its ledger line, a read or a judgment."""
    purse.reserve(most)
    line = None
    try:
        reply = call(body, key, send, what)
        line = bill(kind, reply)
        if reply.stop != "end_turn" or not reply.text:
            raise ModelError(f"{what} stopped with {reply.stop!r} after {len(reply.text)} characters, not a whole "
                             f"{kind}; it cost ${reply.usd:.4f}")
    finally:
        purse.settle(line, most)
    return reply


def key_from_environment(role: str) -> str:
    """The API key, from the environment or the project's .env: VT104 without one, or with one an HTTP header cannot
    carry. role says what needs it, as in a reader of this model's eye."""
    key = os.environ.get(KEY, "").strip()
    if not key:
        raise ScreenplayError("VT104", ".env", f"{MODEL}, {role}, needs {KEY}, and it is not in the environment or "
                              ".env", f"copy .env.example to .env and set {KEY} there, or export it")
    if not key.isprintable():
        raise ScreenplayError("VT104", ".env", f"{KEY} holds a character an HTTP header cannot carry, such as a line "
                              "break", f"set {KEY} to the API key alone, in .env or the environment")
    return key


def cached(looks: Path, fields: list) -> Path:
    """Where a tape caches the reply to the request these fields name."""
    return looks / f"{hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()}.json"


def remembered[T](looks: Path, fields: list, ask: Callable[[], Reply], parse: Callable[[str], T]) -> T:
    """What the reply to the request these fields name parses into: from the tape's cache, or from asking, whose reply
    is cached once it parses, so a reply that is no answer is asked for again."""
    path = cached(looks, fields)
    if path.exists():
        return parse(json.loads(path.read_text())["reply"])
    reply = ask()
    parsed = parse(reply.text)
    looks.mkdir(parents=True, exist_ok=True)
    write_atomically(path, lambda partial: partial.write_text(json.dumps(
        {"model": reply.model, "reply": reply.text, "tokens": reply.tokens, "usd": round(reply.usd, 6)},
        indent=2) + "\n"))
    return parsed


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
UNCOUNTED = 195
"""Input tokens a read bills beyond its picture's and those tokens() counts in its prompt and schema. Every read of a
1280x720 picture in the paid screen test of 2026-11-16 billed 2,191 input tokens, where the picture is 1,196 and
tokens() counts 800."""


def estimate(width: int, height: int) -> float:
    """The most one read of a picture this size costs: its image tokens, the prompt's, the schema's and the uncounted
    at the input price, and every output token the read may take at the output price."""
    image = -(-width // PATCH) * -(-height // PATCH)
    words = tokens(PROMPT.format(width=width, height=height)) + tokens(json.dumps(SCHEMA)) + UNCOUNTED
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
        # The sender is looked up when the reader is built, so a test that stands in for the network stands in here.
        self._key, self._send = key_from_environment("a reader of this model's eye"), send or _urlopen
        self.looks = tape / "looks"

    @staticmethod
    def most(width: int, height: int) -> float:
        return estimate(width, height)

    def see(self, frame: Frame, purse: Purse = Free()) -> Read:
        fields = [MODEL, PROMPT, SCHEMA, MAX_TOKENS, EFFORT, frame.width, frame.height, hashlib.sha256(frame.rgb).hexdigest()]
        return remembered(self.looks, fields,
                          lambda: paid(request(frame), self._key, self._send, "read", estimate(frame.width, frame.height),
                                       purse, f"{self.name}'s read"),
                          lambda reply: read(reply, frame.width, frame.height))


# The judge.

JUDGE_MAX_TOKENS = 4096
"""The most output a judgment may take, thinking included, which the estimate charges in full."""
JUDGE_PROMPT = """These are {count} frames taken at even steps across one short clip, {width} by {height} pixels, in the \
order they play: the clip's first frame first and its last frame last. The clip moves from one screen of an app to the \
next. For each frame, in order, say whether it shows two pictures overlaid: one image fading into another, so that \
parts of both show through each other at once, as the middle of a cross-dissolve does. One picture in motion, \
blurred, panned, zoomed, cropped or lit otherwise is one picture, not two. Then say in a few words what the frame \
shows."""
_JUDGED = {"type": "object", "properties": {"overlaid": {"type": "boolean"}, "seen": {"type": "string"}},
           "required": ["overlaid", "seen"], "additionalProperties": False}
JUDGE_SCHEMA = {"type": "object", "properties": {"frames": {"type": "array", "items": _JUDGED}}, "required": ["frames"],
                "additionalProperties": False}
"""What a judgment answers with: an entry per frame, in the frames' order."""


def asked() -> str:
    """What a judgment's answer answers, hashed: the model, the prompt, the schema and the settings. A recorded
    answer to another question is no answer to this one."""
    return hashlib.sha256(json.dumps([MODEL, JUDGE_PROMPT, JUDGE_SCHEMA, JUDGE_MAX_TOKENS, EFFORT, FRAMES],
                                     sort_keys=True).encode()).hexdigest()


def judge_estimate(width: int, height: int, count: int = FRAMES) -> float:
    """The most one judgment of this many frames of this size costs, priced as a read is."""
    image = count * (-(-width // PATCH) * -(-height // PATCH))
    words = tokens(JUDGE_PROMPT.format(count=count, width=width, height=height)) + tokens(json.dumps(JUDGE_SCHEMA)) + UNCOUNTED
    return price({"input_tokens": image + words, "output_tokens": JUDGE_MAX_TOKENS})


def judge_request(pictures: Sequence[Frame]) -> dict:
    """One judgment: every frame as a PNG, in order, then the prompt, answered in the schema's shape."""
    images = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                           "data": base64.b64encode(frames.png(picture)).decode()}}
              for picture in pictures]
    first = pictures[0]
    return {"model": MODEL, "max_tokens": JUDGE_MAX_TOKENS,
            "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
            "messages": [{"role": "user", "content": [*images, {"type": "text", "text": JUDGE_PROMPT.format(
                count=len(pictures), width=first.width, height=first.height)}]}]}


def judged(reply: str, at: Sequence[int]) -> Dissolve:
    """What a reply says of each frame, as a Dissolve, with the frames numbered as at numbers them: ModelError when
    it does not answer for every frame."""
    try:
        told = json.loads(reply)["frames"]
        if len(told) != len(at):
            raise ValueError
        overlaid = tuple(entry["overlaid"] is True for entry in told)
        seen = tuple(str(entry["seen"]).strip() for entry in told)
    except (ValueError, KeyError, TypeError):
        raise ModelError(f"{MODEL} answered with something other than a judgment of {len(at)} frames: "
                         f"{reply[:300]!r}") from None
    return Dissolve(MODEL, tuple(at), overlaid, seen)


class ClaudeJudge:
    """Claude, run as a service, which looks at frames spread across a move's take and says of each whether it shows
    two pictures overlaid: the dissolve check, VT507. A judgment is paid, so the tape caches each reply in looks/, as
    a read is cached, by the model, the prompt and the frames' hashes."""

    name = MODEL
    key = KEY
    paid = True

    def __init__(self, tape: Path, send: Send | None = None) -> None:
        self._key, self._send = key_from_environment("the judge of this model's moves"), send or _urlopen
        self.looks = tape / "looks"

    @staticmethod
    def most(width: int, height: int) -> float:
        return judge_estimate(width, height)

    def judge(self, sampled: Sequence[tuple[int, Frame]], purse: Purse = Free()) -> Dissolve:
        at, pictures = [number for number, _ in sampled], [picture for _, picture in sampled]
        most = judge_estimate(pictures[0].width, pictures[0].height, len(pictures))
        return remembered(self.looks, _fields(pictures),
                          lambda: paid(judge_request(pictures), self._key, self._send, "judgment", most, purse,
                                       f"{self.name}'s judgment"),
                          lambda reply: judged(reply, at))

    def recorded(self, sampled: Sequence[tuple[int, Frame]]) -> dict | None:
        """The cached reply to a judgment of these frames, as the cache holds it, or None when none was asked."""
        path = cached(self.looks, _fields([picture for _, picture in sampled]))
        return json.loads(path.read_text()) if path.exists() else None


def _fields(pictures: Sequence[Frame]) -> list:
    return [MODEL, JUDGE_PROMPT, JUDGE_SCHEMA, JUDGE_MAX_TOKENS, EFFORT,
            [[picture.width, picture.height, hashlib.sha256(picture.rgb).hexdigest()] for picture in pictures]]
