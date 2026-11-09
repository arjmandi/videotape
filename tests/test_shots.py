from pathlib import Path

import pytest

from videotape import ScreenplayError
from videotape.cli import main
from videotape.loader import load
from videotape.shots import Mode, plan

SURF_SHOP = Path(__file__).parent.parent / "examples" / "surf_shop"
LOOK = ("A small surf shop on the California coast in warm afternoon light: whitewashed wood, sea air, "
        "and surfboards hand-painted in bright patterns.")
CLOSE = "The camera settles and holds still. Large, crisp, legible lettering."


def write_screenplay(directory: Path, body: str) -> Path:
    (directory / "screenplay.py").write_text('import videotape as vt\n\nplay = vt.Screenplay("T", look="L")\n' + body)
    return directory


def test_surf_shop_walks_six_shots_breadth_first():
    shots = plan(load(SURF_SHOP))
    assert [(s.start, s.land, s.mode) for s in shots] == [
        (None, "welcome", Mode.TEXT_TO_VIDEO),
        ("welcome", "entrance", Mode.IMAGE_TO_VIDEO),
        ("entrance", "login", Mode.IMAGE_TO_VIDEO),
        ("entrance", "signup", Mode.IMAGE_TO_VIDEO),
        ("entrance", "gallery", Mode.IMAGE_TO_VIDEO),
        ("signup", "login", Mode.FIRST_AND_LAST_FRAME),
    ]


def test_walk_finishes_each_queued_scene_before_the_next(tmp_path):
    write_screenplay(tmp_path, 'play.scene("a", actions={"B": "b", "C": "c"})\n'
                     'play.scene("b", actions={"D": "d"})\nplay.scene("c", actions={"E": "e"})\n'
                     'play.scene("d")\nplay.scene("e")\n')
    assert [s.label for s in plan(load(tmp_path))] == [None, "B", "C", "D", "E"]


def test_opening_prompt():
    opening = plan(load(SURF_SHOP))[0]
    assert opening.prompt == (
        f"{LOOK} The camera slowly pushes in. The shop's front by the beach, its name painted over the open door. "
        'The lettering reads "Brushstroke Surf Co." and "Hand-painted surfboards from California". '
        f'A button is labelled "Enter shop". {CLOSE}'
    )


def test_action_prompt():
    signup = next(s for s in plan(load(SURF_SHOP)) if s.label == "Create an account")
    assert signup.prompt == (
        f'{LOOK} The button labelled "Create an account" is pressed. The camera glides smoothly to the next view. '
        'A sign-up card on a stand. The lettering reads "Create your account", "Email" and "Password". '
        f'A button is labelled "Sign up". {CLOSE}'
    )


def test_every_prompt_quotes_its_landing_scene():
    screenplay = load(SURF_SHOP)
    for shot in plan(screenplay):
        scene = screenplay.scenes[shot.land]
        for text in [*scene.shows, *scene.actions]:
            assert f'"{text}"' in shot.prompt


def test_action_to_missing_scene(tmp_path):
    write_screenplay(tmp_path, 'play.scene("home", actions={"Go": "nowhere"})\n')
    with pytest.raises(ScreenplayError, match='"home".*"Go".*"nowhere"'):
        plan(load(tmp_path))


def test_unreachable_scene(tmp_path):
    write_screenplay(tmp_path, 'play.scene("home")\nplay.scene("attic")\n')
    with pytest.raises(ScreenplayError, match="attic"):
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
