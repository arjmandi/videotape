"""A render draws every shot of a plan in a story into a tape. Each shot films one take at a time, seed by seed, and
stops at the first take that passes every check. Shots that do not depend on each other film at once, up to the
model's limit: every key is submitted first, and a move as soon as both of its keys are done. A model that bills per
call films under a cap. Every take on disk is reused, so a render run again resumes without paying for a take twice."""

import hashlib
import json
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, CancelledError, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path

from videotape import dailies, frames
from videotape.checks import Checks, Eye, Failure, score, seams
from videotape.dailies import Carried
from videotape.errors import RenderError, shown
from videotape.fal import FalError, Price, Receipt
from videotape.frames import Box, DecodeError, FfmpegError, Shape
from videotape.ledger import Ledger, now
from videotape.model import Model
from videotape.plan import Key, Move, Plan, Shot
from videotape.publish import partial, publish
from videotape.screenplay import State
from videotape.standin import StandInError
from videotape.story import Prompt, Story, prompt, text
from videotape.wan import WanError
from videotape.wan3 import RecordedFailure


@dataclass(frozen=True)
class Take:
    seed: int
    path: Path
    cached: bool
    checks: Checks
    seconds: float | None
    gpu: str | None
    usd: float | None


@dataclass(frozen=True)
class Filmed:
    shot: Shot
    prompt: Prompt
    takes: tuple[Take, ...]
    kept: Take
    reported: tuple[RenderError, ...] = ()
    """What went wrong on the way and was skipped: a corrupt take per seed in corrupt."""
    corrupt: tuple[int, ...] = ()

    @property
    def rendered(self) -> int:
        return sum(not take.cached for take in self.takes)

    @property
    def usd(self) -> float:
        """What this run paid for the shot."""
        return sum(take.usd or 0.0 for take in self.takes if not take.cached)

    @property
    def seconds(self) -> float:
        """What this run spent filming the shot."""
        return sum(take.seconds or 0.0 for take in self.takes if not take.cached)

    @property
    def passed(self) -> bool:
        return self.kept.checks.passed

    @property
    def failures(self) -> list[Failure]:
        return [Failure(item.code, self.shot.title, item.about, item.result, item.box)
                for item in self.kept.checks.failures]


@dataclass(frozen=True)
class Render:
    tape: Path
    keys: tuple[Filmed, ...]
    moves: tuple[Filmed, ...]
    seconds: float
    """The wall clock of the run."""

    @property
    def shots(self) -> tuple[Filmed, ...]:
        return *self.keys, *self.moves


class Budget:
    """What a render may still spend. One lock keeps the invariant: spent plus reserved never passes the cap, where
    spent is the sum of this tape's lines in the ledger and reserved is the price of every call in flight. Every ledger
    write goes through settle, under the same lock, and a request's line is written once. A call that fails keeps its
    reservation, since a submitted call may have been billed, and the render stops on it anyway."""

    def __init__(self, ledger: Ledger, price: Price | None, cap: float | None) -> None:
        self.ledger, self.price, self.cap = ledger, price, cap
        self.lock = threading.Lock()
        self.spent = ledger.totals()["usd"]
        self.reserved = 0.0

    def reserve(self, place: str, resume: str) -> None:
        """Hold the price of one call, or refuse when it would pass the cap."""
        if not self.price:
            return
        with self.lock:
            if self.cap is not None and self.spent + self.reserved + self.price.usd > self.cap:
                raise RenderError("VT402", place, f"the next call would pass the cap of ${self.cap:.2f}, with "
                                  f"${self.spent:.2f} spent on this tape and ${self.reserved:.2f} reserved for the "
                                  "calls in flight", f"raise the cap and run the render again, which resumes:\n{resume}")
            self.reserved += self.price.usd

    def settle(self, line: dict, reserved: bool) -> bool:
        """Record a finished call: its line goes into the ledger, unless the ledger holds its request already, and
        the price reserved for it is let go. Whether the line was written."""
        with self.lock:
            written = not self._holds(line.get("request_id"))
            if written:
                self.ledger.append(line)
                self.spent += line.get("usd") or 0.0
            if self.price and reserved:
                self.reserved -= self.price.usd
        return written

    def _holds(self, request_id: str | None) -> bool:
        return bool(request_id) and any(line.get("request_id") == request_id for line in self.ledger.lines())


@dataclass(frozen=True)
class _Set:
    """Everything every shot of one render shares."""

    model: Model
    eye: Eye
    tape: Path
    images: dict[State, Path]
    """Each state's key image, which the moves that leave or land on it are pinned to."""
    budget: Budget
    resume: str
    """The command that runs this render again."""
    stop: threading.Event
    """Set when the render stops on an error: a take in flight finishes and is recorded, and no new one starts."""
    locks: dict[Path, threading.Lock]
    """One lock per take name, so two shots that share a take film it once and the other reads it."""
    lock: threading.Lock

    def one_at_a_time(self, path: Path) -> threading.Lock:
        with self.lock:
            return self.locks.setdefault(path, threading.Lock())


class _Stopped(Exception):
    """A shot that did not film because the render had stopped."""


def render(plan: Plan, story: Story, model: Model, eye: Eye, tape: Path, ledger: Ledger, made: dict, takes: int = 4,
           limit: int = 1, price: Price | None = None, cap: float | None = None, resume: str = "videotape render",
           report: Callable[[Filmed], None] = lambda filmed: None) -> Render:
    """Draw a key for every state of the plan and a move for every action, each from the prompt the story gives it,
    and write them into the tape. made is the block that says what made the tape, which tape.json carries. report is
    told each shot as it finishes."""
    started = time.perf_counter()
    if price and cap is None:
        raise RenderError("VT402", "before the first call", f"{model.name} bills per call, and no cap is set",
                          f"set the most this render may spend, as in {resume} --cap-usd 20, or for good in "
                          "[tool.videotape]:\ncap_usd = 20")
    for folder in ("takes", "keys", "moves"):
        (tape / folder).mkdir(parents=True, exist_ok=True)
    carried = dailies.carried(tape)
    shared = _Set(model, eye, tape, {key.state: tape / key.image for key in plan.keys}, Budget(ledger, price, cap), resume,
                  threading.Event(), {}, threading.Lock())
    seeds = {shot.title: _seeds(shot, takes, carried) for shot in plan.shots}
    finished = dict[Shot, Filmed]()
    stopped: RenderError | None = None
    # Every key is submitted first. A move is submitted when both of its keys are done, since it is pinned to their
    # images. With one worker the keys all run before any move, so Wan 2.2 swaps its checkpoint once.
    with ThreadPoolExecutor(max_workers=limit) as pool:
        pending: dict[Future[Filmed], Shot] = {
            pool.submit(_film_key, shared, key, prompt(key, story), *seeds[key.title]): key for key in plan.keys}
        waiting = list(plan.moves)

        def stop() -> None:
            shared.stop.set()
            for other in pending:
                other.cancel()

        try:
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    shot = pending.pop(future)
                    try:
                        filmed = future.result()
                    except (CancelledError, _Stopped):
                        continue
                    except RenderError as error:
                        if stopped is None:
                            stopped = error
                            stop()
                        continue
                    finished[shot] = filmed
                    report(filmed)
                    if stopped is not None or not isinstance(shot, Key):
                        continue
                    ready = {key.state for key in plan.keys if key in finished}
                    for move in [move for move in waiting if {move.start, move.land} <= ready]:
                        waiting.remove(move)
                        pending[pool.submit(_film_move, shared, move, prompt(move, story), *seeds[move.title])] = move
        except BaseException:
            # Leaving the pool waits for every future, so a Ctrl-C or a worker's unexpected error would otherwise
            # run every queued shot. Cancelled, only the takes in flight finish, and they are settled.
            stop()
            raise
    elapsed = time.perf_counter() - started
    keys = tuple(finished[key] for key in plan.keys if key in finished)
    moves = tuple(finished[move] for move in plan.moves if move in finished)
    result = Render(tape, keys, moves, elapsed)
    corrupt = _corrupt(carried, result)
    if stopped is not None:
        dailies.write(tape, dailies.record(plan.title, eye.name, result, story, ledger.tape, corrupt, takes, False),
                      ledger.totals())
        raise stopped
    opening = result.keys[0].kept
    publish(tape / "moves" / "opening.mp4", lambda out: shutil.copyfile(opening.path, out))
    manifest = {**_manifest(plan, result), "made": made}
    publish(tape / "tape.json", lambda out: out.write_text(json.dumps(manifest, indent=2) + "\n"))
    dailies.write(tape, dailies.record(plan.title, eye.name, result, story, ledger.tape, corrupt, takes), ledger.totals())
    return result


def _seeds(shot: Shot, takes: int, carried: Carried) -> tuple[list[int], list[int]]:
    """The seeds a shot tries: 1 up to the limit, minus the seeds its record marks corrupt, and then the seeds a
    retake added."""
    corrupt, retakes = carried.corrupt.get(shot.title, []), carried.retakes.get(shot.title, [])
    return [seed for seed in range(1, takes + 1) if seed not in corrupt], [seed for seed in retakes if seed not in corrupt]


def _corrupt(carried: Carried, result: Render) -> Carried:
    """The record to carry on, with every seed found corrupt in this run added."""
    corrupt = {title: list(seeds) for title, seeds in carried.corrupt.items()}
    for filmed in result.shots:
        for seed in filmed.corrupt:
            if seed not in corrupt.setdefault(filmed.shot.title, []):
                corrupt[filmed.shot.title].append(seed)
    return Carried(carried.retakes, corrupt, carried.accepted)


def _film_key(shared: _Set, key: Key, clauses: Prompt, seeds: list[int], retakes: list[int]) -> Filmed:
    words = text(clauses)
    filmed = _film_shot(shared, key, clauses, seeds, retakes, lambda seed, out: shared.model.text_to_video(words, seed, out),
                        (), lambda path: score(frames.last_frame(path), key, shared.eye))
    # The key image is the kept take's last frame. The worker writes it, since the moves pinned to it wait for it.
    publish(shared.tape / key.image, lambda out: frames.write_png(frames.last_frame(filmed.kept.path), out))
    return filmed


def _film_move(shared: _Set, move: Move, clauses: Prompt, seeds: list[int], retakes: list[int]) -> Filmed:
    words = text(clauses)
    start, end = shared.images[move.start], shared.images[move.land]
    pinned = frames.read_png(start), frames.read_png(end)
    filmed = _film_shot(shared, move, clauses, seeds, retakes,
                        lambda seed, out: shared.model.first_last_frame(words, start, end, seed, out), (start, end),
                        lambda path: seams(frames.first_frame(path), frames.last_frame(path), *pinned))
    publish(shared.tape / move.clip, lambda out: shutil.copyfile(filmed.kept.path, out))
    return filmed


def _film_shot(shared: _Set, shot: Shot, clauses: Prompt, seeds: list[int], retakes: list[int],
               film: Callable[[int, Path], Receipt | None], images: tuple[Path, ...],
               check: Callable[[Path], Checks]) -> Filmed:
    """Film the shot's takes seed by seed. Each take comes from the cache or the model, then its checks. The seeds up
    to the limit are filmed until one passes, and a take on disk is always read. The retake seeds are filmed whatever
    passed before, and with them the shot keeps the best of all its takes."""
    words = text(clauses)
    takes, reported, corrupt = list[Take](), list[RenderError](), list[int]()
    passed = False
    try:
        for seed, always in [*((seed, False) for seed in seeds), *((seed, True) for seed in retakes)]:
            if passed and not always and not _cached(shared, shot, words, images, seed):
                continue
            if shared.stop.is_set():
                raise _Stopped()
            place = f"{shot.title} take {seed}"
            taken = _take(shared, shot, words, images, seed, place, film, check)
            if isinstance(taken, RenderError):
                reported.append(taken)
                corrupt.append(seed)
                continue
            takes.append(taken)
            passed = passed or taken.checks.passed
            if passed and not retakes:
                break
    except DecodeError as error:
        raise RenderError("VT404", f"{shot.title}", str(error), "delete the file it names and run the render again") \
            from None
    except FfmpegError as error:
        raise RenderError("VT404", f"{shot.title}", str(error),
                          "install ffmpeg, as in brew install ffmpeg, and run the render again") from None
    if not takes:
        raise RenderError("VT403", shot.title, "every take of the shot is corrupt",
                          f"raise takes in [tool.videotape] or pass --takes, or retake the shot: "
                          f'videotape retake "{dailies.named(shot)}"')
    return Filmed(shot, clauses, tuple(takes), min(takes, key=lambda take: take.checks.rank(take.seed)),
                  tuple(reported), tuple(corrupt))


def _take(shared: _Set, shot: Shot, words: str, images: tuple[Path, ...], seed: int, place: str,
          film: Callable[[int, Path], Receipt | None], check: Callable[[Path], Checks]) -> Take | RenderError:
    """One take and its checks, one shot at a time per take name, so two shots that share a take film it once. A
    take whose file does not decode is downloaded again from the request the model recorded beside it, and is VT403
    when it is still corrupt, or when the model recorded nothing to download again."""
    path = _take_path(shared.model, shot, words, images, seed, shared.tape)
    with shared.one_at_a_time(path):
        cached, timing = _film(shared, shot, path, seed, place, film)
        try:
            checks = check(path)
        except DecodeError as corrupt:
            if _downloaded_again(shared, path, place) is None:
                return RenderError("VT403", place, str(corrupt), f"nothing; seed {seed} is skipped from now on")
            try:
                checks = check(path)
            except DecodeError as again:
                return RenderError("VT403", place, f"downloaded again, and still: {again}",
                                   f"nothing; seed {seed} is skipped from now on")
    return Take(seed, path, cached, checks, timing.get("seconds"), timing.get("gpu"), timing.get("usd"))


def _downloaded_again(shared: _Set, path: Path, place: str) -> Receipt | None:
    """The take written again from the request the model recorded beside it, which submits nothing and costs
    nothing, or None when the model recorded none."""
    try:
        receipt = shared.model.download_again(partial(path))
    except (FalError, WanError, StandInError) as error:
        raise _failed(error, place, shared.resume) from None
    if receipt is not None:
        partial(path).replace(path)
    return receipt


def _failed(error: Exception, place: str, resume: str) -> RenderError:
    """VT401: a model call failed. A submitted request is recorded beside its take, so the next render polls it and
    never submits it again on its own; only deleting the record lets a render submit a new, paid take."""
    if isinstance(error, RecordedFailure):
        return RenderError("VT401", place, str(error), f"run the render again, which resumes; this request is "
                           f"polled, not submitted again:\n{resume}\nor delete {shown(error.record)} first, and the "
                           "render submits a new, paid take")
    return RenderError("VT401", place, str(error), f"run the render again, which resumes; a request that was "
                       f"submitted is polled, not submitted again:\n{resume}")


def _cached(shared: _Set, shot: Shot, words: str, images: tuple[Path, ...], seed: int) -> bool:
    return _take_path(shared.model, shot, words, images, seed, shared.tape).exists()


def _take_path(model: Model, shot: Shot, words: str, images: tuple[Path, ...], seed: int, tape: Path) -> Path:
    """A take's name hashes everything its pixels depend on: the mode, the prompt, the key images a move is pinned to,
    the model, the seed and the model's settings."""
    fields = [shot.mode.value, words, *(hashlib.sha256(image.read_bytes()).hexdigest() for image in images),
              model.name, seed]
    if settings := model.settings(shot.mode):
        fields.append(settings)
    return tape / "takes" / f"{hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()}.mp4"


def _film(shared: _Set, shot: Shot, path: Path, seed: int, place: str,
          film: Callable[[int, Path], Receipt | None]) -> tuple[bool, dict]:
    """Whether the take at path was already there, and its timing. A take that is not is downloaded again from the
    request the model recorded beside it, which costs nothing, else filmed, which reserves its price first. The render
    time and any price live in a sidecar next to the take, so they survive caching. A take the ledger already holds
    counts as cached."""
    timing = path.with_suffix(".json")
    if path.exists():
        return True, json.loads(timing.read_text()) if timing.exists() else {}
    started = time.perf_counter()
    receipt = _downloaded_again(shared, path, place)
    reserved = receipt is None
    if reserved:
        shared.budget.reserve(place, shared.resume)
        try:
            receipt = publish(path, lambda out: film(seed, out))
        except (FalError, WanError, StandInError) as error:
            raise _failed(error, place, shared.resume) from None
    filmed = {"seconds": round(time.perf_counter() - started, 3), "gpu": shared.model.device}
    if receipt:
        filmed |= {"request_id": receipt.request_id, "duration": receipt.duration, "usd": receipt.usd}
    written = shared.budget.settle({"kind": "take", "at": now(), "model": shared.model.name, "shot": shot.title,
                                    "mode": shot.mode.value, "seed": seed, **filmed}, reserved)
    response = {"response": receipt.response} if receipt else {}
    publish(timing, lambda out: out.write_text(json.dumps({**filmed, **response}) + "\n"))
    return not written, {**filmed, **response}


def _fraction(box: Box, size: Shape) -> dict:
    return {"x": round(box.x / size.width, 4), "y": round(box.y / size.height, 4),
            "w": round(box.w / size.width, 4), "h": round(box.h / size.height, 4)}


def _shape(result: Render) -> Shape:
    """The one size and frame rate every kept clip shares, which the player sizes its window to."""
    shapes = {filmed.kept.path: frames.shape(filmed.kept.path) for filmed in result.shots}
    if len(set(shapes.values())) > 1:
        raise FfmpegError("the kept clips differ in size or frame rate, so no one window plays them: " +
                          ", ".join(f"{path.name} {s.width}x{s.height} at {s.fps} fps" for path, s in shapes.items()))
    return next(iter(shapes.values()))


def _manifest(plan: Plan, result: Render) -> dict:
    """tape.json: one scene for each state, named as the plan names it, with its words, its hotspots and its search."""
    found = {filmed.shot.state: filmed.kept.checks.hotspots for filmed in result.keys}
    moves = {(move.start, move.label): move for move in plan.moves}
    size = _shape(result)
    scenes = {}
    for key in plan.keys:
        scene = {
            "key": key.image,
            "words": list(key.lines),
            # A hotspot needs a box, and a box is never invented, so an action the checks did not find has none.
            "hotspots": [{"label": action.label, "box": _fraction(box, size), "move": moves[(key.state, action.label)].id}
                         for action in key.actions if (box := found[key.state][action.label])],
        }
        if search := _search(key, moves):
            scene["search"] = search
        scenes[key.state.name] = scene
    return {
        "size": {"width": size.width, "height": size.height},
        "fps": size.fps,
        "opening": {"clip": "moves/opening.mp4", "lands": plan.keys[0].state.name},
        "scenes": scenes,
        "moves": {move.id: {"clip": move.clip, "lands": move.land.name} for move in plan.moves},
    }


def _search(key: Key, moves: dict[tuple[State, str], Move]) -> dict | None:
    """The search a state offers: its bar, every option with the move its press plays, and the move the bar plays
    when the typed text picks no option. Only a state that shows a search bar with options has one."""
    for element in key.shown:
        if element.type != "SearchBar" or len(element.rows) < 2:
            continue
        bar, options = element.rows[0][0][0], [row[0][0] for row in element.rows[1:]]
        if bar.action is None:
            continue
        no_match = moves[(key.state, bar.action.label)]
        return {
            "bar": bar.words,
            "options": [{"label": option.words, "move": moves[(key.state, option.action.label)].id}
                        for option in options if option.action],
            "no_match": {"move": no_match.id, "lands": no_match.land.name},
        }
    return None
