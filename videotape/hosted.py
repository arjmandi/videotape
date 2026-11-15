"""Video models fal hosts, which draw every pixel: text-to-video draws each state's key, and image-to-video draws each
move from the kept key it starts on to the kept key it lands on. One adapter films them all, and a FalModel holds what
differs between them. Their takes are only compared with the 5B's, never trained on."""

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from videotape.atomic import write_atomically
from videotape.fal import Fal, FalError, Price, Receipt
from videotape.plan import Mode


@dataclass(frozen=True)
class FalModel:
    """A model fal hosts: the endpoint of each mode, what a request of each mode sends beyond its prompt, seed, images
    and duration, the field that takes a move's first frame, whether fal takes a seed, the longest prompt it takes in
    characters, and its price, whose seconds are the duration every request asks for. A move's last frame goes in
    end_image_url on every model here."""

    name: str
    endpoints: dict[Mode, str]
    fields: dict[Mode, dict]
    start_image: str
    seeded: bool
    prompt_characters: int
    price: Price

    def settings(self, mode: Mode) -> dict:
        """Everything a request depends on beyond its prompt, seed and images, which the take cache already hashes."""
        return {"endpoint": self.endpoints[mode], **self.fields[mode], "duration": self.price.seconds}

    def request(self, mode: Mode, prompt: str, seed: int, start: Path | None = None,
                end: Path | None = None) -> "FalRequest":
        """A key is text-to-video from its prompt. A move is image-to-video pinned to the two key images it joins."""
        images = {self.start_image: _data_uri(start), "end_image_url": _data_uri(end)} \
            if mode is Mode.FIRST_AND_LAST_FRAME else {}
        settings = self.settings(mode)
        endpoint = settings.pop("endpoint")
        return FalRequest(endpoint, {"prompt": prompt, **settings, **({"seed": seed} if self.seeded else {}), **images})

    def bill(self, response: dict) -> tuple[str, Receipt]:
        """The video's url and the receipt from fal's answers to one call, read without the network."""
        submitted, result = response["submitted"], response["result"]
        try:
            url, duration = result["video"]["url"], float(result["duration"])
        except (KeyError, TypeError, ValueError):
            raise FalError(f"request {submitted['request_id']} answered without video.url and duration: {result}") from None
        return url, Receipt(submitted["request_id"], duration, round(duration * self.price.usd_per_second, 4), response)


@dataclass(frozen=True)
class FalRequest:
    endpoint: str
    arguments: dict


# Five seconds without sound, like the 5B's clips. fal's defaults are 1080p, an adaptive aspect ratio, audio on and
# prompt expansion on, which rewrites the prompt, so each is set to give both models the same words at one size.
WAN3_FIELDS = {"resolution": "720p", "aspect_ratio": "16:9", "audio": False, "enable_prompt_expansion": False}
WAN3 = FalModel(
    "wan3.0",
    # fal.ai/api/openapi/queue/openapi.json?endpoint_id=<endpoint>, read 2026-11-10: Wan30TextToVideoInput and
    # Wan30ImageToVideoInput, whose start_image_url is the "First frame of the generated video" and end_image_url the
    # "Last frame of the generated video".
    {Mode.TEXT_TO_VIDEO: "alibaba/wan-3.0/text-to-video", Mode.FIRST_AND_LAST_FRAME: "alibaba/wan-3.0/image-to-video"},
    {Mode.TEXT_TO_VIDEO: WAN3_FIELDS, Mode.FIRST_AND_LAST_FRAME: WAN3_FIELDS},
    "start_image_url",
    seeded=True,
    # The same two schemas, read 2026-11-14: each gives its prompt a maxLength of 20000 characters.
    prompt_characters=20_000,
    # Both endpoints' model pages on 2026-11-10: "$0.05 480p, $0.10 720p, or $0.20 1080p" for every second generated.
    price=Price(usd_per_second=0.10, seconds=5),
)

FAL_MODELS = (WAN3,)


class RecordedFailure(FalError):
    """A recorded request's poll or download failed. A render never submits it again on its own, so the error names
    the record, which deleting lets a render submit a new, paid take."""

    def __init__(self, message: str, record: Path) -> None:
        super().__init__(message)
        self.record = record


def _data_uri(png: Path) -> str:
    # fal's API page for each image-to-video endpoint: "You can pass a Base64 data URI as a file input."
    return "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()


class OnFal:
    """A FalModel with fal's queue to film on."""

    device = "fal"

    def __init__(self, model: FalModel, fal: Fal):
        self.model, self.fal = model, fal
        self.name, self.price = model.name, model.price

    def settings(self, mode: Mode) -> dict:
        return self.model.settings(mode)

    def text_to_video(self, prompt: str, seed: int, out: Path) -> Receipt:
        return self._film(self.model.request(Mode.TEXT_TO_VIDEO, prompt, seed), out)

    def first_last_frame(self, prompt: str, start: Path, end: Path, seed: int, out: Path) -> Receipt:
        return self._film(self.model.request(Mode.FIRST_AND_LAST_FRAME, prompt, seed, start, end), out)

    def download_again(self, out: Path) -> Receipt | None:
        record = request_record(out)
        if not record.exists():
            return None
        return self._fetch(record, json.loads(record.read_text()), out)

    def _film(self, built: FalRequest, out: Path) -> Receipt:
        """One take, submitted once. fal's answer to the submit is recorded beside the take before the wait, so a
        render that dies between submitting and downloading polls and downloads that request on resume instead of
        paying for it again. The record holds the endpoint, the request id and its urls, never the key."""
        if (receipt := self.download_again(out)) is not None:
            return receipt
        record = request_record(out)
        submitted = {"endpoint": built.endpoint, **self.fal.submit(built.endpoint, built.arguments)}
        write_atomically(record, lambda partial: partial.write_text(json.dumps(submitted, indent=2) + "\n"))
        return self._fetch(record, submitted, out)

    def _fetch(self, record: Path, submitted: dict, out: Path) -> Receipt:
        try:
            url, receipt = self.model.bill(self.fal.wait(submitted["endpoint"], submitted))
            self.fal.download(url, out)
        except FalError as error:
            raise RecordedFailure(str(error), record) from None
        return receipt


def request_record(out: Path) -> Path:
    """Where a take's submitted request is recorded: beside the take, under the take's name. A render films a take
    into <name>.partial.mp4 and moves it into place as <name>.mp4, so the record goes by the name before the first dot."""
    return out.with_name(f"{out.name.partition('.')[0]}.request.json")


def from_environment(model: FalModel) -> OnFal:
    if not (key := os.environ.get("FAL_KEY", "").strip()):
        raise FalError(f"{model.name} needs FAL_KEY in the environment or the project's .env")
    # http.client rejects a header with a control character by quoting the whole header, key and all, in its error.
    if not key.isprintable():
        raise FalError("FAL_KEY holds a character an HTTP header cannot carry, such as a line break")
    return OnFal(model, Fal(key))
