import importlib
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

SAMPLES = {
    "hello": (FIXTURES / "hello", "app"),
    "demo": (FIXTURES / "apps", "demo"),
    "screening": (FIXTURES / "apps", "screening"),
    "pinhole": (FIXTURES / "apps", "pinhole"),
    "relay": (FIXTURES / "apps", "relay"),
    "crm": (FIXTURES / "apps", "crm"),
}
"""The 06 §2.2 sign-in app and the five §9 apps: directory and module."""

BROKEN = FIXTURES / "broken"


def load_module(directory: Path, module: str):
    """Imports `module` from `directory` as the CLI would, then forgets the modules it brought in,
    so fixtures with the same module names (`app`, `services`) do not see each other."""
    before = set(sys.modules)
    sys.path.insert(0, str(directory))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.remove(str(directory))
        for name in set(sys.modules) - before:
            mod = sys.modules[name]
            if getattr(mod, "__file__", "") and str(directory) in mod.__file__:
                del sys.modules[name]


def load_sample(name: str):
    directory, module = SAMPLES[name]
    return load_module(directory, module)


def load_broken(name: str):
    return load_module(BROKEN, name)


@pytest.fixture(params=sorted(SAMPLES))
def sample(request):
    """Each sample app's module."""
    return load_sample(request.param)
