import io
import json
import sys
import tarfile
from dataclasses import fields
from importlib.util import find_spec
from pathlib import Path

import pytest

from conftest import FIXTURES, copy_of, planned
from videotape import wan
from videotape.plan import Mode


def test_a_key_runs_ti2v_from_text_and_a_move_runs_fun_inp_between_two_keys():
    plan = planned(FIXTURES / "cafe")
    menu, pick = plan.keys[0], plan.moves[0]
    assert (menu.title, pick.title) == ("key menu()", 'menu() -> order(Espresso) "Espresso, $3"')
    start, end = Path("tape") / menu.image, Path("tape") / plan.keys[1].image
    common = dict(negative_prompt=wan.NEGATIVE_PROMPT, width=1280, height=704, frames=81, fps=24, steps=50, shift=5.0)
    assert wan.request(menu.mode, menu.prompt, None, None, 1) == wan.Request(
        checkpoint="Wan-AI/Wan2.2-TI2V-5B-Diffusers", revision="b8fff7315c768468a5333511427288870b2e9635",
        mode=Mode.TEXT_TO_VIDEO, prompt=menu.prompt, seed=1, guidance=5.0, start=None, end=None, **common)
    assert wan.request(pick.mode, pick.prompt, start, end, 2) == wan.Request(
        checkpoint="alibaba-pai/Wan2.2-Fun-5B-InP", revision="d3e911d57ec9e44f1f06dc565387afbe8d28f25f",
        mode=Mode.FIRST_AND_LAST_FRAME, prompt=pick.prompt, seed=2, guidance=6.0, start=start, end=end, **common)


def test_every_shot_fits_the_models_and_the_five_second_limit():
    for mode in Mode:
        built = wan.request(mode, "a prompt", None, None, 1)
        assert (built.frames - 1) % 4 == 0
        assert built.frames / built.fps <= 5
        assert (built.width, built.height) == (1280, 704)


def test_settings_cover_every_field_a_shot_does_not_supply():
    built = wan.request(Mode.TEXT_TO_VIDEO, "a prompt", None, None, 7)
    settings = built.settings()
    assert set(settings) == {field.name for field in fields(wan.Request)} - {"mode", "prompt", "seed", "start", "end"}
    assert json.dumps(settings, sort_keys=True)
    assert wan.request(Mode.TEXT_TO_VIDEO, "another prompt", None, None, 8).settings() == settings
    assert wan.request(Mode.FIRST_AND_LAST_FRAME, "a prompt", Path("a.png"), Path("b.png"), 7).settings() != settings


def test_the_model_puts_its_request_settings_in_the_cache_key():
    for mode in Mode:
        assert wan.Wan.settings(mode) == wan.request(mode, "any prompt", None, None, 99).settings()


def test_wan_without_its_extra_says_what_to_install_and_renders_nothing(tmp_path, cli, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "diffusers", None)
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "render", "--model", "wan2.2-5b") == 1
    assert capsys.readouterr().err == ("error: wan2.2-5b needs videotape's wan extra, which is not installed here; "
                                       "install videotape[wan]\n")
    assert not (directory / "tape").exists()


@pytest.mark.skipif(find_spec("diffusers") is None, reason="needs the wan extra")
def test_wan_on_a_machine_without_cuda_says_so_before_rendering(tmp_path, cli, capsys):
    import torch

    if torch.cuda.is_available():
        pytest.skip("this machine has CUDA")
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "render", "--model", "wan2.2-5b") == 1
    err = capsys.readouterr().err
    assert err.startswith("error: wan2.2-5b needs a CUDA GPU with about 80 GB, and this machine has ")
    assert err.endswith(" only; rent one with scripts/runpod-render\n")
    assert not (directory / "tape").exists()


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
