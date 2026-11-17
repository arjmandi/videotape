import io
import json
import sys
import tarfile
from dataclasses import fields
from importlib.util import find_spec
from pathlib import Path

import pytest

from conftest import FIXTURES, as_explained, copy_of, planned, told, words
from videotape import wan
from videotape.errors import CODES, ModelError
from videotape.model import MODELS
from videotape.plan import Mode


def test_a_key_runs_ti2v_from_text_and_a_move_runs_fun_inp_between_two_keys():
    plan, chalk = planned(FIXTURES / "cafe"), told(FIXTURES / "cafe")
    menu, pick = plan.keys[0], plan.moves[0]
    assert (menu.title, pick.title) == ("key menu()", 'menu() -> order(Espresso) "Espresso, $3"')
    start, end = Path("tape") / menu.image, Path("tape") / plan.keys[1].image
    common = dict(negative_prompt=wan.NEGATIVE_PROMPT, width=1280, height=704, frames=81, fps=24, steps=50, shift=5.0)
    assert wan.request(menu.mode, words(menu, chalk), None, None, 1) == wan.Request(
        checkpoint="Wan-AI/Wan2.2-TI2V-5B-Diffusers", revision="b8fff7315c768468a5333511427288870b2e9635",
        mode=Mode.TEXT_TO_VIDEO, prompt=words(menu, chalk), seed=1, guidance=5.0, start=None, end=None, **common)
    assert wan.request(pick.mode, words(pick, chalk), start, end, 2) == wan.Request(
        checkpoint="alibaba-pai/Wan2.2-Fun-5B-InP", revision="d3e911d57ec9e44f1f06dc565387afbe8d28f25f",
        mode=Mode.FIRST_AND_LAST_FRAME, prompt=words(pick, chalk), seed=2, guidance=6.0, start=start, end=end, **common)


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


# What umT5's own tokenizer made of each prompt on 2026-11-14, with its end token: google/umt5-xxl's tokenizer.json.
UMT5_TOKENS = {
    'The day "12" is pressed. The camera slides along the wall to the next poster and settles straight on.': 27,
    'Reading "Jan" "679", "Feb" "1,358", "Mar" "6,530", "Apr" "6,530", and "May" "11,326".': 52,
    'Static shot. A long sunlit wall in a 1960s airline ticket office, hung with screen-printed travel posters.': 31,
}


def test_a_plan_counts_a_prompts_tokens_without_the_tokenizer_and_never_lower_than_it():
    assert wan.tokens("Static shot.") == len(["Stat", "ic", "shot", ".", "the end"])
    assert [wan.tokens(prompt) for prompt in UMT5_TOKENS] == [32, 58, 36]
    assert all(wan.tokens(prompt) >= real for prompt, real in UMT5_TOKENS.items())
    assert (MODELS["wan2.2-5b"].prompt_limit.most, MODELS["wan2.2-5b"].prompt_limit.count) == (512, wan.tokens)
    assert MODELS["stand-in"].prompt_limit is None


def test_wan_without_its_extra_says_what_to_install_and_renders_nothing(tmp_path, cli, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "diffusers", None)
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "render", "--story", "chalk", "--model", "wan2.2-5b") == 1
    assert as_explained("VT111").fullmatch(capsys.readouterr().err.rstrip("\n"))
    assert not (directory / "tapes").exists()


@pytest.mark.skipif(find_spec("diffusers") is None, reason="needs the wan extra")
def test_wan_on_a_machine_without_cuda_says_so_before_rendering(tmp_path, cli, capsys):
    import torch

    if torch.cuda.is_available():
        pytest.skip("this machine has CUDA")
    directory = copy_of("cafe", tmp_path)
    assert cli(directory, "render", "--story", "chalk", "--model", "wan2.2-5b") == 1
    err = capsys.readouterr().err
    assert err.startswith("error VT111 wan2.2-5b: needs a CUDA GPU with about 80 GB, and this machine has ")
    assert err.endswith(f" only\nfix: {CODES['VT111'].fix.removeprefix('fix: ')}\n")
    assert not (directory / "tapes").exists()


def test_wan_films_no_key_from_a_start_picture_and_names_a_model_on_fal_that_does(tmp_path):
    with pytest.raises(ModelError) as refused:
        wan.Wan.__new__(wan.Wan).first_frame("a key", tmp_path / "start.png", 1, tmp_path / "take.mp4")
    assert refused.value.code == "VT111" and "--model gemini-omni-flash-1.2" in refused.value.fix
    assert not (tmp_path / "take.mp4").exists()


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
