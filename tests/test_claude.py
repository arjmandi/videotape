"""Claude as the second reader of a key's picture. tests/fixtures/recorded/claude/ holds 16 reads the paid screen test
cached, each a reply's text, its tokens and their price. No test sends a request: the HTTP layer is a stand-in that
answers each request with a reply it is given, or with a reply built from what the stand-in's own eye reads on the
picture the request carries, so a render through the reader needs no network and no key but a made-up one."""

import base64
import io
import json
import re
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

from conftest import RECORDED, copy_of, planned
from videotape import claude, dailies, frames, ledger, standin
from videotape.checks import Chart, Read, Spot
from videotape.claude import ClaudeJudge, ClaudeReader
from videotape.errors import CODES, ModelError, ScreenplayError
from videotape.frames import Box
from videotape.model import MODELS, Listing, estimate
from videotape.qwen import QwenEye
from videotape.standin import StandIn, StandInEye

KEY = "sk-ant-test-key-0123456789abcdef"
MESSAGES = "https://api.anthropic.com/v1/messages"
READS = sorted((RECORDED / "claude").glob("*.json"))
PROFILE = "7dd745d51d"
"""The recorded read of a profile, with a chart and a line drawn marked."""
BOOKING = "0d37ae9aa3"
"""The recorded read of a flight, with neither."""


def recorded(name: str) -> dict:
    """The recorded read whose cache name starts with name."""
    [path] = [path for path in READS if path.name.startswith(name)]
    return json.loads(path.read_text())


def message(text: str, stop: str = "end_turn", input_tokens: int = 2191, output_tokens: int = 900) -> dict:
    """A reply in the shape the API documents, with this text and these tokens. Written by hand, since the read cache
    keeps a reply's text and tokens and not the message they came in. Every read of the paid screen test billed 2,191
    input tokens, for a picture of as many tokens as the cafe's."""
    return {"id": "msg_01ClaudeRead000000000000", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "thinking", "thinking": "", "signature": "EqoBCkgIBxABGAIiQL0aZ2VuZXJpYy1zaWduYXR1cmU="},
                        {"type": "text", "text": text}],
            "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0}}


def replied(read: dict) -> dict:
    """The reply a recorded read came in."""
    return message(read["reply"], **read["tokens"])


class Claude:
    """Answers each request with the next answer it is given, or, given none, with what the stand-in's eye reads on
    the picture the request carries, which no paid run read. An answer that is an exception is raised."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.seen: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request) -> bytes:
        self.seen.append(request)
        answer = self.answers.pop(0) if self.answers else self.read(request)
        if isinstance(answer, Exception):
            raise answer
        return json.dumps(answer).encode()

    def bodies(self) -> list[dict]:
        return [json.loads(request.data) for request in self.seen]

    def read(self, request: urllib.request.Request) -> dict:
        frame = picture(json.loads(request.data))
        seen = StandInEye().see(frame)
        lines = [{"text": spot.text, "box": {"x": spot.box.x, "y": spot.box.y, "w": spot.box.w, "h": spot.box.h},
                  "control": spot.control, "marked": spot.box in seen.marked} for spot in seen.spots]
        # Each reply gets an id of its own, as the API gives, since the ledger holds a request's line once.
        return {**message(json.dumps({"lines": lines, "charts": []})), "id": f"msg_{uuid.uuid4().hex[:24]}"}


def picture(body: dict) -> frames.Frame:
    """The frame a request's image carries."""
    [image, _] = body["messages"][0]["content"]
    assert (image["type"], image["source"]["type"], image["source"]["media_type"]) == ("image", "base64", "image/png")
    return frames.png_frame(base64.b64decode(image["source"]["data"]))


class Purse:
    """Records what a reader reserves and settles."""

    def __init__(self):
        self.calls = []

    def reserve(self, usd: float) -> None:
        self.calls.append(("reserve", usd))

    def settle(self, line: dict | None, reserved: float) -> None:
        self.calls.append(("settle", line, reserved))


@pytest.fixture
def reader(tmp_path, monkeypatch):
    """A reader of the tape at tmp_path, with its key in the environment, that sends through the Claude it is given."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)

    def build(*answers) -> tuple[ClaudeReader, Claude]:
        hosted = Claude(*answers)
        return ClaudeReader(tmp_path / "tape", send=hosted), hosted
    return build


def a_frame(*rows: list[str]) -> frames.Frame:
    return standin.draw(list(rows))[0]


def test_the_request_sends_the_picture_as_png_before_a_prompt_that_holds_none_of_its_words_and_asks_for_json(reader):
    frame = a_frame(["Thanks"], ["One Espresso coming up."], ["Done"])
    made, hosted = reader(replied(recorded(BOOKING)))
    made.see(frame, Purse())
    [request] = hosted.seen
    assert (request.get_method(), request.full_url) == ("POST", MESSAGES)
    assert (request.get_header("X-api-key"), request.get_header("Anthropic-version")) == (KEY, "2026-10-21")
    [body] = hosted.bodies()
    assert set(body) == {"model", "max_tokens", "output_config", "messages"}
    assert (body["model"], body["max_tokens"], body["output_config"]["effort"]) == ("claude-opus-5-5", claude.MAX_TOKENS,
                                                                                    "medium")
    schema = body["output_config"]["format"]
    assert schema["type"] == "json_schema" and set(schema["schema"]["properties"]) == {"lines", "charts"}
    assert all(found["additionalProperties"] is False for found in objects(schema["schema"]))
    assert picture(body) == frame
    [_, text] = body["messages"][0]["content"]
    assert text["type"] == "text" and "1280 by 704" in text["text"]
    for words in ("Thanks", "Espresso", "Done", "Corner"):
        assert words not in text["text"]
    for asked in ("exactly", "box", "control", "marked", "chart", "title", "label", "value"):
        assert asked in text["text"]


def objects(schema: dict) -> list[dict]:
    """Every object schema inside a schema."""
    found = [schema] if schema.get("type") == "object" else []
    for inner in (*schema.get("properties", {}).values(), *([schema["items"]] if "items" in schema else [])):
        found += objects(inner)
    return found


def test_the_reply_parses_into_a_read_with_every_line_its_box_the_controls_the_marks_and_each_chart(reader):
    made, _ = reader(replied(recorded(PROFILE)))
    seen = made.see(a_frame(["Profile"]), Purse())
    assert seen.reader == "claude-opus-5-5"
    assert seen.spots[:3] == (Spot("ra", Box(140, 0, 60, 40), False),
                              Spot("Silver member, 48,250 miles", Box(536, 113, 235, 112), False),
                              Spot("Miles flown in 2026", Box(71, 143, 209, 62), False))
    assert [spot.text for spot in seen.spots] == [
        "ra", "Silver member, 48,250 miles", "Miles flown in 2026", "Jan", "679", "6,530", "Jun", "Home", "Trips",
        "Profile", "Jul", "11,326", "15,018", "Sep", "Nov", "Oct", "15,355", "15,355", "Oct", "15,355", "Nov"]
    assert [spot.text for spot in seen.spots if spot.control] == ["Home", "Trips", "Profile"]
    assert seen.marked == (Box(749, 268, 196, 147),)
    assert seen.charts == (Chart("Miles flown in 2026", ("Oct", "15,355", "15,355", "Nov"),
                                 (4697.0, 5270.0, 5805.0, 6530.0)),)


def test_a_reply_without_a_chart_or_a_mark_is_an_empty_report_not_a_missing_one(reader):
    made, _ = reader(replied(recorded(BOOKING)))
    seen = made.see(a_frame(["Book for $22"]), Purse())
    assert (seen.spots[0], len(seen.spots), seen.marked, seen.charts) == (
        Spot("Book for $22", Box(1000, 0, 280, 90), True), 5, (), ())


@pytest.mark.parametrize("path", READS, ids=lambda path: path.name[:10])
def test_each_reply_of_the_paid_run_reads_every_line_and_is_cached_as_the_paid_run_cached_it(reader, tmp_path, path):
    read = json.loads(path.read_text())
    made, _ = reader(replied(read))
    assert len(made.see(a_frame(["Thanks"]), Purse()).spots) == len(json.loads(read["reply"])["lines"])
    [looked] = (tmp_path / "tape" / "looks").iterdir()
    assert json.loads(looked.read_text()) == read


def test_a_box_past_the_pictures_edge_is_kept_within_it_and_an_empty_line_is_left_out(reader):
    """Written by hand: no reply of the paid run put a box past its picture or gave a line with no words."""
    text = json.dumps({"lines": [{"text": " Done ", "box": {"x": 1270, "y": 700, "w": 30, "h": 10}, "control": True,
                                  "marked": False}, {"text": "  ", "box": {"x": 0, "y": 0, "w": 5, "h": 5},
                                                     "control": False, "marked": False}], "charts": []})
    made, _ = reader(message(text))
    assert made.see(a_frame(["Done"]), Purse()).spots == (Spot("Done", Box(1270, 700, 10, 4), True),)


def test_a_read_is_cached_in_the_tape_by_the_pictures_hash_so_a_render_run_again_pays_nothing(reader, tmp_path):
    frame, other = a_frame(["Thanks"]), a_frame(["Done"])
    made, hosted = reader(replied(recorded(PROFILE)), replied(recorded(BOOKING)))
    first = made.see(frame, Purse())
    assert made.see(frame, Purse()) == first and len(hosted.seen) == 1
    [cached] = list((tmp_path / "tape" / "looks").iterdir())
    assert json.loads(cached.read_text()) == recorded(PROFILE)
    assert len(made.see(other, Purse()).spots) == 5 and len(hosted.seen) == 2
    again, _ = reader()
    assert again.see(frame, Purse()) == first


def test_a_paid_read_reserves_its_most_cost_before_it_is_sent_and_settles_its_bill_after(reader):
    frame, profile = a_frame(["Thanks"]), recorded(PROFILE)
    made, hosted = reader(replied(profile))
    purse = Purse()
    made.see(frame, purse)
    most = claude.estimate(1280, 704)
    [(reserved, held), (settled, line, released)] = [(call[0], call[1]) if len(call) == 2 else call for call in purse.calls]
    assert (reserved, held, settled, released) == ("reserve", most, "settle", most)
    assert {key: line[key] for key in ("kind", "model", "request_id", "tokens", "usd")} == {
        "kind": "read", "model": "claude-opus-5-5", "request_id": "msg_01ClaudeRead000000000000",
        "tokens": profile["tokens"], "usd": profile["usd"]}
    assert line["at"].endswith("+00:00")
    assert made.see(frame, purse).spots and purse.calls[2:] == []


def test_the_most_a_read_costs_is_the_pictures_tokens_and_the_prompts_at_the_input_price_plus_every_output_token():
    # platform.claude.com/docs/en/build-with-claude/vision, read 2026-11-15: an image costs ceil(w / 28) * ceil(h / 28)
    # tokens, so a 1280x704 picture is 46 * 26 = 1,196.
    image = 1196 * 4.00 / 1_000_000
    # A 1000x100 picture is 36 * 4 tokens, and its prompt names its size in as many digits, so the prompts cost the same.
    assert claude.estimate(1280, 704) - claude.estimate(1000, 100) == pytest.approx((1196 - 144) * 4.00 / 1_000_000)
    output = claude.MAX_TOKENS * 20.00 / 1_000_000
    assert 0 < claude.estimate(1280, 704) - (output + image) < 0.005
    assert 0.15 < claude.estimate(1280, 704) < 0.19


def test_the_most_a_read_costs_covers_the_input_the_paid_run_was_billed_with_every_output_token_a_read_may_take():
    """The paid screen test's reads are of 1280x720 pictures: their boxes reach x 1280 and y 720, and none passes."""
    billed = {json.loads(path.read_text())["tokens"]["input_tokens"] for path in READS}
    assert billed == {2191}
    assert claude.price({"input_tokens": 2191, "output_tokens": claude.MAX_TOKENS}) <= claude.estimate(1280, 720)


def test_every_model_but_the_stand_in_reads_with_qwen_and_claude_and_the_stand_in_with_its_own_reader():
    assert {name: listing.readers for name, listing in MODELS.items()} == {
        "stand-in": (StandInEye,),
        "wan2.2-5b": (QwenEye, ClaudeReader),
        "wan3.0": (QwenEye, ClaudeReader),
        "minimax-h3": (QwenEye, ClaudeReader),
        "gemini-omni-flash-1.2": (QwenEye, ClaudeReader),
    }
    assert (ClaudeReader.name, ClaudeReader.key, ClaudeReader.paid) == ("claude-opus-5-5", "ANTHROPIC_API_KEY", True)
    for name in ("wan3.0", "minimax-h3", "gemini-omni-flash-1.2"):
        assert MODELS[name].keys(name) == ((name, "FAL_KEY"), (f"{name}'s reader claude-opus-5-5", "ANTHROPIC_API_KEY"))
    assert MODELS["wan2.2-5b"].keys("wan2.2-5b") == (("wan2.2-5b's reader claude-opus-5-5", "ANTHROPIC_API_KEY"),)
    assert MODELS["stand-in"].keys("stand-in") == ()
    assert estimate("wan3.0", MODELS["wan3.0"], 160, 58, 4) == (
        "wan3.0: 160 shots, 160 to 640 calls, $80.00 to $320.00 at $0.10/s, and 58 to 232 reads by claude-opus-5-5, "
        f"at most ${58 * claude.estimate(1280, 704):.2f} to ${232 * claude.estimate(1280, 704):.2f}")
    assert estimate("stand-in", MODELS["stand-in"], 160, 58, 4) == "stand-in: 160 shots, 160 to 640 calls, free"


@pytest.fixture
def read_by_claude(monkeypatch):
    """The stand-in, read by its own eye and by Claude, who answers from the stand-in's eye through a fake network."""
    hosted = Claude()
    monkeypatch.setattr(claude, "_urlopen", hosted)
    clean = lambda mode, prompt, seed: standin.Flaw.NONE
    monkeypatch.setitem(MODELS, "stand-in", Listing(lambda: StandIn(flaw=clean), (StandInEye, ClaudeReader), limit=8,
                                                     kind=StandIn))
    return hosted


def test_a_render_pays_for_each_keys_read_under_the_cap_and_writes_each_to_the_ledger(tmp_path, cli, capsys, monkeypatch,
                                                                                    read_by_claude):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "render", "--story", "chalk", "--takes", "1", "--cap-usd", "2") == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == ("stand-in: 11 shots, 11 calls, free, and 5 reads by claude-opus-5-5, at most "
                                   f"${5 * claude.estimate(1280, 704):.2f}, cap $2.00, $0.00 spent")
    assert len(read_by_claude.seen) == 5
    lines = [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines()]
    reads = [line for line in lines if line["kind"] == "read"]
    assert sorted(line["shot"] for line in reads) == sorted(key.title for key in planned(directory).keys)
    assert all((line["tape"], line["seed"], line["model"], line["tokens"], line["usd"]) == (
        "tapes/chalk", 1, "claude-opus-5-5", {"input_tokens": 2191, "output_tokens": 900}, 0.026764) for line in reads)
    totals = ledger.of(directory, directory / "tapes" / "chalk").totals()
    assert (totals["takes"], totals["reads"], totals["usd"]) == (11, 5, 0.13)
    record = dailies.read(directory / "tapes" / "chalk")
    assert record["checks"] == "stand-in and claude-opus-5-5" and record["ledger"] == totals
    assert [reading["reader"] for reading in record["keys"][0]["items"][2]["readings"]] == ["stand-in", "claude-opus-5-5"]
    assert "$0.13" in out.splitlines()[-1]
    assert cli(directory, "render", "--story", "chalk", "--takes", "1", "--cap-usd", "2") == 0
    assert len(read_by_claude.seen) == 5 and KEY not in out


def test_a_read_that_would_pass_the_cap_is_vt402_before_it_is_sent_and_no_cap_does_not_start(tmp_path, cli, capsys,
                                                                                             monkeypatch, read_by_claude):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "render", "--story", "chalk", "--takes", "1", "--cap-usd", "0.10") == 1
    err = capsys.readouterr().err
    assert err.startswith("error VT402 key ") and f"at the listed price of ${claude.estimate(1280, 704):.2f} a call" in err
    assert read_by_claude.seen == [] and '"read"' not in (directory / "ledger.jsonl").read_text()
    assert cli(directory, "render", "--story", "chalk", "--takes", "1") == 1
    assert capsys.readouterr().err.startswith("error VT402 before the first call: claude-opus-5-5 bills per call, and no "
                                              "cap is set\nnext: set the most this render may spend, as in ")


def test_a_missing_key_stops_the_render_before_any_call_as_vt104_and_env_supplies_it(tmp_path, cli, capsys, monkeypatch,
                                                                                   read_by_claude):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "render", "--story", "chalk", "--takes", "1", "--cap-usd", "2") == 1
    assert capsys.readouterr().err == (
        "error VT104 .env: claude-opus-5-5, a reader of this model's eye, needs ANTHROPIC_API_KEY, and it is not in the "
        "environment or .env\nfix: copy .env.example to .env and set ANTHROPIC_API_KEY there, or export it\n")
    assert read_by_claude.seen == [] and not (directory / "tapes").exists()
    (directory / ".env").write_text(f"ANTHROPIC_API_KEY={KEY}\n")
    assert cli(directory, "render", "--story", "chalk", "--takes", "1", "--cap-usd", "2") == 0
    assert [request.get_header("X-api-key") for request in read_by_claude.seen] == [KEY] * 5


def test_a_key_an_http_header_cannot_carry_is_vt104_too(tmp_path, cli, capsys, monkeypatch, read_by_claude):
    monkeypatch.setenv("ANTHROPIC_API_KEY", f"{KEY}\nx")
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "render", "--story", "chalk", "--takes", "1", "--cap-usd", "2") == 1
    assert capsys.readouterr().err == ("error VT104 .env: ANTHROPIC_API_KEY holds a character an HTTP header cannot "
                                       "carry, such as a line break\nfix: set ANTHROPIC_API_KEY to the API key alone, in "
                                       ".env or the environment\n")
    assert read_by_claude.seen == []


def test_a_reply_that_is_not_whole_stops_the_render_and_its_cost_still_reaches_the_ledger(tmp_path, cli, capsys,
                                                                                          monkeypatch, read_by_claude):
    """Written by hand: no read of the paid run was cut short."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    read_by_claude.answers.append(message('{"lines": [', stop="max_tokens", output_tokens=8192))
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "render", "--story", "chalk", "--takes", "1", "--cap-usd", "2") == 1
    assert re.fullmatch(r"error VT401 key .+ take 1: claude-opus-5-5's read stopped with 'max_tokens' after 11 "
                        r"characters, not a whole read; it cost \$0\.1726\nnext: run the render again, which resumes and "
                        r"reads this take again:\nvideotape render --story chalk --takes 1 --cap-usd 2\.00\n",
                        capsys.readouterr().err)
    reads = [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines() if '"read"' in line]
    [line] = [line for line in reads if line["tokens"]["output_tokens"] == 8192]
    assert line["usd"] == 0.172604
    # The reads that came back whole are cached; the one cut short is not, so the next render asks again.
    assert len(list((directory / "tapes" / "chalk" / "looks").iterdir())) == len(reads) - 1


def test_the_key_never_appears_in_an_error_and_a_refused_request_is_not_in_the_ledger(tmp_path, cli, capsys, monkeypatch,
                                                                                      read_by_claude):
    """Written by hand: no read of the paid run failed."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    refused = urllib.error.HTTPError(MESSAGES, 401, "Unauthorized", {},
                                     io.BytesIO(f'{{"error": {{"message": "invalid x-api-key {KEY}"}}}}'.encode()))
    read_by_claude.answers.append(refused)
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "render", "--story", "chalk", "--takes", "1", "--cap-usd", "2") == 1
    err = capsys.readouterr().err
    assert re.match(r"error VT401 key .+ take 1: claude-opus-5-5's read failed with HTTP 401: ", err)
    assert "<ANTHROPIC_API_KEY>" in err
    assert KEY not in err
    # The other keys' reads went on at once and were billed; the refused one has no line.
    reads = [line for line in (directory / "ledger.jsonl").read_text().splitlines() if '"read"' in line]
    assert len(reads) == len(read_by_claude.seen) - 1


def test_doctor_checks_every_api_key_the_model_and_its_readers_need(tmp_path, cli, capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setitem(MODELS, "stand-in", Listing(StandIn, (StandInEye, ClaudeReader), limit=8, kind=StandIn))
    directory = copy_of("cafe", tmp_path)
    cli(directory, "doctor")
    lines = capsys.readouterr().out.splitlines()
    assert lines[3:6] == ["fail VT104 stand-in's reader claude-opus-5-5 needs ANTHROPIC_API_KEY, and it is not in the "
                          "environment or .env", "  fix: copy .env.example to .env and set ANTHROPIC_API_KEY there, or "
                          "export it", "ok   VT105 stand-in's eye needs no GPU"]
    (directory / ".env").write_text(f"ANTHROPIC_API_KEY={KEY}\n")
    cli(directory, "doctor")
    assert capsys.readouterr().out.splitlines()[3] == "ok   VT104 ANTHROPIC_API_KEY is set, for stand-in's reader claude-opus-5-5"
    assert CODES["VT104"].title == "an API key the project's model or one of its readers needs is not set"


# The judge.

def sampled(first: list[str], last: list[str]) -> list[tuple[int, frames.Frame]]:
    """Eight frames across a made-up move: the stand-in's crossfade from one drawn picture to another, as a take's
    frames are sampled."""
    with tempfile.TemporaryDirectory() as scratch:
        start, end, clip = (Path(scratch) / name for name in ("start.png", "end.png", "clip.mp4"))
        frames.write_png(a_frame(first), start)
        frames.write_png(a_frame(last), end)
        frames.crossfade(start, end, clip)
        return frames.sampled(clip, claude.FRAMES)


def judgment(*overlaid: bool, seen: str = "a screen") -> str:
    return json.dumps({"frames": [{"overlaid": flag, "seen": seen} for flag in overlaid]})


@pytest.fixture
def judge(tmp_path, monkeypatch):
    """A judge of the tape at tmp_path, with its key in the environment, that sends through the Claude it is given."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)

    def build(*answers) -> tuple[ClaudeJudge, Claude]:
        hosted = Claude(*answers)
        return ClaudeJudge(tmp_path / "tape", send=hosted), hosted
    return build


def test_a_judgment_sends_every_frame_as_png_in_order_before_a_prompt_that_asks_about_each_and_parses_the_answers(judge):
    taken = sampled(["Thanks"], ["Done"])
    made, hosted = judge(message(judgment(False, False, True, True, False, False, False, False, seen="a blend")))
    verdict = made.judge(taken, Purse())
    [body] = hosted.bodies()
    assert set(body) == {"model", "max_tokens", "output_config", "messages"}
    assert (body["model"], body["max_tokens"], body["output_config"]["effort"]) == ("claude-opus-5-5", 4096, "medium")
    schema = body["output_config"]["format"]
    assert schema["type"] == "json_schema" and set(schema["schema"]["properties"]) == {"frames"}
    assert all(found["additionalProperties"] is False for found in objects(schema["schema"]))
    *images, text = body["messages"][0]["content"]
    assert len(images) == 8 and all(image["type"] == "image" and image["source"]["media_type"] == "image/png" for image in images)
    assert [frames.png_frame(base64.b64decode(image["source"]["data"])) for image in images] == [picture for _, picture in taken]
    assert text["type"] == "text" and "8 frames" in text["text"] and "1280 by 704" in text["text"]
    for asked in ("overlaid", "dissolve", "order", "first", "last"):
        assert asked in text["text"]
    assert verdict.judge == "claude-opus-5-5" and verdict.at == (0, 3, 7, 10, 13, 16, 20, 23)
    assert verdict.overlaid == (False, False, True, True, False, False, False, False) and set(verdict.seen) == {"a blend"}
    assert not verdict.passed and verdict.item().about == "frames 7 and 10"


def test_a_judgment_is_cached_in_the_tape_by_its_frames_so_a_run_again_pays_nothing(judge, tmp_path):
    taken, other = sampled(["Thanks"], ["Done"]), sampled(["Done"], ["Thanks"])
    made, hosted = judge(message(judgment(*[False] * 8)), message(judgment(*[True] * 8)))
    first = made.judge(taken, Purse())
    assert made.judge(taken, Purse()) == first and len(hosted.seen) == 1 and first.passed
    [looked] = list((tmp_path / "tape" / "looks").iterdir())
    assert json.loads(looked.read_text())["reply"] == judgment(*[False] * 8)
    assert made.recorded(taken) == json.loads(looked.read_text()) and made.recorded(other) is None
    assert not made.judge(other, Purse()).passed and len(hosted.seen) == 2
    again, _ = judge()
    assert again.judge(taken, Purse()) == first


def test_a_paid_judgment_reserves_its_most_cost_before_it_is_sent_and_settles_its_bill_after_like_a_read(judge):
    taken = sampled(["Thanks"], ["Done"])
    made, _ = judge(message(judgment(*[False] * 8), input_tokens=9900, output_tokens=700))
    purse = Purse()
    made.judge(taken, purse)
    most = claude.judge_estimate(1280, 704)
    [(reserved, held), (settled, line, released)] = [(call[0], call[1]) if len(call) == 2 else call for call in purse.calls]
    assert (reserved, held, settled, released) == ("reserve", most, "settle", most)
    assert {key: line[key] for key in ("kind", "model", "request_id", "tokens", "usd")} == {
        "kind": "judgment", "model": "claude-opus-5-5", "request_id": "msg_01ClaudeRead000000000000",
        "tokens": {"input_tokens": 9900, "output_tokens": 700}, "usd": 0.0536}
    assert made.judge(taken, purse).passed and purse.calls[2:] == []
    assert ClaudeJudge.most(1280, 704) == most and 0.11 < most < 0.14
    image = 1196 * 4.00 / 1_000_000
    assert claude.judge_estimate(1280, 704) - claude.judge_estimate(1280, 704, 4) == pytest.approx(4 * image)


def test_a_reply_that_does_not_answer_for_every_frame_is_no_judgment_and_is_not_cached(judge, tmp_path):
    taken = sampled(["Thanks"], ["Done"])
    made, hosted = judge(message(judgment(*[False] * 7)), message('{"frames": "none"}'), message(judgment(*[False] * 8)))
    for _ in range(2):
        with pytest.raises(ModelError, match="answered with something other than a judgment of 8 frames"):
            made.judge(taken, Purse())
    assert not (tmp_path / "tape" / "looks").exists()
    assert made.judge(taken, Purse()).passed and len(hosted.seen) == 3


def test_the_judge_needs_the_same_key_as_the_reader_and_says_what_needs_it(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ScreenplayError) as refused:
        ClaudeJudge(tmp_path)
    assert (refused.value.code, refused.value.message) == (
        "VT104", "claude-opus-5-5, the judge of this model's moves, needs ANTHROPIC_API_KEY, and it is not in the "
                 "environment or .env")
    assert (ClaudeJudge.name, ClaudeJudge.key, ClaudeJudge.paid) == ("claude-opus-5-5", "ANTHROPIC_API_KEY", True)


def test_what_a_judgment_answers_is_hashed_so_a_recorded_answer_holds_only_for_the_question_it_answered(monkeypatch):
    before = claude.asked()
    assert re.fullmatch(r"[0-9a-f]{64}", before) and claude.asked() == before
    monkeypatch.setattr(claude, "JUDGE_PROMPT", claude.JUDGE_PROMPT + " Be brief.")
    assert claude.asked() != before


def test_the_ledger_counts_judgments_with_the_reads_and_the_takes(tmp_path):
    book = ledger.Ledger(tmp_path / "ledger.jsonl", "tapes/x")
    book.append({"kind": "take", "seconds": 2.0, "usd": 0.44})
    book.append({"kind": "read", "seconds": 0.0, "usd": 0.03})
    book.append({"kind": "judgment", "seconds": 0.0, "usd": 0.05})
    book.append({"kind": "take", "seconds": 1.0, "usd": None})
    assert book.totals() == {"takes": 2, "gpu_seconds": 3.0, "pods": 0, "pod_hours": 0.0, "reads": 1, "judgments": 1,
                             "usd": 0.52}
