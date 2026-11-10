import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from videotape.fal import Fal, FalError

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


@pytest.mark.parametrize("failure", [http(500, "runner crashed"), urllib.error.URLError("connection reset")])
def test_a_failed_submit_is_never_sent_again(failure):
    _, queue = exchange(submit=[failure])
    with pytest.raises(FalError, match="submit to alibaba/wan-3.0/image-to-video failed"):
        Fal(KEY, send=queue, sleep=lambda _: None).run("alibaba/wan-3.0/image-to-video", {"prompt": "p"})
    assert [method for method, _, _ in queue.sent()] == ["POST"]


def test_a_failed_poll_or_download_is_tried_again(tmp_path):
    response, queue = exchange(status=[http(503), urllib.error.URLError("timed out"), recorded("image-to-video")["status"]],
                               video=[urllib.error.URLError("reset"), b"the video"])
    client = Fal(KEY, send=queue, sleep=lambda _: None)
    assert client.run("alibaba/wan-3.0/image-to-video", {"prompt": "p"}) == response
    client.download(response["result"]["video"]["url"], tmp_path / "take.mp4")
    assert (tmp_path / "take.mp4").read_bytes() == b"the video"
    assert [method for method, _, _ in queue.sent()] == ["POST", "GET", "GET", "GET", "GET", "GET", "GET"]


def test_the_key_never_appears_in_an_error():
    _, queue = exchange(submit=[http(401, f'{{"detail": "Invalid key {KEY}"}}')])
    with pytest.raises(FalError) as error:
        Fal(KEY, send=queue).run("alibaba/wan-3.0/image-to-video", {"prompt": "p"})
    assert KEY not in str(error.value)
    assert "HTTP 401" in str(error.value) and "<FAL_KEY>" in str(error.value)


def test_the_key_is_sent_only_to_the_queue():
    response, queue = exchange()
    elsewhere = {**response["submitted"], "status_url": "https://example.com/steal/status"}
    queue.answers[("POST", "https://queue.fal.run/alibaba/wan-3.0/image-to-video")] = [elsewhere]
    with pytest.raises(FalError, match="https://example.com/steal/status, which is not on https://queue.fal.run"):
        Fal(KEY, send=queue).run("alibaba/wan-3.0/image-to-video", {"prompt": "p"})
    assert [url for _, url, _ in queue.sent()] == ["https://queue.fal.run/alibaba/wan-3.0/image-to-video"]
