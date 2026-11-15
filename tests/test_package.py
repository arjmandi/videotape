"""What videotape's wheel carries, as uv builds it from this checkout."""

import subprocess
import zipfile
from pathlib import Path

from videotape import player

ROOT = Path(__file__).parent.parent


def test_the_wheel_carries_tapeplayers_source_as_videotape_macos_and_nothing_a_build_leaves(tmp_path):
    subprocess.run(["uv", "build", "--wheel", "--quiet", "--out-dir", str(tmp_path)], cwd=ROOT, check=True)
    [wheel] = tmp_path.glob("videotape-*.whl")
    names = zipfile.ZipFile(wheel).namelist()
    assert sorted(name.removeprefix("videotape/macos/") for name in names if name.startswith("videotape/macos/")) == \
        sorted(path.relative_to(player.SOURCE).as_posix() for path in player.sources())
