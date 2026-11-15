"""tests/fixtures/words-test.json holds a count and an answer written by hand in the shapes the API documents. No test
sends a request: the HTTP layer is a stand-in that answers each request with the next recorded response."""

import importlib.machinery
import importlib.util
import io
import json
import re
import sys
import urllib.error
import urllib.request

import pytest

from conftest import FIXTURES
from videotape import errors
from videotape.cli import main

ROOT = FIXTURES.parent.parent
KEY = "sk-ant-test-key-0123456789abcdef"
COUNT = "https://api.anthropic.com/v1/messages/count_tokens"
MESSAGES = "https://api.anthropic.com/v1/messages"


@pytest.fixture(scope="module")
def script():
    loader = importlib.machinery.SourceFileLoader("words_test", str(ROOT / "scripts" / "words-test"))
    spec = importlib.util.spec_from_loader("words_test", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def recorded() -> dict:
    return json.loads((FIXTURES / "words-test.json").read_text())


class Claude:
    """Answers each request with the next recorded response. An answer that is an exception is raised."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.seen: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request) -> bytes:
        self.seen.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return json.dumps(answer).encode()

    def bodies(self) -> list[dict]:
        return [json.loads(request.data) for request in self.seen]


@pytest.fixture
def run(script, tmp_path, monkeypatch, capsys):
    """Run the script with the recorded answers, its key in the environment, and its report, ledger and .env in a
    temporary folder."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    for name, file in (("REPORT", "words-test.md"), ("LEDGER", "ledger.jsonl"), ("ENV", ".env")):
        monkeypatch.setattr(script, name, tmp_path / file)

    def run(*answers, arguments=("--cap-usd", "1")):
        claude = Claude(*answers)
        code = script.main(list(arguments), send=claude)
        return code, claude, capsys.readouterr()
    return run


def subcommands(capsys) -> list[str]:
    with pytest.raises(SystemExit):
        main(["--help"])
    return re.search(r"\{([\w,-]+)\}", capsys.readouterr().out)[1].split(",")


def test_without_a_key_it_says_so_and_sends_nothing(run, script, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    code, claude, said = run(recorded()["count"], recorded()["answer"])
    assert (code, claude.seen, said.out) == (1, [], "")
    assert said.err == f"error: ANTHROPIC_API_KEY is not set, in the environment or in {tmp_path / '.env'}\n"
    assert not (tmp_path / "words-test.md").exists() and not (tmp_path / "ledger.jsonl").exists()


def test_the_key_comes_from_the_repositorys_env_file_when_the_environment_lacks_it(run, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    (tmp_path / ".env").write_text(f"# for scripts/words-test\nANTHROPIC_API_KEY={KEY}\n")
    code, claude, _ = run(recorded()["count"], recorded()["answer"])
    assert code == 0
    assert [request.get_header("X-api-key") for request in claude.seen] == [KEY, KEY]


def test_without_a_cap_it_refuses_and_sends_nothing(run, tmp_path):
    code, claude, said = run(recorded()["count"], recorded()["answer"], arguments=())
    assert (code, claude.seen) == (1, [])
    assert said.err == "error: the words test makes a paid call; pass --cap-usd with the most it may spend\n"
    assert not (tmp_path / "ledger.jsonl").exists()


def test_an_estimate_over_the_cap_counts_the_tokens_for_free_and_sends_no_paid_call(run, tmp_path):
    code, claude, said = run(recorded()["count"], recorded()["answer"], arguments=("--cap-usd", "0.50"))
    assert code == 1
    assert [request.full_url for request in claude.seen] == [COUNT]
    assert said.out == "estimate  14,210 input tokens and at most 24,000 output tokens, at most $0.5368, cap $0.50\n"
    assert said.err == "error: the estimate of $0.5368 is not under the cap of $0.50, so nothing was sent\n"
    assert not (tmp_path / "words-test.md").exists() and not (tmp_path / "ledger.jsonl").exists()


def test_under_the_cap_it_counts_then_sends_the_words_every_help_text_and_every_error_to_claude_opus(run, capsys):
    code, claude, _ = run(recorded()["count"], recorded()["answer"])
    assert code == 0
    assert [(request.get_method(), request.full_url) for request in claude.seen] == [("POST", COUNT), ("POST", MESSAGES)]
    assert all((request.get_header("X-api-key"), request.get_header("Anthropic-version")) == (KEY, "2026-10-21")
               for request in claude.seen)
    count, call = claude.bodies()
    assert set(call) == {"model", "max_tokens", "output_config", "messages"}
    assert (call["model"], call["max_tokens"], call["output_config"]) == ("claude-opus-5-5", 24000, {"effort": "medium"})
    assert count == {"model": call["model"], "messages": call["messages"]}
    [message] = call["messages"]
    content = message["content"]
    words = (ROOT / "README.md").read_text().split("## The words Videotape uses\n", 1)[1].strip()
    assert f"<words>\n{words}\n</words>" in content
    for name in subcommands(capsys):
        assert f"usage: videotape {name} " in content
    assert "show this help message and exit" in content
    for code_, entry in errors.CODES.items():
        assert f"{code_}: {entry.title}" in content and entry.long in content
    assert re.search(r'^videotape/dailies\.py:\d+ ScreenplayError: "VT405" / "has no dailies.json, which every render '
                     r'writes" / f"render the story first, as in:\\n\{render\}"$', content, re.M)
    assert re.search(r'^videotape/doctor\.py:\d+ Check: "VT102" / ', content, re.M)
    assert re.search(r'^videotape/project\.py:\d+ wrong: f.screenplay is \{screenplay!r\}, not "module:app"', content,
                     re.M)


def test_the_answer_is_saved_with_the_model_tokens_and_cost_and_the_ledger_gets_one_line(run, tmp_path):
    code, _, said = run(recorded()["count"], recorded()["answer"])
    assert (code, said.err) == (0, "")
    spent = "claude-opus-5-5: 14,210 input tokens, 6,120 output tokens, $0.1792"
    assert said.out.splitlines() == [
        "estimate  14,210 input tokens and at most 24,000 output tokens, at most $0.5368, cap $1.00",
        f"call      {spent} -> {tmp_path / 'words-test.md'}"]
    saved = (tmp_path / "words-test.md").read_text()
    assert saved.startswith("# Words test\n\n`scripts/words-test` sent the words section of `README.md`")
    assert f"## The places\n\n{recorded()['answer']['content'][1]['text'].strip()}\n\n" in saved
    assert saved.endswith(f"## Tokens and cost\n\n- {spent}\n")
    [line] = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert {key: line[key] for key in ("kind", "model", "tokens", "usd")} == {
        "kind": "words-test", "model": "claude-opus-5-5", "tokens": {"input_tokens": 14210, "output_tokens": 6120},
        "usd": 0.17924}
    assert line["at"].endswith("+00:00")
    assert KEY not in said.out + saved + (tmp_path / "ledger.jsonl").read_text()


def test_the_ledger_keeps_the_lines_already_in_it(run, tmp_path):
    (tmp_path / "ledger.jsonl").write_text('{"kind": "take", "tape": "tapes/terminal", "usd": 0.5}\n')
    run(recorded()["count"], recorded()["answer"])
    assert [json.loads(line)["kind"] for line in (tmp_path / "ledger.jsonl").read_text().splitlines()] == [
        "take", "words-test"]


def test_record_writes_the_raw_response(run, tmp_path):
    run(recorded()["count"], recorded()["answer"], arguments=("--cap-usd", "1", "--record", str(tmp_path / "raw.json")))
    assert json.loads((tmp_path / "raw.json").read_text()) == recorded()["answer"]


@pytest.mark.parametrize("change, said", [
    ({"stop_reason": "refusal"}, "error: the call stopped with 'refusal' after "),
    ({"stop_reason": "max_tokens"}, "error: the call stopped with 'max_tokens' after "),
])
def test_an_answer_that_is_not_whole_fails_and_its_cost_still_reaches_the_ledger(run, tmp_path, change, said):
    code, _, printed = run(recorded()["count"], {**recorded()["answer"], **change})
    assert code == 1
    assert printed.err.startswith(said) and printed.err.endswith("not a whole answer; it cost $0.1792\n")
    assert json.loads((tmp_path / "ledger.jsonl").read_text())["usd"] == 0.17924
    assert not (tmp_path / "words-test.md").exists()


def test_the_key_never_appears_in_an_error(run, tmp_path):
    refused = urllib.error.HTTPError(COUNT, 401, "Unauthorized", {},
                                     io.BytesIO(f'{{"error": {{"message": "invalid x-api-key {KEY}"}}}}'.encode()))
    code, claude, said = run(refused)
    assert (code, said.out, len(claude.seen)) == (1, "", 1)
    assert said.err.startswith("error: the count failed with HTTP 401: ") and "<ANTHROPIC_API_KEY>" in said.err
    assert KEY not in said.err and not (tmp_path / "ledger.jsonl").exists()


def test_a_key_that_an_http_header_cannot_carry_is_refused_before_anything_is_sent(run, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", f"{KEY}\nx")
    code, claude, said = run(recorded()["count"], recorded()["answer"])
    assert (code, claude.seen) == (1, [])
    assert said.err == ("error: ANTHROPIC_API_KEY holds a character an HTTP header cannot carry, such as a line "
                        "break\n")


def test_a_readme_without_the_words_section_fails_before_anything_is_sent(run, script, tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("# Videotape\n\n## 1. Start a project\n")
    monkeypatch.setattr(script, "README", tmp_path / "README.md")
    code, claude, said = run(recorded()["count"], recorded()["answer"])
    assert (code, claude.seen) == (1, [])
    assert said.err == f'error: {tmp_path / "README.md"} has no section under "## The words Videotape uses"\n'
