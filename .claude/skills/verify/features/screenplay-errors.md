# Screenplay errors

When a screenplay has one of the mistakes videotape checks for, `videotape shots <dir>` prints one `error: ...` line to stderr naming the offending scene, label or file, prints nothing to stdout, and exits 1. `videotape render <dir> --model stand-in` rejects the same mistakes, plus one of its own, before it writes anything.

## Sub-features

- `errors-missing-scene` rejects an action whose target scene doesn't exist.
- `errors-unreachable` rejects a scene that no action reaches.
- `errors-duplicate-label` rejects two actions with one label in a scene, with the file and line of the repeat.
- `errors-two-screenplays` rejects a file that does not define exactly one `Screenplay`. The fixture defines two.
- `errors-no-screenplay` rejects a directory without `screenplay.py`.
- `errors-no-scenes` rejects a screenplay with no scenes.
- `errors-clip-collision` makes `render` reject two labels in one scene that would share one clip file, such as `Sign up` and `Sign-up`. `shots` accepts the same screenplay.

## How to get to it (user POV)

- Run `videotape shots <dir>` on a screenplay with one of the mistakes above. Each has a fixture under `.claude/skills/verify/fixtures/`.
- Run `videotape render <dir> --model stand-in` on a scene with two labels that differ only in punctuation.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- The fixtures named below are unchanged from git.

- **Missing scene.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-missing-scene -- shots .claude/skills/verify/fixtures/missing-scene`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error: scene "home": action "Open settings" goes to missing scene "settings"`.
- **Unreachable scene.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-unreachable -- shots .claude/skills/verify/fixtures/unreachable`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error: no action reaches scene(s): attic`.
- **Duplicate label.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-duplicate-label -- shots .claude/skills/verify/fixtures/duplicate-label`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error: .claude/skills/verify/fixtures/duplicate-label/screenplay.py:5: scene "home" has two actions labelled "Continue"`.
- **Two screenplays.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-two-screenplays -- shots .claude/skills/verify/fixtures/two-screenplays`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error: .claude/skills/verify/fixtures/two-screenplays/screenplay.py must define exactly one Screenplay, found 2`.
- **No screenplay.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-no-screenplay -- shots .claude/skills/verify/fixtures/no-screenplay`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error: no screenplay.py in .claude/skills/verify/fixtures/no-screenplay`.
- **No scenes.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-no-scenes -- shots .claude/skills/verify/fixtures/no-scenes`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error: the screenplay has no scenes`.
- **Clip collision.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-clip-collision -- render .claude/skills/verify/fixtures/clip-collision --model stand-in`. `.exit` is `1`, `.stdout` is empty, `.stderr` is `error: scene "home": actions "Sign up" and "Sign-up" would share the clip moves/home--sign-up.mp4`, and `.claude/skills/verify/fixtures/clip-collision/tape` does not exist.
- **Proof.** For each journey cite `.cmd`, `.exit`, `.stderr`, and `.screenplay.py` where one exists.

## Gotchas

- Exit code `2` with a `usage:` line means the arguments were wrong, not that the screenplay was rejected. Recheck the command.
- The duplicate-label check reads the file's source, so it fires only for a literal `actions={...}` dict passed to `.scene(...)`. A Python run of the same dict silently keeps the last entry, so never prove this journey by importing the screenplay.
- Error paths in stderr follow the directory you passed, relative or absolute. Pass the fixture path exactly as written here.
- A screenplay with several mistakes reports only one. A missing scene stops the walk, so a screenplay with a missing scene and an unreachable scene reports only the missing one. Keep one mistake per fixture.
- A Python error in `screenplay.py`, such as a misspelt name, exits 1 with a Python traceback and no `error:` line. That is not one of these journeys.
- `errors-clip-collision` drives `render`, not `shots`. `shots` on that fixture exits 0. If the fixture ever gains a `tape/` directory, the render got past the check.
