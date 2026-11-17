"""fal.ai's queue, the boundary to hosted models that bill per call.

Hosts, paths and the auth header follow fal's queue REST docs (fal.ai/docs/model-apis/model-endpoints/queue): POST
https://queue.fal.run/<endpoint> with "Authorization: Key <FAL_KEY>" answers with a request id, a status_url and a
response_url, polled until the status is COMPLETED."""

import http.client
import itertools
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from videotape.errors import ModelError

QUEUE = "https://queue.fal.run"
POLL_SECONDS = 5
WAIT_SECONDS = 1800
# For a poll, a result or a download, which cost nothing to repeat. A submit is sent once, because each one is paid for.
TRIES = 5

Send = Callable[[urllib.request.Request], bytes]


@dataclass(frozen=True)
class Receipt:
    """What one paid call reports: fal's request id, the seconds of video it billed, their price, and the raw response."""

    request_id: str
    duration: float
    usd: float
    response: dict


@dataclass(frozen=True)
class Price:
    """What a model that bills by the second of video charges, how many seconds one call makes, and what a call costs
    beyond its seconds."""

    usd_per_second: float
    seconds: int
    usd_per_call: float = 0.0
    """For a model that also bills the tokens of its prompt, the most they can cost, which no answer of fal's counts."""

    @property
    def usd(self) -> float:
        """What one call costs."""
        return self.billed(self.seconds)

    def billed(self, seconds: float) -> float:
        """What a call that filmed this many seconds costs."""
        return round(seconds * self.usd_per_second + self.usd_per_call, 4)

    def span(self, least: int, most: int) -> str:
        """What this many calls cost, as a range when they differ."""
        prices = f"${least * self.usd:.2f} to ${most * self.usd:.2f}" if most > least else f"${least * self.usd:.2f}"
        rate = self.usd_per_second
        prompt = f" plus ${self.usd_per_call:.2f} a call for the prompt" if self.usd_per_call else ""
        return f"{prices} at ${rate:.2f}/s{prompt}" if round(rate, 2) == rate else f"{prices} at ${rate:g}/s{prompt}"


def _urlopen(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


class Fal:
    """fal's queue over plain HTTP. The key goes only into the Authorization header of requests to the queue's host,
    and never into a message, a result or a file."""

    def __init__(self, key: str, send: Send = _urlopen, sleep: Callable[[float], None] = time.sleep):
        self._key = key
        self._send = send
        self._sleep = sleep

    def run(self, endpoint: str, arguments: dict) -> dict:
        """Submit one request, wait for it, and return fal's three answers: submitted, the last status, and the result."""
        return self.wait(endpoint, self.submit(endpoint, arguments))

    def submit(self, endpoint: str, arguments: dict) -> dict:
        """Submit one request, once, and return fal's answer: the request id and where to poll and fetch it."""
        submitted = self._json(self._queue(f"{QUEUE}/{endpoint}", arguments), 1, f"submit to {endpoint}")
        try:
            submitted["request_id"], submitted["status_url"], submitted["response_url"]
        except (KeyError, TypeError):
            raise ModelError(self._scrub(f"submit to {endpoint} answered without a request: {submitted}")) from None
        return submitted

    def wait(self, endpoint: str, submitted: dict) -> dict:
        """Poll a submitted request until it is done, fetch its result, and return fal's three answers."""
        request_id, status_url, response_url = submitted["request_id"], submitted["status_url"], submitted["response_url"]
        for _ in range(WAIT_SECONDS // POLL_SECONDS):
            status = self._json(self._queue(status_url), TRIES, f"status of {endpoint} request {request_id}")
            if status.get("status") == "COMPLETED":
                break
            self._sleep(POLL_SECONDS)
        else:
            raise ModelError(f"{endpoint} request {request_id} is not done after {WAIT_SECONDS} s; "
                           f"its result will be at {response_url}")
        result = self._json(self._queue(response_url), TRIES, f"result of {endpoint} request {request_id}")
        return {"submitted": submitted, "status": status, "result": result}

    def download(self, url: str, out: Path) -> None:
        out.write_bytes(self._call(urllib.request.Request(url), TRIES, f"download of {url}"))

    def _queue(self, url: str, body: dict | None = None) -> urllib.request.Request:
        # The status and result urls come from fal's answer, so check where they point before the key goes there.
        if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(QUEUE).netloc:
            raise ModelError(f"fal answered with {url}, which is not on {QUEUE}; the API key is only sent there")
        if body is None:
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
        else:
            request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                             headers={"Accept": "application/json", "Content-Type": "application/json"})
        # urllib copies ordinary headers onto a redirect to any host. An unredirected header stays on this request.
        request.add_unredirected_header("Authorization", f"Key {self._key}")
        return request

    def _json(self, request: urllib.request.Request, tries: int, what: str) -> dict:
        body = self._call(request, tries, what)
        try:
            answer = json.loads(body)
        except json.JSONDecodeError:
            answer = None
        if not isinstance(answer, dict):
            shown = self._scrub(body.decode(errors="replace"))[:300]
            raise ModelError(f"{what} answered with something other than a JSON object: {shown!r}")
        return answer

    def _call(self, request: urllib.request.Request, tries: int, what: str) -> bytes:
        for attempt in itertools.count(1):
            try:
                return self._send(request)
            except urllib.error.HTTPError as error:
                said = self._scrub(error.read().decode(errors="replace"))
                if (flagged := refusal(error.code, said)) is not None:
                    raise ModelError(f"{what} was refused for its content: HTTP 422 content_policy_violation, {flagged}",
                                     "VT409", "nothing; a render skips the take's seed from now on")
                retry = error.code == 429 or error.code >= 500
                failure = f"{what} failed with HTTP {error.code}: {said[:500]}"
            except (OSError, http.client.HTTPException) as error:
                retry, failure = True, f"{what} failed: {error}"
            if not retry or attempt == tries:
                raise ModelError(self._scrub(failure))
            self._sleep(2 ** attempt)

    def _scrub(self, message: str) -> str:
        return message.replace(self._key, "<FAL_KEY>") if self._key else message


def refusal(status: int, body: str) -> str | None:
    """The categories fal's content checker flagged, when an answer refuses a request for its content, else None.
    fal.ai/docs/errors, read 2026-11-16: content_policy_violation is HTTP 422, not retryable, with the detail's type
    naming it, and a model's own moderation appends model_moderated to its categories."""
    if status != 422:
        return None
    try:
        detail = json.loads(body).get("detail")
    except (ValueError, AttributeError):
        return None
    for item in detail if isinstance(detail, list) else []:
        if isinstance(item, dict) and item.get("type") == "content_policy_violation":
            return ", ".join(map(str, item.get("categories") or [])) or "no category"
    return None
