import base64
import datetime
import importlib.machinery
import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import CONTRAIL
from videotape.ledger import Ledger

ROOT = Path(__file__).parent.parent
SCRIPT = str(ROOT / "scripts" / "runpod-render")
PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeFakeFakeFakeFakeFakeFakeFakeFakeFakeFake videotape-runpod\n"


@pytest.fixture(scope="module")
def script():
    loader = importlib.machinery.SourceFileLoader("runpod_render", str(ROOT / "scripts" / "runpod-render"))
    spec = importlib.util.spec_from_loader("runpod_render", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


@pytest.fixture
def built(script):
    return script.plan("examples/contrail", "terminal", "tapes/terminal", 3, "NVIDIA H100 80GB HBM3", 20.0, 3.99,
                       "catalog", PUBLIC_KEY, name="videotape-test")


def bash_parses(text: str) -> None:
    subprocess.run(["bash", "-n", "-c", text], check=True)


def test_the_deadline_is_the_cap_in_hours_minus_the_teardown_margin(script):
    assert script.deadline_seconds(20.0, 3.99) == int(20 / 3.99 * 3600) - 600 == 17445
    assert script.deadline_seconds(5.0, 3.99) == 3911


def test_a_cap_too_small_to_render_anything_is_refused(script):
    with pytest.raises(script.PlanError, match=r"a cap of \$1.00 buys 5 minutes .* the least that makes sense is \$2.00"):
        script.plan("examples/contrail", "terminal", "tapes/terminal", 1, "NVIDIA H100 80GB HBM3", 1.0, 3.99, "catalog",
                    PUBLIC_KEY)
    with pytest.raises(script.PlanError, match="has no secure price"):
        script.plan("examples/contrail", "terminal", "tapes/terminal", 1, "NVIDIA H100 80GB HBM3", 20.0, 0.0, "catalog",
                    PUBLIC_KEY)
    assert script.plan("examples/contrail", "terminal", "tapes/terminal", 1, "NVIDIA H100 80GB HBM3", 2.0, 3.99,
                       "catalog", PUBLIC_KEY).deadline_seconds == 1204


def test_the_create_body_asks_for_one_gpu_with_the_cuda_floor_ssh_and_the_self_destruct(script, built):
    body = script.create_body(built)
    assert body["name"] == "videotape-test"
    assert body["image"] == "runpod/pytorch:2.0.0-cu1300-torch2130-ubuntu2404"
    assert body["cloud"] == "SECURE"
    assert body["gpu"] == {"id": "NVIDIA H100 80GB HBM3", "count": 1, "minCudaVersion": "13.0"}
    assert body["disk"] == 160 and body["ports"] == ["22/tcp"]
    assert body["env"]["PUBLIC_KEY"] == PUBLIC_KEY.strip()
    assert body["env"]["HF_HUB_ENABLE_HF_TRANSFER"] == "0"
    assert "RUNPOD_API_KEY" not in json.dumps(body)
    json.dumps(body)
    words = shlex.split(body["args"])
    assert words[:2] == ["bash", "-c"] and len(words) == 3
    inner = words[2]
    assert inner.endswith("& exec /start.sh")
    bash_parses(inner)
    encoded = inner.split("echo ", 1)[1].split(" |", 1)[0]
    timer = base64.b64decode(encoded).decode()
    assert timer == script.self_destruct(17445)
    assert timer.startswith("sleep 17445\n")
    assert 'curl -fsS -X DELETE "https://api.runpod.io/v2/pods/$RUNPOD_POD_ID" -H "Authorization: Bearer $RUNPOD_API_KEY"' in timer
    assert 'runpodctl pod delete "$RUNPOD_POD_ID"' in timer
    assert '-d "{\\"action\\":\\"stop\\"}"' in timer and 'runpodctl pod stop "$RUNPOD_POD_ID"' in timer
    bash_parses(timer)


def test_the_remote_scripts_parse_and_run_the_render_in_the_project_with_the_story_and_the_takes(script, built):
    setup = script.setup_script()
    bash_parses(setup)
    assert setup.startswith("set -euo pipefail\n")
    assert "cd /workspace/videotape\n" in setup
    assert "uv sync --extra wan --extra qwen\n" in setup
    assert "wan.prefetch()" in setup and "snapshot_download(qwen.MODEL_ID)" in setup
    render = script.render_script(built)
    bash_parses(render)
    assert render.splitlines()[-3:] == [
        "cd /workspace/videotape", "cd examples/contrail",
        "uv run --project /workspace/videotape videotape render --story terminal --model wan2.2-5b --takes 3"]
    assert script.fetched(built) == "examples/contrail/tapes/terminal"
    assert script.dailies_command(built) == ["uv", "run", "--project", str(ROOT), "videotape", "dailies", "--story", "terminal"]
    cafe = script.plan("tests/fixtures/cafe", "chalk", "tape-wan2", 1, "NVIDIA H100 80GB HBM3", 5.0, 3.99, "catalog",
                       PUBLIC_KEY)
    assert script.render_script(cafe).splitlines()[-2:] == [
        "cd tests/fixtures/cafe",
        "uv run --project /workspace/videotape videotape render --story chalk --model wan2.2-5b --takes 1 --out tape-wan2"]
    assert script.fetched(cafe) == "tests/fixtures/cafe/tape-wan2"
    assert script.dailies_command(cafe) == ["uv", "run", "--project", str(ROOT), "videotape", "dailies", "--out", "tape-wan2"]


STARTED = datetime.datetime(2026, 11, 9, 11, 0, tzinfo=datetime.timezone.utc)
STOPPED = datetime.datetime(2026, 11, 9, 11, 30, tzinfo=datetime.timezone.utc)


def test_the_pod_ledger_line_names_its_tape_and_prices_the_wall_clock_at_the_list_price(script, built):
    assert script.ledger_line("abc123", built, STARTED, STOPPED) == {
        "kind": "pod", "tape": "tapes/terminal", "at": "2026-11-09T11:30:00+00:00", "pod": "abc123", "gpu": "NVIDIA H100 80GB HBM3",
        "usd_per_hour": 3.99, "started": "2026-11-09T11:00:00+00:00", "stopped": "2026-11-09T11:30:00+00:00",
        "seconds": 1800, "usd": 1.995}


class Pod:
    """A pod's SSH for the copy back: rsync is recorded, and cat answers with the take lines its render wrote."""

    host = "203.0.113.7"

    def __init__(self, takes: bytes):
        self.takes = takes
        self.copied: list[tuple[str, str]] = []
        self.ran: list[str] = []

    def rsync(self, source: str, target: str) -> None:
        self.copied.append((source, target))

    def run(self, command: str, check: bool = True) -> subprocess.CompletedProcess:
        self.ran.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=self.takes)


def test_the_pods_take_lines_and_its_pod_line_land_in_the_projects_ledger_for_their_tape(script, tmp_path, monkeypatch):
    monkeypatch.setattr(script, "ROOT", tmp_path)
    (tmp_path / "examples" / "contrail").mkdir(parents=True)
    book = tmp_path / "examples" / "contrail" / "ledger.jsonl"
    book.write_text(json.dumps({"kind": "take", "tape": "tapes/terminal", "seconds": 0.5}) + "\n")
    wan2 = script.plan("examples/contrail", "terminal", "tape-wan2", 3, "NVIDIA H100 80GB HBM3", 20.0, 3.99, "catalog",
                       PUBLIC_KEY)
    takes = "".join(json.dumps({"kind": "take", "tape": "tape-wan2", "seconds": seconds, "model": "wan2.2-5b"}) + "\n"
                    for seconds in (90.0, 100.5))
    pod = Pod(takes.encode())
    script.download(pod, wan2)
    script.append_ledger(wan2, script.ledger_line("abc123", wan2, STARTED, STOPPED))
    assert pod.copied == [("root@203.0.113.7:/workspace/videotape/examples/contrail/tape-wan2/",
                           f"{tmp_path}/examples/contrail/tape-wan2/")]
    assert pod.ran == ["cat /workspace/videotape/examples/contrail/ledger.jsonl"]
    assert [json.loads(line)["kind"] for line in book.read_text().splitlines()] == ["take", "take", "take", "pod"]
    assert Ledger(book, "tape-wan2").totals() == {"takes": 2, "gpu_seconds": 190.5, "pods": 1, "pod_hours": 0.5, "usd": 2.0}
    assert Ledger(book, "tapes/terminal").totals() == {"takes": 1, "gpu_seconds": 0.5, "pods": 0, "pod_hours": 0.0, "usd": 0.0}


def test_describe_names_every_part_of_the_plan(script, built):
    text = script.describe(built)
    for part in ("examples/contrail in the story terminal, 3 takes per shot, tape examples/contrail/tapes/terminal",
                 "$3.99/h (catalog)",
                 "$20.00 buys 5.01 h", "17445 s", "host CUDA >= 13.0", "160 GB container disk",
                 "PUBLIC_KEY, HF_HUB_ENABLE_HF_TRANSFER, PYTORCH_CUDA_ALLOC_CONF", "uv sync --extra wan --extra qwen",
                 "cd examples/contrail && uv run --project /workspace/videotape videotape render --story terminal "
                 "--model wan2.2-5b --takes 3",
                 "append the pod line to examples/contrail/ledger.jsonl",
                 "run videotape dailies --story terminal in examples/contrail"):
        assert part in text, part
    assert "AAAAIFakeFakeFake" not in text.split("create body")[1].split("\n")[0]


def test_dry_run_in_a_project_without_a_key_prints_the_plan_and_creates_nothing():
    result = subprocess.run([SCRIPT, "--story", "posters", "--takes", "3", "--cap-usd", "20", "--dry-run"],
                            capture_output=True, text=True, cwd=CONTRAIL, env={"PATH": "/usr/bin:/bin"})
    assert result.returncode == 0, result.stderr
    assert ("project       examples/contrail in the story posters, 3 takes per shot, tape examples/contrail/tapes/posters"
            in result.stdout.splitlines())
    assert ("render        cd examples/contrail && uv run --project /workspace/videotape videotape render --story posters "
            "--model wan2.2-5b --takes 3") in result.stdout.splitlines()
    assert result.stdout.rstrip().endswith("dry run: nothing was created.")
    assert "$3.99/h (assumed, catalog read of 2026-11-09; set RUNPOD_API_KEY for the live price)" in result.stdout
    assert (ROOT / ".runpod" / "id_ed25519.pub").read_text().startswith("ssh-ed25519 ")


def test_a_real_run_without_a_key_stops_before_anything_else():
    result = subprocess.run([SCRIPT, "--story", "terminal", "--cap-usd", "20"], capture_output=True, text=True,
                            cwd=CONTRAIL, env={"PATH": "/usr/bin:/bin"})
    assert result.returncode == 2
    assert result.stderr.strip() == "error: RUNPOD_API_KEY is not set; export it, or pass --dry-run to see the plan"


def test_a_story_the_project_does_not_have_stops_it_before_a_pod_is_rented():
    result = subprocess.run([SCRIPT, "--story", "poster", "--cap-usd", "20", "--dry-run"], capture_output=True, text=True,
                            cwd=CONTRAIL, env={"PATH": "/usr/bin:/bin"})
    assert (result.returncode, result.stdout) == (2, "")
    assert result.stderr == 'error: no story "poster" in examples/contrail/stories; the stories are posters and terminal\n'
    missing = subprocess.run([SCRIPT, "--cap-usd", "20", "--dry-run"], capture_output=True, text=True, cwd=CONTRAIL,
                             env={"PATH": "/usr/bin:/bin"})
    assert missing.returncode == 2 and "the following arguments are required: --story" in missing.stderr


def test_it_runs_only_in_a_project_inside_the_repository(tmp_path):
    outside = subprocess.run([SCRIPT, "--story", "terminal", "--cap-usd", "20", "--dry-run"], capture_output=True,
                             text=True, cwd=ROOT, env={"PATH": "/usr/bin:/bin"})
    assert (outside.returncode, outside.stdout) == (2, "")
    assert outside.stderr.startswith("error: no pyproject.toml with a [tool.videotape] table here; run this in an app's project")
    (tmp_path / "pyproject.toml").write_text('[tool.videotape]\nscreenplay = "app:app"\n')
    elsewhere = subprocess.run([SCRIPT, "--story", "terminal", "--cap-usd", "20", "--dry-run"], capture_output=True,
                               text=True, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"})
    assert (elsewhere.returncode, elsewhere.stdout) == (2, "")
    assert "and only this repository's tracked files are copied to the pod" in elsewhere.stderr
