"""Every error a screenplay, its data, a story, a render or a check can have: its code, what it means, an example,
and the fix or the next step."""

import os
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from types import FrameType, TracebackType

PACKAGE = Path(__file__).parent


@dataclass(frozen=True)
class Code:
    title: str
    long: str
    example: str
    fix: str


CODES: dict[str, Code] = {
    "VT101": Code(
        "Python is older than videotape needs",
        "videotape runs on the Python its package names in requires-python. doctor compares the Python it runs on "
        "with that. uv picks a Python that fits when it makes a project's environment, so this happens to an "
        "environment made by hand, or with an older Python named.",
        "fail VT101 Python 3.11.4, and videotape needs >=3.12",
        "make the project's environment with a newer Python, as in uv sync --python 3.12",
    ),
    "VT102": Code(
        "ffmpeg or ffprobe is not on PATH",
        "A render decodes takes, writes key images and copies clips with ffmpeg, and reads clips with ffprobe. doctor "
        "looks for both on PATH. A render without them stops at its first take with VT404.",
        "fail VT102 ffprobe is not on PATH",
        "install ffmpeg, which brings ffprobe, as in brew install ffmpeg",
    ),
    "VT103": Code(
        "Xcode is missing, so TapePlayer cannot build",
        "play and publish build TapePlayer, the macOS app that plays a tape, from the Swift source videotape carries. "
        "The build needs Xcode itself, with xcode-select pointing at it. The Command Line Tools alone have no "
        "xcodebuild that builds an app, and play stops with VT603.",
        "fail VT103 xcode-select points at /Library/Developer/CommandLineTools, the Command Line Tools without Xcode, "
        "so TapePlayer cannot build",
        "install Xcode from the App Store, then point xcode-select at it, as in "
        "sudo xcode-select --switch /Applications/Xcode.app",
    ),
    "VT104": Code(
        "an API key the project's model needs is not set",
        "A model that runs as a service needs its API key: wan3.0 runs on fal and needs FAL_KEY. A project command "
        "reads API keys from the environment and from the project's .env, one KEY=VALUE line each, and an API key "
        "already in the environment wins. No command prints an API key's value. The stand-in and wan2.2-5b run here "
        "and need none.",
        "fail VT104 wan3.0 needs FAL_KEY, and it is not in the environment or .env",
        "copy .env.example to .env and set FAL_KEY there, or export it",
    ),
    "VT105": Code(
        "the checks need a GPU this machine does not have",
        "After a render films a key, an eye reads it back to check every line and find every action. The eye of the "
        "Wan models is Qwen3-VL-8B, which runs on Apple silicon or a CUDA GPU. The stand-in's eye reads its own boxes "
        "and needs neither.",
        "fail VT105 wan3.0's checks need Apple silicon or a CUDA GPU, and this machine is Linux on x86_64 without "
        "nvidia-smi",
        "render on a Mac with Apple silicon or a machine with a CUDA GPU, or with the stand-in, as in "
        "videotape render --story starter --model stand-in",
    ),
    "VT106": Code(
        "no project here",
        "A project is the folder that holds an app's pyproject.toml, with a [tool.videotape] table that names the "
        "app's screenplay. Every command but new, doctor, explain and diff runs in a project, and finds it from the "
        "working folder upward. Neither this folder nor any above it holds a pyproject.toml, or the nearest one has "
        "no [tool.videotape] table.",
        "error VT106 pyproject.toml: no pyproject.toml here or in any folder above",
        "run the command in the app's project, or start one:\nvideotape new shop\nor add the table to the project's "
        'pyproject.toml:\n[tool.videotape]\nscreenplay = "shop.screenplay:app"',
    ),
    "VT107": Code(
        "a value in [tool.videotape] is wrong",
        "[tool.videotape] in the project's pyproject.toml names the screenplay as module:name, the module that holds "
        "it and the name of its vt.Screenplay. It may set model, one of the models videotape has, max_states and "
        "takes, whole numbers of at least 1, and cap_usd, a number of dollars. A value here is none of what its "
        "setting takes, the screenplay it names is not a vt.Screenplay in the project, or the file is not TOML. The "
        "error names the setting and what it holds.",
        'error VT107 pyproject.toml: [tool.videotape] model is "wan3", and videotape has no such model',
        "set each to what it takes:\n[tool.videotape]\n"
        'screenplay = "shop.screenplay:app"\nmodel = "wan3.0"\ntakes = 4\ncap_usd = 20',
    ),
    "VT201": Code(
        "the screenplay has no scenes",
        "The app opens on the state of the screenplay's first scene, called with no arguments. A screenplay with no "
        "scenes has nothing to open on, and neither does one whose first scene needs arguments.",
        'app = vt.Screenplay("Shop")',
        '@app.scene\ndef home():\n    return [vt.Heading("Shop")]',
    ),
    "VT202": Code(
        "a to= holds something other than a state",
        "An action leads to a state, and calling a scene names one. A to=, a no_match=, or a tab that holds anything "
        "else, such as the scene itself or its name, leads nowhere.",
        'vt.Button("Open", to=detail)',
        'vt.Button("Open", to=detail(item))',
    ),
    "VT203": Code(
        "a scene raised",
        "The plan builds every state by calling its scene with the state's arguments. This scene raised an exception "
        "for these arguments, or returned something other than a list of elements, so its state cannot be drawn. The "
        "error names the state and the line.",
        '@app.scene\ndef receipt(order: Order):\n    return [vt.Text(f"${order.total // order.guests} each")]',
        "Handle every value the data holds, here an order with no guests, or keep that state out of every to=.",
    ),
    "VT204": Code(
        "no action reaches a scene",
        "Every state is reached by actions, starting from the first scene. No action in any reached state leads to "
        "this scene, so nobody using the app could get to it and it would never be drawn.",
        '@app.scene\ndef home():\n    return [vt.Heading("Shop")]\n\n\n@app.scene\ndef help():\n'
        '    return [vt.Text("Call us.")]',
        'Lead to it from a scene that is reached, as in vt.Button("Help", to=help()), or delete it.',
    ),
    "VT205": Code(
        "a data file is missing, or is not under data/",
        "vt.table and vt.one load their file when the module is imported. A path is relative to the project, the "
        "folder that holds pyproject.toml, and it is under data/, so that the data hash in a tape's made block covers "
        "every record the app loads. Either no file is at this path, or the path leads outside data/.",
        'flights = vt.table(Flight, "flights.json")',
        'flights = vt.table(Flight, "data/flights.json")',
    ),
    "VT206": Code(
        "a record is not what its class says",
        "A table's file holds a JSON array of objects, and vt.one's file holds one object. Each object has exactly "
        'the fields of its record class, and each value has its field\'s type: a string, a whole number, a date '
        'written like "2026-12-11", or a time written like "07:05". The fields that key= names identify a record, so '
        "no two records in a table share them. The error names the file, the record's position, and the field.",
        '{"number": "CT 100", "day": "12/11/2026", "fare": "219"}',
        '{"number": "CT 100", "day": "2026-12-11", "fare": 219}',
    ),
    "VT207": Code(
        "a query names a field its records don't have",
        "where, order_by, get, distinct, min, and sum take the names of a record's fields, and so does key=. This "
        "name is not one of them. The error lists the fields the records do have.",
        'flights.where(dest="SEA")',
        'flights.where(destination="SEA")',
    ),
    "VT208": Code(
        "first() or get() matched no row, or get() matched several",
        "first() returns a table's first row, and get() returns the one row that matches. An empty table has no "
        "first row, and get() needs exactly one match.",
        'airports.get(code="XXX")',
        "Ask for a row the data holds, or count the matches with where(...).count() and show something else when "
        "there are none.",
    ),
    "VT209": Code(
        "two actions in one state have one label",
        "An action is found on its key by its words and pressed by its hotspot's label, so each action in a state "
        "needs its own. Two here share one, and only the first could ever be pressed.",
        'vt.Button("Open", to=inbox()), vt.Button("Open", to=archive())',
        'vt.Button("Open inbox", to=inbox()), vt.Button("Open archive", to=archive())',
    ),
    "VT210": Code(
        "the plan reached more states than max_states",
        "The plan walks every state the app can reach, and a render draws each one. It stopped when it passed "
        "max_states, which is 500 unless [tool.videotape] sets it. Usually a scene's argument grows without end, "
        "such as a counter that every state passes on plus one.",
        '@app.scene\ndef count(n: int):\n    return [vt.Button("More", to=count(n + 1))]',
        "Take a scene's arguments from the data, which ends. If the app really has more states, raise the limit:\n"
        "[tool.videotape]\nmax_states = 2000",
    ),
    "VT211": Code(
        "a line is hard to letter",
        "A warning. A video model letters short, plain lines best. This line has more than 12 words, or a character "
        "other than plain ASCII letters, digits, spaces, and . , ' ? ! $ % ( ) : -. The plan goes on, and the line "
        "may come out misspelt in a take.",
        'vt.Text("Café Lumière opens at 7 & closes at 9")',
        'vt.Text("Cafe Lumiere opens at 7 and closes at 9")',
    ),
    "VT301": Code(
        "a story has no version or no look",
        "A story is one file under stories/, and it opens with its version and its look. The look is the sentence or "
        "two that every key's prompt starts from, and a tape's label names the story by its version. Both are words "
        "in quotes above the first [heading], because a line under a heading belongs to that heading's table.",
        '[scenes]\nhome = "The main hall."\nlook = "A quiet airport terminal at first light."',
        'version = "1.0.0"\nlook = "A quiet airport terminal at first light."\n\n[scenes]\nhome = "The main hall."',
    ),
    "VT302": Code(
        "a story directs a scene the screenplay doesn't have",
        "Under [scenes] a story gives a scene its direction, by the scene's name, which is the name of its function "
        "in the screenplay. No scene has this name, so no key would ever get the direction. The error names the "
        "line, and the fix names the closest real scene.",
        '[scenes]\nresult = "The departure board, showing one day\'s flights."',
        '[scenes]\nresults = "The departure board, showing one day\'s flights."',
    ),
    "VT303": Code(
        "a story names an element type the screenplay doesn't use",
        "Under [elements] a story gives an element type its appearance, and under [moves] its camera move, by the "
        "type's class name, such as Button or DateStrip. An Option takes those of its SearchBar, DatePicker or "
        "DateStrip, and a Row those of its List. No state of this app shows an element of this type, so the words "
        "would never be used. [moves] may also hold default, the move of every type without its own. The error names "
        "the line, and the fix names the closest type the app does show.",
        '[elements]\nButon = "a lit amber panel with bold black letters"',
        '[elements]\nButton = "a lit amber panel with bold black letters"',
    ),
    "VT304": Code(
        "a scene has no direction",
        "A warning. A key's prompt is the story's look, then its scene's direction, then each element it shows. This "
        "story directs other scenes and not this one, so each of this scene's keys gets only the look, and nothing "
        "sets its place apart from the rest of the app. The plan goes on.",
        '[scenes]\nhome = "The main hall, facing the big departure board."',
        '[scenes]\nhome = "The main hall, facing the big departure board."\n'
        'search = "Up close at the departure board."',
    ),
    "VT305": Code(
        "the tape's label is published already, as another tape",
        "A tape's label names the app and the story, each by its version, as in contrail 0.1.0 + starter 1.0.0, and "
        "its id hashes everything that made it. Publish records the label and id of each app it ships in "
        "videotape.lock, at the project's root, which the project commits. This tape's label is in the lock with "
        "another id: the code, the data, the story, the model or videotape changed, and neither version did, so two "
        "different apps would ship under one name. Publish ships nothing.",
        "error VT305 videotape.lock: contrail 0.1.0 + starter 1.0.0 was published as 3f9a0c1d2e4b, and this tape "
        "under the same label is 7b2e9d4c1a0f: the data changed",
        "fix: give the tape a label of its own: bump version in pyproject.toml, or in stories/starter.toml for a "
        "change to the story, then render and publish again",
    ),
    "VT306": Code(
        "a story is not TOML, or a table holds something other than words",
        'A story is a TOML file: lines of name = "words", above and under the headings [scenes], [elements] and '
        "[moves]. This file breaks TOML's rules, most often with words that are not in quotes or a quote that never "
        "closes, or one of its tables holds a number, a list or another table where words belong. The error names "
        "the line and says what is there.",
        "look = A quiet airport terminal at first light.\n\n[scenes]\nhome = 3",
        'look = "A quiet airport terminal at first light."\n\n[scenes]\nhome = "The main hall."',
    ),
    "VT307": Code(
        "a prompt is longer than the model takes",
        "A warning. A model takes a prompt up to a limit. Wan 2.2 reads 512 tokens and drops the rest without saying "
        "so, and a key's prompt ends with the elements at the bottom of its state, so those are the ones it would "
        "never draw. The plan has no tokenizer, so it counts high: one token for every four letters of a word, one "
        "for every other character that is not a space, and one for the end. Wan 3.0 on fal takes 20,000 characters. "
        "The stand-in has no limit. The plan goes on.",
        'look = """\nA quiet international airport terminal at first light, and four hundred more words.\n"""',
        "Shorten the look, the scene's direction or the appearances in the story, or show fewer lines in the state.",
    ),
    "VT308": Code(
        "a story quotes words",
        "The screenplay owns every word on screen, and a story says only how they look. A video model letters "
        "whatever a prompt quotes, so a story that quotes words puts them on every key it reaches, beside the "
        "screenplay's own. A straight double quote or a curly one anywhere in a story's words is this error, which "
        "names the line.",
        'SearchBar = "a white slot that says \\"Where to?\\" in black letters"',
        'SearchBar = "a wide white slot with black letters"',
    ),
    "VT309": Code(
        "no story has this name",
        "A story is stories/<name>.toml in the project, and --story names it by the file's stem. No file under "
        "stories/ has this name. The fix lists the stories that are there, or names the file to add when there are "
        "none.",
        "videotape plan --story poster",
        "videotape plan --story posters",
    ),
    "VT401": Code(
        "a model call failed",
        "A render asks the model for one take at a time, and this call did not come back with a clip. The error "
        "prints the provider's message and the request id when there is one, and never an API key. The takes already on "
        "disk and the requests already submitted are kept, so running the render again resumes from them, and a "
        "submitted request is polled and downloaded, never submitted again on its own. A request fal has recorded "
        "beside its take and refuses for good, as when its safety checker flags the output, fails the same way on "
        "every run, so the next step names its record: deleting that file lets the render submit a new, paid take.",
        "error VT401 key home() take 2: result of alibaba/wan-3.0/text-to-video request 01a1... failed with HTTP 422",
        "next: run the render again, which resumes; this request is polled, not submitted again:\n"
        "videotape render --story terminal --model wan3.0 --cap-usd 20.00\n"
        "or delete tapes/terminal/takes/3f9a....request.json first, and the render submits a new, paid take",
    ),
    "VT402": Code(
        "the next call would pass the cap",
        "A model that bills per call renders under a cap: cap_usd in [tool.videotape], or --cap-usd. What a tape has "
        "spent is the sum of its lines in the project's ledger, so running the render again never resets it. Before "
        "each paid call the render stops when the call would pass the cap, says what was spent, and lets the calls "
        "in flight finish and be recorded. The cap is checked against each call's listed price, and the ledger "
        "records what the call then billed, which can differ a little, so the spend can end a little past the cap. "
        "A paid model with no cap at all does not start.",
        "error VT402 key search() take 1: the next call would pass the cap of $5.00, with $4.54 spent on this tape "
        "and $0.00 reserved for the calls in flight, at the listed price of $0.50 a call",
        "next: run the render again with a higher cap, which resumes, as in:\n"
        "videotape render --story terminal --cap-usd 10.00",
    ),
    "VT403": Code(
        "a take's file is corrupt",
        "A take came back as a file that does not decode into a frame. A model that bills per call keeps its request "
        "beside the take, so the take is downloaded again first. When it is still corrupt, or when the model has "
        "nothing to download again, the seed is recorded in the tape's record as corrupt, reported, skipped, and "
        "never filmed again. The shot goes on with its next seed.",
        "error VT403 key home() take 1: tapes/terminal/takes/3f9a....mp4 did not decode to one frame: Error opening "
        "input files: Invalid data found when processing input",
        "next: nothing; seed 1 is skipped from now on",
    ),
    "VT404": Code(
        "ffmpeg failed",
        "A render decodes frames, writes key images and copies clips with ffmpeg and ffprobe, and one of them "
        "failed or is not on PATH. The error prints the command and what ffmpeg said. This is about the machine, "
        "not the model or the screenplay.",
        "error VT404 key home(): ffmpeg is not on PATH",
        "next: install ffmpeg, as in brew install ffmpeg, and run the render again",
    ),
    "VT501": Code(
        "an action was not found on its key",
        "Every action of a state is found on the state's key by its words, and its box becomes the hotspot a "
        "person presses. The eye found no box reading these words, within the character error the find allows, "
        "on the kept take, so the action has no hotspot in the tape and cannot be pressed. The dailies show where "
        "the box should be, from another take that found it when there is one.",
        'vt.Button("Book for $89", to=booked(f)), with no box reading "Book for $89" on the key',
        "retake the shot, change the story line that draws the element, change the screenplay, or accept it with a "
        "reason",
    ),
    "VT502": Code(
        "a word was misread",
        "Every line of a state is read back from its key, and a line reads back exactly or the check fails. The "
        "character error rate says how far off it was, and the dailies show the line's box when the eye saw one.",
        'vt.Text("Confirmation 7F2K9Q"), read back as "Confirmation 7F2K90"',
        "retake the shot, shorten or simplify the line in the screenplay, or accept it with a reason",
    ),
    "VT503": Code(
        "the model invented a control",
        "The kept take shows a control-like box whose words are none of the state's lines, so a person would try "
        "to press something the app does not have. The eye lists every control-like box with its text, and one is "
        "invented when its text matches no line within the character error the find allows.",
        'a lit panel reading "Cancel" on a key whose state has no such line',
        "retake the shot, change the story's appearance for the element type that drew it, or accept it with a "
        "reason, as in --reason \"a printed logo, not a control\"",
    ),
    "VT508": Code(
        "a seam between a move and its key is too wide",
        "A move is drawn from the key it leaves to the key it lands on, and its first and last frames are compared "
        "with those two keys. A difference over 0.05 at either end is a visible jump when the tape plays. The "
        "dailies name which end and by how much.",
        "end: difference 0.279, when the move's last frame is far from the key it lands on",
        "retake the move, change the story's move for that element type, or accept it with a reason",
    ),
    "VT601": Code(
        "the tape is out of date with its sources",
        "tape.json's made block hashes everything that made the tape: the app's code and data, the story, the model's "
        "settings and videotape itself, with an id that hashes them all. Publish makes the block again from the "
        "project as it is now, for the tape's story and model, and compares the two ids. They differ, so the app "
        "would ship a tape drawn from sources the project no longer has. The error says what changed. A render that "
        "stopped before its last shot also leaves its tape out of date. Publish ships nothing.",
        "error VT601 tapes/starter: the app's code changed since the tape was rendered",
        "fix: render the tape again with the model that made it, then publish it:\n"
        "videotape render --story starter --model stand-in",
    ),
    "VT602": Code(
        "the tape has failing checks nobody accepted",
        "Every key and move of a tape is checked when it renders. A check its kept take fails stays failing until a "
        "retake passes it or a person accepts it with a reason, and an accept holds only for the take it was given "
        "on. Publish reads the tape's dailies.json and ships nothing while a failure there is not accepted.",
        "error VT602 tapes/starter: 1 check fails that nobody accepted: key todo() VT503",
        "fix: look at it with videotape dailies --story starter, then retake the shot or accept the failure with a "
        "reason; for the first:\nvideotape retake \"todo()\" --story starter\n"
        "videotape accept \"todo()\" VT503 --story starter --reason \"...\"",
    ),
    "VT603": Code(
        "TapePlayer did not build",
        "play and publish build TapePlayer, the macOS app that plays a tape, from the Swift source videotape carries. "
        "It builds in Release with xcodebuild, in a cache under ~/Library/Caches/videotape, or VIDEOTAPE_CACHE_DIR "
        "when that is set, once for each version of the source. This build did not finish, so nothing was cached. The "
        "error names the build's log, which holds everything xcodebuild printed, and quotes its first error.",
        "error VT603 ~/Library/Caches/videotape/player/3f9a0c1d2e4b5a67/build.log: the build exited with 1: "
        "xcode-select: error: tool 'xcodebuild' requires Xcode, but active developer directory "
        "'/Library/Developer/CommandLineTools' is a command line tools instance",
        "run videotape doctor, which checks for Xcode; when it passes, the log says what failed",
    ),
    "VT604": Code(
        "a check fails on the HEVC frame the player rests on",
        "Publish encodes each clip of the tape as HEVC, which makes a Wan tape's app smaller than the clips a render keeps."
        " A clip's last frame is where the player rests until the next press, so publish reads each encoded "
        "clip's last frame, runs the tape's eye on it against the state the clip lands on, and compares it with that "
        "state's key image. A check that passed on the key and fails on this frame means the encoding lost what the "
        "check needs. Publish ships nothing.",
        "error VT604 moves/home--see-the-steps.mp4: its HEVC last frame, where the player rests on todo(), fails 2 "
        "checks its key passed, the first VT501 Back: not found",
        "fix: retake the shot, whose next take may come through the encoding, then publish again:\n"
        "videotape retake \"home() -> todo()\" --story starter",
    ),
}


class ScreenplayError(Exception):
    """One logical error: its code, the place it is at, what is wrong there, and the fix."""

    def __init__(self, code: str, place: str, message: str, fix: str) -> None:
        if code not in CODES:
            raise KeyError(f"{code} has no entry in CODES, so videotape explain could not explain it")
        super().__init__(f"{code} {place}: {message}")
        self.code, self.place, self.message, self.fix = code, place, message, fix

    def report(self, level: str = "error") -> str:
        return f"{level} {self.code} {self.place}: {self.message}\nfix: {self.fix}"

    def in_state(self, state: str) -> "ScreenplayError":
        return ScreenplayError(self.code, self.place, f"{self.message}, in state {state}", self.fix)


class RenderError(Exception):
    """One error a render stops on, or reports and goes on from: its code, the shot and take it is at, what went
    wrong, and the next step."""

    def __init__(self, code: str, place: str, message: str, next: str) -> None:
        if code not in CODES:
            raise KeyError(f"{code} has no entry in CODES, so videotape explain could not explain it")
        super().__init__(f"{code} {place}: {message}")
        self.code, self.place, self.message, self.next = code, place, message, next

    def report(self) -> str:
        return f"error {self.code} {self.place}: {self.message}\nnext: {self.next}"


def explain(code: str) -> str:
    entry = CODES[code]
    what = "Next" if "VT400" <= code < "VT600" else "Fix"
    return (f"{code}: {entry.title}\n\n{entry.long}\n\nExample:\n{_indented(entry.example)}\n\n"
            f"{what}:\n{_indented(entry.fix)}")


def _indented(text: str) -> str:
    return "\n".join(f"    {line}" if line else "" for line in text.splitlines())


def shown(path: str | Path) -> str:
    """A path as an error names it: relative to the working directory when it is inside it."""
    path = Path(path)
    return os.path.relpath(path) if path.is_relative_to(Path.cwd()) else str(path)


LIBRARIES = tuple({sysconfig.get_path(name) for name in ("stdlib", "platstdlib", "purelib", "platlib")})


def _own(filename: str) -> bool:
    # A dataclass's generated __init__ reports the file "<string>".
    return filename.startswith("<") or Path(filename).parent == PACKAGE


def origin() -> tuple[Path, int]:
    """The file and line of the nearest caller outside videotape, which is where the developer's code asked."""
    frame: FrameType = sys._getframe(1)  # pyright: ignore[reportPrivateUsage]
    while frame.f_back is not None and _own(frame.f_code.co_filename):
        frame = frame.f_back
    return Path(frame.f_code.co_filename), frame.f_lineno


def here() -> str:
    path, line = origin()
    return f"{shown(path)}:{line}"


def raised(traceback: TracebackType | None, fallback: tuple[str, int]) -> str:
    """The deepest line of the developer's own code that an exception passed through, or the fallback."""
    place = fallback
    while traceback is not None:
        filename = traceback.tb_frame.f_code.co_filename
        if not _own(filename) and not filename.startswith(LIBRARIES):
            place = (filename, traceback.tb_lineno)
        traceback = traceback.tb_next
    return f"{shown(place[0])}:{place[1]}"
