"""Claude as the second reader of a key's picture. tests/fixtures/recorded/claude/ holds 16 reads the paid screen test
cached, each a reply's text, its tokens and their price. No test sends a request: the HTTP layer is a stand-in that
answers each request with a reply it is given, or with a reply built from what the stand-in's own eye reads on the
picture the request carries, so a render through the reader needs no network and no key but a made-up one."""

import base64
import io
import json
import re
import urllib.error
import urllib.request
import uuid

import pytest

from conftest import RECORDED, copy_of
from videotape import claude, dailies, frames, ledger, standin
from videotape.checks import Chart, Read, Spot
from videotape.claude import ClaudeReader
from videotape.errors import CODES
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


def message(text: str, stop: str = "end_turn", input_tokens: int = 1800, output_tokens: int = 900) -> dict:
    """A reply in the shape the API documents, with this text and these tokens. Written by hand, since the read cache
    keeps a reply's text and tokens and not the message they came in."""
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


def no_network(request):
    raise AssertionError(f"a test reached for the network: {request.full_url}")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No test here sends anything: what stands in for the network answers every request."""
    monkeypatch.setattr(urllib.request, "urlopen", no_network)


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
    assert sorted(line["shot"] for line in reads) == sorted(f"key {state}" for state in (
        "menu()", "order(Espresso)", "order(Latte)", "thanks(Espresso)", "thanks(Latte)"))
    assert all((line["tape"], line["seed"], line["model"], line["tokens"], line["usd"]) == (
        "tapes/chalk", 1, "claude-opus-5-5", {"input_tokens": 1800, "output_tokens": 900}, 0.0252) for line in reads)
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
                        r"characters, not a whole read; it cost \$0\.1710\nnext: run the render again, which resumes and "
                        r"reads this take again:\nvideotape render --story chalk --takes 1 --cap-usd 2\.00\n",
                        capsys.readouterr().err)
    reads = [json.loads(line) for line in (directory / "ledger.jsonl").read_text().splitlines() if '"read"' in line]
    [line] = [line for line in reads if line["tokens"]["output_tokens"] == 8192]
    assert line["usd"] == 0.17104
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
                          "export it", "ok   VT105 stand-in's checks need no GPU"]
    (directory / ".env").write_text(f"ANTHROPIC_API_KEY={KEY}\n")
    cli(directory, "doctor")
    assert capsys.readouterr().out.splitlines()[3] == "ok   VT104 ANTHROPIC_API_KEY is set, for stand-in's reader claude-opus-5-5"
    assert CODES["VT104"].title == "an API key the project's model or one of its readers needs is not set"
