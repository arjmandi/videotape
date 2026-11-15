"""Wan 3.0 on fal draws every pixel: text-to-video draws each state's key, and image-to-video draws each move from the
kept key it starts on to the kept key it lands on. Its takes are only compared with the 5B's, never trained on."""

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from videotape.fal import Fal, FalError, Price, Receipt
from videotape.plan import Mode
from videotape.publish import publish

# fal.ai/api/openapi/queue/openapi.json?endpoint_id=<endpoint>, read 2026-11-10: Wan30TextToVideoInput and
# Wan30ImageToVideoInput, whose start_image_url is the "First frame of the generated video" and end_image_url the
# "Last frame of the generated video".
ENDPOINTS = {
    Mode.TEXT_TO_VIDEO: "alibaba/wan-3.0/text-to-video",
    Mode.FIRST_AND_LAST_FRAME: "alibaba/wan-3.0/image-to-video",
}
# Five seconds without sound, like the 5B's clips. fal's defaults are 1080p, an adaptive aspect ratio, audio on and
# prompt expansion on, which rewrites the prompt, so each is set to give both models the same words at one size.
SETTINGS = {"resolution": "720p", "aspect_ratio": "16:9", "duration": 5, "audio": False, "enable_prompt_expansion": False}
# The same two schemas, read 2026-11-14: each gives its prompt a maxLength of 20000 characters.
PROMPT_CHARACTERS = 20_000
# Both endpoints' model pages on 2026-11-10: "$0.05 480p, $0.10 720p, or $0.20 1080p" for every second generated.
PRICE = Price(usd_per_second=0.10, seconds=SETTINGS["duration"])


@dataclass(frozen=True)
class Wan3Request:
    endpoint: str
    arguments: dict


class RecordedFailure(FalError):
    """A recorded request's poll or download failed. A render never submits it again on its own, so the error names
    the record, which deleting lets a render submit a new, paid take."""

    def __init__(self, message: str, record: Path) -> None:
        super().__init__(message)
        self.record = record


def request(mode: Mode, prompt: str, seed: int, start: Path | None = None, end: Path | None = None) -> Wan3Request:
    """A key is text-to-video from its prompt. A move is image-to-video pinned to the two key images it joins."""
    images = {"start_image_url": _data_uri(start), "end_image_url": _data_uri(end)} \
        if mode is Mode.FIRST_AND_LAST_FRAME else {}
    return Wan3Request(ENDPOINTS[mode], {"prompt": prompt, **SETTINGS, "seed": seed, **images})


def settings(mode: Mode) -> dict:
    """Everything a request depends on beyond its prompt, seed and images, which the take cache already hashes."""
    return {"endpoint": ENDPOINTS[mode], **SETTINGS}


def _data_uri(png: Path) -> str:
    # fal's API page for both endpoints: "You can pass a Base64 data URI as a file input."
    return "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()


def bill(response: dict) -> tuple[str, Receipt]:
    """The video's url and the receipt from fal's answers to one call, read without the network."""
    submitted, result = response["submitted"], response["result"]
    try:
        url, duration = result["video"]["url"], float(result["duration"])
    except (KeyError, TypeError, ValueError):
        raise FalError(f"request {submitted['request_id']} answered without a video and its duration: {result}") from None
    return url, Receipt(submitted["request_id"], duration, round(duration * PRICE.usd_per_second, 4), response)


class Wan3:
    name = "wan3.0"
    device = "fal"
    price = PRICE

    def __init__(self, fal: Fal):
        self.fal = fal

    @staticmethod
    def settings(mode: Mode) -> dict:
        return settings(mode)

    def text_to_video(self, prompt: str, seed: int, out: Path) -> Receipt:
        return self._film(request(Mode.TEXT_TO_VIDEO, prompt, seed), out)

    def first_last_frame(self, prompt: str, start: Path, end: Path, seed: int, out: Path) -> Receipt:
        return self._film(request(Mode.FIRST_AND_LAST_FRAME, prompt, seed, start, end), out)

    def download_again(self, out: Path) -> Receipt | None:
        record = request_record(out)
        if not record.exists():
            return None
        return self._fetch(record, json.loads(record.read_text()), out)

    def _film(self, built: Wan3Request, out: Path) -> Receipt:
        """One take, submitted once. fal's answer to the submit is recorded beside the take before the wait, so a
        render that dies between submitting and downloading polls and downloads that request on resume instead of
        paying for it again. The record holds the endpoint, the request id and its urls, never the key."""
        if (receipt := self.download_again(out)) is not None:
            return receipt
        record = request_record(out)
        submitted = {"endpoint": built.endpoint, **self.fal.submit(built.endpoint, built.arguments)}
        publish(record, lambda partial: partial.write_text(json.dumps(submitted, indent=2) + "\n"))
        return self._fetch(record, submitted, out)

    def _fetch(self, record: Path, submitted: dict, out: Path) -> Receipt:
        try:
            url, receipt = bill(self.fal.wait(submitted["endpoint"], submitted))
            self.fal.download(url, out)
        except FalError as error:
            raise RecordedFailure(str(error), record) from None
        return receipt


def request_record(out: Path) -> Path:
    """Where a take's submitted request is recorded: beside the take, under the take's name. A render films a take
    into <name>.partial.mp4 and publishes it as <name>.mp4, so the record goes by the name before the first dot."""
    return out.with_name(f"{out.name.partition('.')[0]}.request.json")


def from_environment() -> Wan3:
    if not (key := os.environ.get("FAL_KEY", "").strip()):
        raise FalError("wan3.0 needs FAL_KEY in the environment")
    # http.client rejects a header with a control character by quoting the whole header, key and all, in its error.
    if not key.isprintable():
        raise FalError("FAL_KEY holds a character an HTTP header cannot carry, such as a line break")
    return Wan3(Fal(key))
