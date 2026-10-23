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
CLEAN = FIXTURES / "clean"
"""Apps that check clean because of a rule's exception, one per exception."""


def load_module(directory: Path, module: str):
    """Imports `module` from `directory` as the CLI would. Modules stay loaded, as in an app, since
    annotations are read lazily; fixture module names are therefore unique across directories."""
    loaded = sys.modules.get(module)
    if loaded is not None:
        if Path(loaded.__file__).parent != directory:
            raise RuntimeError(f"two fixtures are named {module}: {loaded.__file__} and {directory}")
        return loaded
    sys.path.insert(0, str(directory))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.remove(str(directory))


def load_sample(name: str):
    directory, module = SAMPLES[name]
    return load_module(directory, module)


def load_broken(name: str):
    return load_module(BROKEN, name)


def load_clean(name: str):
    return load_module(CLEAN, name)


@pytest.fixture(params=sorted(SAMPLES))
def sample(request):
    """Each sample app's module."""
    return load_sample(request.param)
