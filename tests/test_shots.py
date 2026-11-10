from pathlib import Path

import pytest

from videotape import ScreenplayError
from videotape.cli import main
from videotape.loader import load
from videotape.shots import Key, Mode, Move, plan

SURF_SHOP = Path(__file__).parent.parent / "examples" / "surf_shop"
WALK = Path(__file__).parent.parent / ".claude" / "skills" / "verify" / "fixtures" / "walk"
LOOK = ("A small surf shop on the California coast in warm afternoon light: whitewashed wood, sea air, "
        "and surfboards hand-painted in bright patterns.")


def write_screenplay(directory: Path, body: str) -> Path:
    (directory / "screenplay.py").write_text('import videotape as vt\n\nplay = vt.Screenplay("T", look="L")\n' + body)
    return directory


def key(screenplay_dir: Path, scene: str) -> Key:
    return next(shot for shot in plan(load(screenplay_dir)) if isinstance(shot, Key) and shot.scene == scene)


def move(screenplay_dir: Path, label: str) -> Move:
    return next(shot for shot in plan(load(screenplay_dir)) if isinstance(shot, Move) and shot.label == label)


def test_surf_shop_keys_every_scene_then_draws_every_move():
    shots = plan(load(SURF_SHOP))
    keys, moves = shots[:5], shots[5:]
    assert [(shot.scene, shot.mode) for shot in keys] == [
        (scene, Mode.TEXT_TO_VIDEO) for scene in ("welcome", "entrance", "login", "signup", "gallery")]
    assert [(shot.start, shot.land, shot.label, shot.mode) for shot in moves] == [
        ("welcome", "entrance", "Enter shop", Mode.FIRST_AND_LAST_FRAME),
        ("entrance", "login", "I have an account", Mode.FIRST_AND_LAST_FRAME),
        ("entrance", "signup", "Create an account", Mode.FIRST_AND_LAST_FRAME),
        ("entrance", "gallery", "Browse as guest", Mode.FIRST_AND_LAST_FRAME),
        ("signup", "login", "Sign up", Mode.FIRST_AND_LAST_FRAME),
    ]
    assert [shot.title for shot in shots] == [
        "key welcome", "key entrance", "key login", "key signup", "key gallery",
        'welcome -> entrance "Enter shop"', 'entrance -> login "I have an account"',
        'entrance -> signup "Create an account"', 'entrance -> gallery "Browse as guest"', 'signup -> login "Sign up"']
    assert [shot.move for shot in moves] == ["welcome--enter-shop", "entrance--i-have-an-account",
                                             "entrance--create-an-account", "entrance--browse-as-guest", "signup--sign-up"]


def test_walk_keys_each_queued_scene_before_the_next():
    shots = plan(load(WALK))
    assert [shot.scene for shot in shots if isinstance(shot, Key)] == ["hall", "left", "right", "desk", "fridge"]
    assert [shot.label for shot in shots if isinstance(shot, Move)] == ["Left door", "Right door", "Open desk", "Open fridge"]


def test_entrance_key_prompt_compiles_exactly():
    assert key(SURF_SHOP, "entrance").prompt == (
        f"Static shot. {LOOK} Just inside, by the counter. "
        'The text reads "How would you like to come in?". Below it, three big flat buttons are stacked, with bold '
        'black letters reading "I have an account", "Create an account" and "Browse as guest". Sharp, legible lettering.'
    )


def test_key_prompt_with_one_button():
    assert key(SURF_SHOP, "welcome").prompt == (
        f"Static shot. {LOOK} The shop's front by the beach, its name painted over the open door. "
        'The text reads "Brushstroke Surf Co." and "Hand-painted surfboards from California". '
        'Below it, one big flat button sits, with bold black letters reading "Enter shop". Sharp, legible lettering.'
    )


def test_key_prompt_with_no_buttons():
    assert key(SURF_SHOP, "login").prompt == (
        f'Static shot. {LOOK} A card on the counter. The text reads "Log in", "Email" and "Password". Sharp, legible lettering.'
    )


def test_key_prompt_with_buttons_but_no_text():
    assert key(WALK, "hall").prompt == (
        'Static shot. A plain room. A long hall. Two big flat buttons are stacked, with bold black letters reading '
        '"Left door" and "Right door". Sharp, legible lettering.'
    )
    assert key(WALK, "left").prompt == (
        'Static shot. A plain room. A small study. One big flat button sits, with bold black letters reading '
        '"Open desk". Sharp, legible lettering.'
    )


def test_key_prompt_with_neither_text_nor_buttons():
    assert key(WALK, "desk").prompt == "Static shot. A plain room. An open drawer. Sharp, legible lettering."


def test_move_prompt_is_the_press_and_the_move_only():
    assert move(SURF_SHOP, "Enter shop").prompt == (
        'The button labelled "Enter shop" is pressed. The camera walks through the open door.')
    assert move(SURF_SHOP, "Sign up").prompt == (
        'The button labelled "Sign up" is pressed. The camera glides smoothly to the next view.')


def test_every_key_quotes_its_scene_and_no_move_quotes_any_scene():
    screenplay = load(SURF_SHOP)
    for shot in plan(screenplay):
        if isinstance(shot, Key):
            scene = screenplay.scenes[shot.scene]
            for text in [*scene.shows, *scene.actions]:
                assert f'"{text}"' in shot.prompt
        else:
            scene = screenplay.scenes[shot.land]
            for text in [*scene.shows, *(label for label in scene.actions)]:
                assert f'"{text}"' not in shot.prompt


def test_cli_lists_the_ten_shots_with_their_prompts(capsys):
    assert main(["shots", str(SURF_SHOP)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Brushstroke Surf Co."
    assert [line for line in lines if line[:1].isdigit()] == [
        "1. key welcome  (text-to-video)",
        "2. key entrance  (text-to-video)",
        "3. key login  (text-to-video)",
        "4. key signup  (text-to-video)",
        "5. key gallery  (text-to-video)",
        '6. welcome -> entrance "Enter shop"  (first-and-last-frame)',
        '7. entrance -> login "I have an account"  (first-and-last-frame)',
        '8. entrance -> signup "Create an account"  (first-and-last-frame)',
        '9. entrance -> gallery "Browse as guest"  (first-and-last-frame)',
        '10. signup -> login "Sign up"  (first-and-last-frame)',
    ]
    assert lines[3] == f"   {key(SURF_SHOP, 'welcome').prompt}"
    assert lines[-1] == f"   {move(SURF_SHOP, 'Sign up').prompt}"


def test_action_to_missing_scene(tmp_path):
    write_screenplay(tmp_path, 'play.scene("home", actions={"Go": "nowhere"})\n')
    with pytest.raises(ScreenplayError, match='"home".*"Go".*"nowhere"'):
        plan(load(tmp_path))


def test_unreachable_scene(tmp_path):
    write_screenplay(tmp_path, 'play.scene("home")\nplay.scene("attic")\n')
    with pytest.raises(ScreenplayError, match="attic"):
        plan(load(tmp_path))


def test_no_scenes(tmp_path):
    write_screenplay(tmp_path, "")
    with pytest.raises(ScreenplayError, match="no scenes"):
        plan(load(tmp_path))


def test_duplicate_label_in_scene(tmp_path):
    write_screenplay(tmp_path, 'play.scene("home", actions={"Sign up": "home", "Sign up": "home"})\n')
    with pytest.raises(ScreenplayError, match='"home".*"Sign up"'):
        load(tmp_path)


def test_cli_reports_error(tmp_path, capsys):
    write_screenplay(tmp_path, 'play.scene("home")\nplay.scene("attic")\n')
    assert main(["shots", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "attic" in err
