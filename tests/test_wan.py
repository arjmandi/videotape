import io
import json
import sys
import tarfile
from dataclasses import fields
from importlib.util import find_spec
from pathlib import Path

import pytest

from videotape import wan
from videotape.cli import main
from videotape.loader import load
from videotape.shots import Mode, plan

SURF_SHOP = Path(__file__).parent.parent / "examples" / "surf_shop"


def test_the_three_surf_shop_requests():
    opening, enter_shop, *_, sign_up = plan(load(SURF_SHOP))
    keys = SURF_SHOP / "tape" / "keys"
    common = dict(negative_prompt=wan.NEGATIVE_PROMPT, width=1280, height=704, frames=81, fps=24, steps=50, shift=5.0)
    assert wan.request(opening.mode, opening.prompt, None, None, 1) == wan.Request(
        checkpoint="Wan-AI/Wan2.2-TI2V-5B-Diffusers", revision="b8fff7315c768468a5333511427288870b2e9635",
        mode=Mode.TEXT_TO_VIDEO, prompt=opening.prompt, seed=1, guidance=5.0, start=None, end=None, **common)
    assert wan.request(enter_shop.mode, enter_shop.prompt, keys / "welcome.png", None, 2) == wan.Request(
        checkpoint="Wan-AI/Wan2.2-TI2V-5B-Diffusers", revision="b8fff7315c768468a5333511427288870b2e9635",
        mode=Mode.IMAGE_TO_VIDEO, prompt=enter_shop.prompt, seed=2, guidance=5.0, start=keys / "welcome.png", end=None, **common)
    assert wan.request(sign_up.mode, sign_up.prompt, keys / "signup.png", keys / "login.png", 3) == wan.Request(
        checkpoint="alibaba-pai/Wan2.2-Fun-5B-InP", revision="d3e911d57ec9e44f1f06dc565387afbe8d28f25f",
        mode=Mode.FIRST_AND_LAST_FRAME, prompt=sign_up.prompt, seed=3, guidance=6.0,
        start=keys / "signup.png", end=keys / "login.png", **common)


def test_every_shot_fits_the_models_and_the_five_second_limit():
    for mode in Mode:
        built = wan.request(mode, "a prompt", None, None, 1)
        assert (built.frames - 1) % 4 == 0
        assert built.frames / built.fps <= 5
        assert (built.width, built.height) == (1280, 704)


def test_settings_cover_every_field_a_shot_does_not_supply():
    built = wan.request(Mode.IMAGE_TO_VIDEO, "a prompt", Path("start.png"), None, 7)
    settings = built.settings()
    assert set(settings) == {field.name for field in fields(wan.Request)} - {"mode", "prompt", "seed", "start", "end"}
    assert json.dumps(settings, sort_keys=True)
    assert wan.request(Mode.IMAGE_TO_VIDEO, "another prompt", Path("other.png"), None, 8).settings() == settings
    assert wan.request(Mode.FIRST_AND_LAST_FRAME, "a prompt", Path("a.png"), Path("b.png"), 7).settings() != settings


def test_the_model_puts_its_request_settings_in_the_cache_key():
    for mode in Mode:
        assert wan.Wan.settings(mode) == wan.request(mode, "any prompt", None, None, 99).settings()


def test_wan_without_the_extra_names_the_install_command(capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "diffusers", None)
    assert main(["render", str(SURF_SHOP), "--model", "wan2.2-5b"]) == 1
    assert capsys.readouterr().err == "error: wan2.2-5b needs the wan extra; install it with uv sync --extra wan\n"


@pytest.mark.skipif(find_spec("diffusers") is None, reason="needs the wan extra")
def test_wan_on_a_machine_without_cuda_says_so_before_rendering(tmp_path, capsys):
    import torch

    if torch.cuda.is_available():
        pytest.skip("this machine has CUDA")
    (tmp_path / "screenplay.py").write_text('import videotape as vt\n\nplay = vt.Screenplay("T", look="L")\n')
    assert main(["render", str(tmp_path), "--model", "wan2.2-5b"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: wan2.2-5b needs a CUDA GPU with about 80 GB, and this machine has ")
    assert err.endswith(" only; rent one with scripts/runpod-render\n")
    assert not (tmp_path / "tape").exists()


def test_videox_fun_source_is_fetched_once_from_the_pinned_archive(tmp_path, monkeypatch):
    repo, sha = wan.VIDEOX_FUN
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for name, text in ((f"VideoX-Fun-{sha}/videox_fun/__init__.py", ""), (f"VideoX-Fun-{sha}/config/wan2.2/wan_civitai_5b.yaml", "format: civitai\n")):
            info = tarfile.TarInfo(name)
            info.size = len(text.encode())
            archive.addfile(info, io.BytesIO(text.encode()))
    archive_path = tmp_path / "archive.tar.gz"
    archive_path.write_bytes(payload.getvalue())
    monkeypatch.setattr(wan, "VIDEOX_FUN_ARCHIVE", archive_path.as_uri())
    monkeypatch.setenv("VIDEOX_FUN_DIR", str(tmp_path / "code" / "videox"))
    source = wan.videox_fun_dir()
    assert source == tmp_path / "code" / "videox"
    assert (source / "videox_fun" / "__init__.py").is_file()
    assert (source / "config" / "wan2.2" / "wan_civitai_5b.yaml").read_text() == "format: civitai\n"
    assert sorted(path.name for path in source.parent.iterdir()) == ["videox"]
    archive_path.unlink()
    assert wan.videox_fun_dir() == source
