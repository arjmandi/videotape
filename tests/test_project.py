"""A project's [tool.videotape] settings and its .env, as every project command reads them."""

import os

from conftest import copy_of
from videotape import project


def test_a_projects_env_file_sets_the_keys_the_environment_lacks_and_prints_nothing(tmp_path, monkeypatch, capsys):
    directory = copy_of("cafe", tmp_path)
    (directory / ".env").write_text('# from fal.ai/dashboard/keys\n\nFAL_KEY="fal-from-the-file"\nexport VT_A=a\n'
                                    "VT_B = 'b' \nVT_EMPTY=\nVT_SET=from-the-file\nnot a setting\n")
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setenv("VT_SET", "from-the-shell")
    project.find(directory / "data")
    assert {key: os.environ.get(key) for key in ("FAL_KEY", "VT_A", "VT_B", "VT_EMPTY", "VT_SET")} == {
        "FAL_KEY": "fal-from-the-file", "VT_A": "a", "VT_B": "b", "VT_EMPTY": None, "VT_SET": "from-the-shell"}
    assert capsys.readouterr() == ("", "")
