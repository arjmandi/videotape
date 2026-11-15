"""What videotape's wheel carries, as uv builds it from this checkout."""

import subprocess
import zipfile
from pathlib import Path

from videotape import new, player

ROOT = Path(__file__).parent.parent


def test_the_wheel_carries_tapeplayers_source_without_what_a_build_leaves_and_the_whole_starter(tmp_path):
    subprocess.run(["uv", "build", "--wheel", "--quiet", "--out-dir", str(tmp_path)], cwd=ROOT, check=True)
    [wheel] = tmp_path.glob("videotape-*.whl")
    names = zipfile.ZipFile(wheel).namelist()

    def under(folder: str) -> list[str]:
        return sorted(name.removeprefix(folder) for name in names if name.startswith(folder))

    assert under("videotape/macos/") == sorted(path.relative_to(player.SOURCE).as_posix() for path in player.sources())
    assert under("videotape/starter/") == sorted(path.relative_to(new.STARTER).as_posix()
                                                 for path in new.STARTER.rglob("*") if path.is_file())
