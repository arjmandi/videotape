"""tests/fixtures/reader-test.json holds two responses written by hand in the shape the Messages API documents,
because the paid run has not happened yet. scripts/reader-test --record tests/fixtures/reader-test.json replaces
them with the real ones."""

import importlib.machinery
import importlib.util
import io
import json
import sys
import urllib.error
import urllib.request

import pytest

from conftest import CONTRAIL, FIXTURES

ROOT = CONTRAIL.parent.parent
KEY = "sk-ant-test-key-0123456789abcdef"
FEATURES = [line.split(". ", 1)[1] for line in (CONTRAIL / "README.md").read_text().splitlines() if line[:1].isdigit()]


@pytest.fixture(scope="module")
def script():
    loader = importlib.machinery.SourceFileLoader("reader_test", str(ROOT / "scripts" / "reader-test"))
    spec = importlib.util.spec_from_loader("reader_test", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def recorded() -> dict:
    return json.loads((FIXTURES / "reader-test.json").read_text())


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
def run(script, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setattr(script, "REPORT", tmp_path / "reader-test.md")

    def run(*answers, arguments=()):
        claude = Claude(*answers)
        return script.main(list(arguments), send=claude), claude, tmp_path / "reader-test.md"
    return run


def with_verdict(check: dict, number: int, yes: bool) -> dict:
    judged = json.loads(check["content"][1]["text"])
    judged[f"feature_{number}"]["yes"] = yes
    return {**check, "content": [check["content"][0], {"type": "text", "text": json.dumps(judged)}]}


def test_the_readme_lists_nine_features(script):
    assert script.features((CONTRAIL / "README.md").read_text()) == FEATURES
    assert len(FEATURES) == 9
    assert FEATURES[0].startswith("Home greets the traveler") and FEATURES[8].startswith("A search that matches no airport")


def test_the_read_sends_only_the_screenplay_to_claude_opus(run):
    code, claude, _ = run(recorded()["read"], recorded()["check"])
    assert code == 0
    read = claude.seen[0]
    assert (read.get_method(), read.full_url) == ("POST", "https://api.anthropic.com/v1/messages")
    assert (read.get_header("X-api-key"), read.get_header("Anthropic-version")) == (KEY, "2026-10-21")
    body = claude.bodies()[0]
    assert set(body) == {"model", "max_tokens", "output_config", "messages"}
    assert (body["model"], body["output_config"]) == ("claude-opus-5-5", {"effort": "medium"})
    [message] = body["messages"]
    assert message["role"] == "user"
    assert (CONTRAIL / "contrail" / "screenplay.py").read_text() in message["content"]
    for other in ("copy.py", "data.py"):
        assert (CONTRAIL / "contrail" / other).read_text().splitlines()[0] not in message["content"]
    assert not any(feature in message["content"] for feature in FEATURES)
    assert '"code": "SFO"' not in message["content"]


def test_the_check_sends_the_answer_and_every_feature_and_must_answer_yes_or_no_to_each(run):
    _, claude, _ = run(recorded()["read"], recorded()["check"])
    body = claude.bodies()[1]
    content = body["messages"][0]["content"]
    assert recorded()["read"]["content"][1]["text"] in content
    assert "\n".join(f"{number}. {feature}" for number, feature in enumerate(FEATURES, 1)) in content
    assert (CONTRAIL / "contrail" / "screenplay.py").read_text() not in content
    schema = body["output_config"]["format"]["schema"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert schema["required"] == [f"feature_{number}" for number in range(1, 10)] == list(schema["properties"])
    assert schema["additionalProperties"] is False
    assert all(verdict["properties"]["yes"] == {"type": "boolean"} and verdict["required"] == ["why", "yes"]
               for verdict in schema["properties"].values())


def test_nine_yeses_exit_zero_and_both_answers_are_saved_with_the_tokens_and_cost(run, capsys):
    code, _, report = run(recorded()["read"], recorded()["check"])
    out, err = capsys.readouterr()
    assert (code, err) == (0, "")
    assert out.splitlines()[:3] == [
        "read   claude-opus-5-5: 2,412 input tokens, 1,105 output tokens, $0.0317",
        "check  claude-opus-5-5: 1,890 input tokens, 520 output tokens, $0.0180",
        "total  $0.0497"]
    assert out.splitlines()[3:12] == [f"{number}. yes  {feature}" for number, feature in enumerate(FEATURES, 1)]
    assert out.splitlines()[12] == f"9 of 9 features stated -> {report}"
    saved = report.read_text()
    assert recorded()["read"]["content"][1]["text"] in saved
    assert "The answer states 9 of 9." in saved
    for number, feature in enumerate(FEATURES, 1):
        assert f"{number}. **Yes.** {feature}\n" in saved
    assert "The answer says one button books the flight and a confirmation code is shown." in saved
    assert "- total  $0.0497" in saved
    assert KEY not in out + saved


def test_one_no_exits_nonzero_and_says_which_feature(run, capsys):
    code, _, report = run(recorded()["read"], with_verdict(recorded()["check"], 3, False))
    out = capsys.readouterr().out
    assert code == 1
    assert f"3. no   {FEATURES[2]}" in out.splitlines() and f"4. yes  {FEATURES[3]}" in out.splitlines()
    assert out.splitlines()[-1] == f"8 of 9 features stated -> {report}"
    assert f"3. **No.** {FEATURES[2]}\n" in report.read_text() and "The answer states 8 of 9." in report.read_text()


def test_record_writes_both_raw_responses(run, tmp_path):
    out = tmp_path / "responses.json"
    run(recorded()["read"], recorded()["check"], arguments=("--record", str(out)))
    assert json.loads(out.read_text()) == recorded()


def test_without_a_key_it_says_so_and_sends_nothing(run, capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    code, claude, report = run(recorded()["read"], recorded()["check"])
    assert (code, claude.seen) == (2, [])
    assert capsys.readouterr() == ("", "error: ANTHROPIC_API_KEY is not set\n")
    assert not report.exists()


def test_the_key_never_appears_in_an_error(run, capsys):
    refused = urllib.error.HTTPError("https://api.anthropic.com/v1/messages", 401, "Unauthorized", {},
                                     io.BytesIO(f'{{"error": {{"message": "invalid x-api-key {KEY}"}}}}'.encode()))
    code, claude, report = run(refused)
    out, err = capsys.readouterr()
    assert (code, out, len(claude.seen)) == (2, "", 1)
    assert err.startswith("error: the read failed with HTTP 401: ") and "<ANTHROPIC_API_KEY>" in err
    assert KEY not in err and not report.exists()


@pytest.mark.parametrize("change, said", [
    ({"stop_reason": "refusal"}, "error: the read stopped with 'refusal' after "),
    ({"stop_reason": "max_tokens"}, "error: the read stopped with 'max_tokens' after "),
    ({"content": [{"type": "thinking", "thinking": "", "signature": "x"}]},
     "error: the read stopped with 'end_turn' after 0 characters of text"),
    ({"type": "error", "content": None}, "error: the read answered with something other than a message: "),
])
def test_an_answer_that_is_not_whole_fails_before_the_check_is_paid_for(run, capsys, change, said):
    code, claude, report = run({**recorded()["read"], **change}, recorded()["check"])
    assert (code, len(claude.seen)) == (2, 1)
    assert capsys.readouterr().err.startswith(said)
    assert not report.exists()


def test_a_check_that_leaves_a_feature_out_fails(run, capsys):
    check = recorded()["check"]
    judged = json.loads(check["content"][1]["text"])
    del judged["feature_9"]
    code, _, report = run(recorded()["read"], {**check, "content": [{"type": "text", "text": json.dumps(judged)}]})
    assert code == 2
    assert capsys.readouterr().err.startswith("error: the check did not say yes or no to each of the 9 features: ")
    assert not report.exists()
