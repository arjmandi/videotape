"""A story is one look of an app: a TOML file under stories/ that says how the whole app, each scene and each element
type look, and how the camera moves when an element is pressed. The screenplay owns the words and a story owns the
looks, so a prompt is made of clauses, and each clause names where it came from."""

from __future__ import annotations

import hashlib
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

from videotape import errors
from videotape.errors import ScreenplayError
from videotape.model import PromptLimit
from videotape.plan import Key, Move, Plan, Shot
from videotape.project import ProjectError
from videotape.screenplay import Shown

DEFAULT = "default"


@dataclass(frozen=True)
class Story:
    name: str
    version: str
    look: str
    scenes: Mapping[str, str]
    """A direction for each scene, by the scene's name."""
    elements: Mapping[str, str]
    """An appearance for each element type, by its class name."""
    moves: Mapping[str, str]
    """A camera move for each element type, by its class name, and one for the rest, named default."""
    path: Path
    hash: str


@dataclass(frozen=True)
class Engine:
    def __str__(self) -> str:
        return "engine"


@dataclass(frozen=True)
class FromStory:
    part: str
    """look, or a table and its key, as in scenes.results."""

    def __str__(self) -> str:
        return f"story {self.part}"


@dataclass(frozen=True)
class FromScreenplay:
    scene: str
    element: str

    def __str__(self) -> str:
        return f"screenplay {self.scene}, {self.element}"


Source = Engine | FromStory | FromScreenplay


@dataclass(frozen=True)
class Clause:
    """One piece of a prompt, and where it came from."""

    text: str
    source: Source


Prompt = tuple[Clause, ...]

STATIC = Clause("Static shot.", Engine())
LETTERING = Clause("Sharp, legible lettering.", Engine())


def text(prompt: Prompt) -> str:
    return " ".join(clause.text for clause in prompt)


def prompt(shot: Shot, story: Story) -> Prompt:
    """The shot's prompt in this story. A key is the look, its scene's direction, then each element as its type's
    appearance and its own words. A move is the element that was pressed, then its type's move."""
    match shot:
        case Key():
            return _key(shot, story)
        case Move():
            return _move(shot, story)


def _key(key: Key, story: Story) -> Prompt:
    scene = key.state.scene.name
    clauses = [STATIC, Clause(story.look, FromStory("look"))]
    if scene in story.scenes:
        clauses.append(Clause(story.scenes[scene], FromStory(f"scenes.{scene}")))
    for element in key.shown:
        appearance = story.elements.get(element.type)
        reading = _reading(element) if element.lines else None
        if appearance:
            ends = "," if reading else "."
            clauses.append(Clause(f"{_capital(appearance)}{ends}", FromStory(f"elements.{element.type}")))
        if reading:
            clauses.append(Clause(reading if appearance else _capital(reading), FromScreenplay(scene, element.type)))
    return *clauses, LETTERING


def _move(move: Move, story: Story) -> Prompt:
    pressed = Clause(f'The {move.action.kind} "{move.action.words}" is pressed.',
                     FromScreenplay(move.start.scene.name, move.element))
    told = next((name for name in (move.element, DEFAULT) if name in story.moves), None)
    return (pressed, Clause(story.moves[told], FromStory(f"moves.{told}"))) if told else (pressed,)


def _reading(shown: Shown) -> str:
    """An element's words as a prompt quotes them, each line once and in reading order. A label and its value sit side
    by side, a row's cells are listed with commas, and rows with semicolons."""
    rows = [_listed([" ".join(f'"{line.words}"' for line in cell) for cell in row], ",") for row in shown.rows]
    chosen = "".join(f', with "{line.words}" chosen' for line in shown.lines if line.chosen)
    return f"reading {_listed(rows, ';')}{chosen}."


def _listed(items: Sequence[str], mark: str) -> str:
    """Items as English lists them, with the mark between them and "and" before the last. Two items that commas would
    join take none, as in a and b."""
    if len(items) < 2:
        return "".join(items)
    last = " and " if mark == "," and len(items) == 2 else f"{mark} and "
    return f"{mark} ".join(items[:-1]) + last + items[-1]


def _capital(words: str) -> str:
    return words[:1].upper() + words[1:]


def named(root: Path, name: str) -> Story:
    """The project's story of this name, which is stories/<name>.toml."""
    path = root / "stories" / f"{name}.toml"
    if not path.is_file():
        have = sorted(found.stem for found in path.parent.glob("*.toml"))
        raise ProjectError(f'no story "{name}" in {errors.shown(path.parent)}; ' + (
            f"the stories are {' and '.join(have)}" if have else f"add {errors.shown(path)}"))
    return load(path)


def load(path: Path) -> Story:
    """Read a story's file. Its words are checked to be words here, so nothing after this checks them again."""
    place, raw = errors.shown(path), path.read_bytes()
    try:
        told = tomllib.loads(raw.decode())
    except tomllib.TOMLDecodeError as error:
        line, wrong = _toml_error(error, raw.decode())
        raise ScreenplayError("VT306", f"{place}:{line}", f"the story is not TOML: {wrong}",
                              'write each line as name = "words", under [scenes], [elements] or [moves], or above '
                              "all three") from None
    version = _top(told, "version", place, '"1.0.0"')
    look = _top(told, "look", place, '"...", the look of the whole app in a sentence or two,')
    tables = dict[str, dict[str, str]]()
    for table in ("scenes", "elements", "moves"):
        held = told.get(table, {})
        if not isinstance(held, dict) or not all(isinstance(words, str) for words in held.values()):
            raise ProjectError(f'{place}: [{table}] holds something other than words, as in name = "..."')
        tables[table] = {name: _plain(words) for name, words in held.items()}
    return Story(path.stem, version, look, tables["scenes"], tables["elements"], tables["moves"], path,
                 hashlib.sha256(raw).hexdigest())


def _top(told: dict, name: str, place: str, example: str) -> str:
    words = told.get(name)
    if isinstance(words, str) and words.strip():
        return _plain(words)
    wrong = f"no {name}" if words is None or isinstance(words, str) else f"the {name} {words!r}, which is not in quotes"
    raise ScreenplayError("VT301", place, f"the story has {wrong}", f"write {name} = {example} above the first [heading]")


def check(story: Story, plan: Plan, limit: PromptLimit | None) -> tuple[ScreenplayError, ...]:
    """Check a story against the app it gives a look to, and its prompts against the longest one the model reads.
    An error is raised, and the warnings are returned."""
    place = errors.shown(story.path)
    for name in story.scenes:
        if name not in plan.scenes:
            raise ScreenplayError("VT302", _at(story.path, "scenes", name),
                                  f"the story directs the scene {name}, and the screenplay has no scene of that name",
                                  _closest(name, plan.scenes, "scenes"))
    used = sorted({element.type for key in plan.keys for element in key.shown})
    for table, gives in (("elements", "an appearance"), ("moves", "a move")):
        for name in getattr(story, table):
            if name not in used and (table, name) != ("moves", DEFAULT):
                raise ScreenplayError("VT303", _at(story.path, table, name),
                                      f"the story gives {gives} to the element type {name}, which the screenplay "
                                      "does not use", _closest(name, used, "element types"))
    warnings = [ScreenplayError("VT304", place, f"the scene {name} has no direction, so its keys get only the look",
                                f'add {name} = "..." under [scenes]')
                for name in plan.scenes if name not in story.scenes]
    if limit:
        lengths = {shot: limit.count(text(prompt(shot, story))) for shot in plan.shots}
        warnings += [ScreenplayError("VT307", shot.title, f"the prompt is {limit.says.format(length)} long, and "
                                     f"{limit.model} takes no more than {limit.most:,}",
                                     f"shorten the look, the scene's direction or the appearances in {place}, or show "
                                     "fewer lines in this state")
                     for shot, length in lengths.items() if length > limit.most]
    return tuple(warnings)


def _plain(words: str) -> str:
    """Words on one line, so a look written over several lines reads as one sentence after another."""
    return " ".join(words.split())


def _toml_error(error: tomllib.TOMLDecodeError, document: str) -> tuple[int, str]:
    """The line a TOML error is at, and what is wrong there. Python 3.14 gives both. Python 3.12 gives one message
    that ends with the place."""
    said = re.fullmatch(r"(?s)(.*) \(at (?:line (\d+), column \d+|end of document)\)", str(error))
    wrong = getattr(error, "msg", None) or (said[1] if said else str(error))
    line = getattr(error, "lineno", None) or (int(said[2]) if said and said[2] else len(document.splitlines()))
    return line, wrong


def _at(path: Path, table: str, name: str) -> str:
    """The file and line of a table's key. tomllib keeps no line numbers, so this reads the file again, and names only
    the file for a key that is written in another way than under its [heading]."""
    inside = False
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if heading := re.fullmatch(r"\s*\[\s*([^\]]+?)\s*\]\s*(#.*)?", line):
            inside = heading[1] == table
        elif inside and re.match(rf"""\s*["']?{re.escape(name)}["']?\s*=""", line):
            return f"{errors.shown(path)}:{number}"
    return errors.shown(path)


def _closest(name: str, real: Sequence[str], kind: str) -> str:
    close = get_close_matches(name, real, n=1)
    return f"write {close[0]}, the closest of the screenplay's {kind}" if close else \
        f"name one of the screenplay's {kind}: {', '.join(real)}"
