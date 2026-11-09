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

from videotape import ledger

ROOT = Path(__file__).parent.parent
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
    return script.plan("examples/surf_shop", 3, "NVIDIA H100 80GB HBM3", 20.0, 3.99, "catalog", PUBLIC_KEY, name="videotape-test")


def bash_parses(text: str) -> None:
    subprocess.run(["bash", "-n", "-c", text], check=True)


def test_the_deadline_is_the_cap_in_hours_minus_the_teardown_margin(script):
    assert script.deadline_seconds(20.0, 3.99) == int(20 / 3.99 * 3600) - 600 == 17445
    assert script.deadline_seconds(5.0, 3.99) == 3911


def test_a_cap_too_small_to_render_anything_is_refused(script):
    with pytest.raises(script.PlanError, match=r"a cap of \$1.00 buys 5 minutes .* the least that makes sense is \$2.00"):
        script.plan("examples/surf_shop", 1, "NVIDIA H100 80GB HBM3", 1.0, 3.99, "catalog", PUBLIC_KEY)
    with pytest.raises(script.PlanError, match="has no secure price"):
        script.plan("examples/surf_shop", 1, "NVIDIA H100 80GB HBM3", 20.0, 0.0, "catalog", PUBLIC_KEY)
    assert script.plan("examples/surf_shop", 1, "NVIDIA H100 80GB HBM3", 2.0, 3.99, "catalog", PUBLIC_KEY).deadline_seconds == 1204


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


def test_the_remote_scripts_parse_and_run_the_render_with_the_takes(script, built):
    setup = script.setup_script()
    bash_parses(setup)
    assert setup.startswith("set -euo pipefail\n")
    assert "cd /workspace/videotape\n" in setup
    assert "uv sync --extra wan --extra qwen\n" in setup
    assert "wan.prefetch()" in setup and "snapshot_download(qwen.MODEL_ID)" in setup
    render = script.render_script(built)
    bash_parses(render)
    assert render.rstrip().endswith("uv run videotape render examples/surf_shop --model wan2.2-5b --checks qwen3-vl-8b --takes 3")
    cafe = script.plan(".claude/skills/verify/fixtures/cafe", 1, "NVIDIA H100 80GB HBM3", 5.0, 3.99, "catalog", PUBLIC_KEY)
    assert script.render_command(cafe) == ("uv run videotape render .claude/skills/verify/fixtures/cafe --model wan2.2-5b "
                                           "--checks qwen3-vl-8b --takes 1")


def test_the_pod_ledger_line_prices_the_wall_clock_at_the_list_price(script, built):
    started = datetime.datetime(2026, 11, 9, 11, 0, tzinfo=datetime.timezone.utc)
    stopped = datetime.datetime(2026, 11, 9, 11, 30, tzinfo=datetime.timezone.utc)
    line = script.ledger_line("abc123", built, started, stopped)
    assert line == {"kind": "pod", "at": "2026-11-09T11:30:00+00:00", "pod": "abc123", "gpu": "NVIDIA H100 80GB HBM3",
                    "usd_per_hour": 3.99, "started": "2026-11-09T11:00:00+00:00", "stopped": "2026-11-09T11:30:00+00:00",
                    "seconds": 1800, "usd": 1.995}
    assert ledger.totals([line]) == {"takes": 0, "gpu_seconds": 0.0, "pods": 1, "pod_hours": 0.5, "usd": 2.0}


def test_describe_names_every_part_of_the_plan(script, built):
    text = script.describe(built)
    for part in ("examples/surf_shop, 3 takes per shot", "$3.99/h (catalog)", "$20.00 buys 5.01 h", "17445 s",
                 "host CUDA >= 13.0", "160 GB container disk", "PUBLIC_KEY, HF_HUB_ENABLE_HF_TRANSFER, PYTORCH_CUDA_ALLOC_CONF",
                 "uv sync --extra wan --extra qwen", "--takes 3", "uv run videotape dailies examples/surf_shop"):
        assert part in text, part
    assert "AAAAIFakeFakeFake" not in text.split("create body")[1].split("\n")[0]


def test_dry_run_without_a_key_prints_the_plan_and_creates_nothing():
    result = subprocess.run([str(ROOT / "scripts" / "runpod-render"), "examples/surf_shop", "--takes", "3", "--cap-usd", "20",
                             "--dry-run"], capture_output=True, text=True, cwd=ROOT, env={"PATH": "/usr/bin:/bin"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.rstrip().endswith("dry run: nothing was created.")
    assert "$3.99/h (assumed, catalog read of 2026-11-09; set RUNPOD_API_KEY for the live price)" in result.stdout
    assert (ROOT / ".runpod" / "id_ed25519.pub").read_text().startswith("ssh-ed25519 ")


def test_a_real_run_without_a_key_stops_before_anything_else(capsys):
    result = subprocess.run([str(ROOT / "scripts" / "runpod-render"), "examples/surf_shop", "--cap-usd", "20"],
                            capture_output=True, text=True, cwd=ROOT, env={"PATH": "/usr/bin:/bin"})
    assert result.returncode == 2
    assert result.stderr.strip() == "error: RUNPOD_API_KEY is not set; export it, or pass --dry-run to see the plan"
    missing = subprocess.run([str(ROOT / "scripts" / "runpod-render"), "examples/nowhere", "--cap-usd", "20", "--dry-run"],
                             capture_output=True, text=True, cwd=ROOT, env={"PATH": "/usr/bin:/bin"})
    assert missing.returncode == 2 and missing.stderr.startswith("error: no screenplay.py in examples/nowhere")
