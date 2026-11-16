import io
import json
import urllib.error
import urllib.request
from http.client import IncompleteRead
from pathlib import Path

import pytest

from videotape.errors import ModelError
from videotape.fal import Fal

FIXTURES = Path(__file__).parent / "fixtures"
KEY = "fal-test-key-0123456789abcdef"


def recorded(mode: str) -> dict:
    return json.loads((FIXTURES / f"wan3.0-{mode}.json").read_text())


class Queue:
    """Answers each request as fal's queue would, from a table of url to answer. An answer that is an exception is raised."""

    def __init__(self, answers: dict[tuple[str, str], list]):
        self.answers = answers
        self.seen: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request) -> bytes:
        self.seen.append(request)
        answer = self.answers[(request.get_method(), request.full_url)].pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, bytes) else json.dumps(answer).encode()

    def sent(self) -> list[tuple[str, str, str | None]]:
        return [(r.get_method(), r.full_url, r.get_header("Authorization")) for r in self.seen]


def http(code: int, body: str = "") -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://queue.fal.run/x", code, "error", {}, io.BytesIO(body.encode()))


def exchange(*, submit=None, status=None, video=None) -> tuple[dict, Queue]:
    response = recorded("image-to-video")
    submitted, result = response["submitted"], response["result"]
    in_progress = {**response["status"], "status": "IN_PROGRESS"}
    return response, Queue({
        ("POST", "https://queue.fal.run/alibaba/wan-3.0/image-to-video"): submit or [submitted],
        ("GET", submitted["status_url"]): status or [in_progress, in_progress, response["status"]],
        ("GET", submitted["response_url"]): [result],
        ("GET", result["video"]["url"]): video or [b"the video"],
    })


def test_fal_submits_once_polls_until_done_then_fetches_the_result_and_downloads_the_video(tmp_path):
    response, queue = exchange()
    slept = []
    client = Fal(KEY, send=queue, sleep=slept.append)
    assert client.run("alibaba/wan-3.0/image-to-video", {"prompt": "p", "seed": 2}) == response
    client.download(response["result"]["video"]["url"], tmp_path / "take.mp4")
    assert (tmp_path / "take.mp4").read_bytes() == b"the video"
    status, result = response["submitted"]["status_url"], response["submitted"]["response_url"]
    assert queue.sent() == [("POST", "https://queue.fal.run/alibaba/wan-3.0/image-to-video", f"Key {KEY}"),
                            ("GET", status, f"Key {KEY}"), ("GET", status, f"Key {KEY}"), ("GET", status, f"Key {KEY}"),
                            ("GET", result, f"Key {KEY}"), ("GET", response["result"]["video"]["url"], None)]
    assert json.loads(queue.seen[0].data) == {"prompt": "p", "seed": 2}
    assert queue.seen[0].get_header("Content-type") == "application/json"
    assert slept == [5, 5]


def test_the_key_rides_only_in_the_authorization_header_and_never_follows_a_redirect(tmp_path):
    response, queue = exchange()
    client = Fal(KEY, send=queue, sleep=lambda _: None)
    client.run("alibaba/wan-3.0/image-to-video", {"prompt": "p"})
    client.download(response["result"]["video"]["url"], tmp_path / "take.mp4")
    for request in queue.seen:
        assert [name for name, value in request.header_items() if KEY in value] in ([], ["Authorization"])
        moved = urllib.request.HTTPRedirectHandler().redirect_request(request, None, 302, "Found", {}, "https://example.com/")
        assert KEY not in repr(moved.header_items())


@pytest.mark.parametrize("failure", [http(500, "runner crashed"), urllib.error.URLError("connection reset"),
                                     IncompleteRead(b"{", 20)])
def test_a_failed_submit_is_never_sent_again(failure):
    _, queue = exchange(submit=[failure])
    with pytest.raises(ModelError, match="submit to alibaba/wan-3.0/image-to-video failed"):
        Fal(KEY, send=queue, sleep=lambda _: None).run("alibaba/wan-3.0/image-to-video", {"prompt": "p"})
    assert [method for method, _, _ in queue.sent()] == ["POST"]


def test_a_failed_poll_or_download_is_tried_again(tmp_path):
    response, queue = exchange(status=[http(503), urllib.error.URLError("timed out"), IncompleteRead(b"{", 20),
                                       recorded("image-to-video")["status"]],
                               video=[urllib.error.URLError("reset"), b"the video"])
    client = Fal(KEY, send=queue, sleep=lambda _: None)
    assert client.run("alibaba/wan-3.0/image-to-video", {"prompt": "p"}) == response
    client.download(response["result"]["video"]["url"], tmp_path / "take.mp4")
    assert (tmp_path / "take.mp4").read_bytes() == b"the video"
    assert [method for method, _, _ in queue.sent()] == ["POST", "GET", "GET", "GET", "GET", "GET", "GET", "GET"]


def test_the_key_never_appears_in_an_error():
    _, queue = exchange(submit=[http(401, f'{{"detail": "Invalid key {KEY}"}}')])
    with pytest.raises(ModelError) as error:
        Fal(KEY, send=queue).run("alibaba/wan-3.0/image-to-video", {"prompt": "p"})
    assert KEY not in str(error.value)
    assert "HTTP 401" in str(error.value) and "<FAL_KEY>" in str(error.value)


@pytest.mark.parametrize("answer, said", [
    (http(401, "x" * 480 + f"Key {KEY}"), "HTTP 401"),
    (("x" * 280 + f"Key {KEY}").encode(), "something other than a JSON object"),
])
def test_the_key_is_scrubbed_before_a_long_error_is_cut(answer, said):
    """The key sits where the message is cut, so a cut before the scrub would leave its first characters."""
    _, queue = exchange(submit=[answer])
    with pytest.raises(ModelError) as error:
        Fal(KEY, send=queue).run("alibaba/wan-3.0/image-to-video", {"prompt": "p"})
    assert said in str(error.value)
    assert "<FAL_KEY>" in str(error.value) and KEY[:8] not in str(error.value)


def test_the_key_is_sent_only_to_the_queue():
    response, queue = exchange()
    elsewhere = {**response["submitted"], "status_url": "https://example.com/steal/status"}
    queue.answers[("POST", "https://queue.fal.run/alibaba/wan-3.0/image-to-video")] = [elsewhere]
    with pytest.raises(ModelError, match="https://example.com/steal/status, which is not on https://queue.fal.run"):
        Fal(KEY, send=queue).run("alibaba/wan-3.0/image-to-video", {"prompt": "p"})
    assert [url for _, url, _ in queue.sent()] == ["https://queue.fal.run/alibaba/wan-3.0/image-to-video"]


REFUSED = ('{"detail":[{"loc":["body"],"msg":"The content could not be processed because it contained material flagged by '
           'a content checker.","type":"content_policy_violation","url":"https://docs.fal.ai/errors#content_policy_violation",'
           '"input":"","categories":["model_moderated"]}]}')
"""fal's answer to the result of request 01a1e4a2-f25e-7972-979d-3aebd879c48c on the paid screen test of 2026-11-16."""


def test_a_result_refused_for_its_content_is_vt409_and_is_not_asked_for_again():
    response, queue = exchange()
    result = response["submitted"]["response_url"]
    queue.answers[("GET", result)] = [http(422, REFUSED)]
    with pytest.raises(ModelError) as error:
        Fal(KEY, send=queue, sleep=lambda _: None).run("alibaba/wan-3.0/image-to-video", {"prompt": "p"})
    assert error.value.code == "VT409"
    assert error.value.message == (f"result of alibaba/wan-3.0/image-to-video request {response['submitted']['request_id']} "
                                   "was refused for its content: HTTP 422 content_policy_violation, model_moderated")
    assert [url for _, url, _ in queue.sent()].count(result) == 1


def test_a_submit_refused_for_its_content_is_vt409_too():
    _, queue = exchange(submit=[http(422, REFUSED)])
    with pytest.raises(ModelError) as error:
        Fal(KEY, send=queue, sleep=lambda _: None).run("alibaba/wan-3.0/image-to-video", {"prompt": "p"})
    assert (error.value.code, error.value.message) == (
        "VT409", "submit to alibaba/wan-3.0/image-to-video was refused for its content: HTTP 422 "
                 "content_policy_violation, model_moderated")
    assert [method for method, _, _ in queue.sent()] == ["POST"]


@pytest.mark.parametrize("answer, tries", [
    (http(422, '{"detail":[{"loc":["body","prompt"],"msg":"field required","type":"value_error.missing"}]}'), 1),
    (http(422, '{"detail": "content policy"}'), 1),
    (http(422, "not json"), 1),
    (http(500, "runner crashed"), 5),
])
def test_a_422_that_is_no_content_refusal_and_a_500_keep_vt401(answer, tries):
    response, queue = exchange()
    result = response["submitted"]["response_url"]
    queue.answers[("GET", result)] = [answer] * tries
    with pytest.raises(ModelError) as error:
        Fal(KEY, send=queue, sleep=lambda _: None).run("alibaba/wan-3.0/image-to-video", {"prompt": "p"})
    assert error.value.code == "VT401"
    assert error.value.message.startswith(f"result of alibaba/wan-3.0/image-to-video request "
                                          f"{response['submitted']['request_id']} failed with HTTP {answer.code}: ")
    assert [url for _, url, _ in queue.sent()].count(result) == tries
