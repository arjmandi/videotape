import json
from dataclasses import fields
from pathlib import Path

from videotape import wan
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
