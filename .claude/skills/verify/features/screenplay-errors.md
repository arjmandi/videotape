# Screenplay errors

When a screenplay can't become a shot list, `videotape shots <dir>` prints one `error: ...` line to stderr naming the offending scene, label or file, prints nothing to stdout, and exits 1.

## Sub-features

- `errors-missing-scene` rejects an action whose target scene doesn't exist.
- `errors-unreachable` rejects a scene that no action reaches.
- `errors-duplicate-label` rejects two actions with one label in a scene, with the file and line of the repeat.
- `errors-two-screenplays` rejects a file that defines more than one `Screenplay`.
- `errors-no-screenplay` rejects a directory without `screenplay.py`.

## How to get to it (user POV)

- Run `videotape shots <dir>` on a screenplay with one of the mistakes above. Each has a fixture under `.claude/skills/verify/fixtures/`.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- The fixtures named below are unchanged from git.

- **Missing scene.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-missing-scene -- shots .claude/skills/verify/fixtures/missing-scene`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error: scene "home": action "Open settings" goes to missing scene "settings"`.
- **Unreachable scene.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-unreachable -- shots .claude/skills/verify/fixtures/unreachable`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error: no action reaches scene(s): attic`.
- **Duplicate label.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-duplicate-label -- shots .claude/skills/verify/fixtures/duplicate-label`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is `error: .claude/skills/verify/fixtures/duplicate-label/screenplay.py:5: scene "home" has two actions labelled "Continue"`.
- **Two screenplays.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-two-screenplays -- shots .claude/skills/verify/fixtures/two-screenplays`. `.exit` is `1` and `.stderr` ends with `must define exactly one Screenplay, found 2`.
- **No screenplay.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" errors-no-screenplay -- shots .claude/skills/verify/fixtures/no-screenplay`. `.exit` is `1` and `.stderr` is `error: no screenplay.py in .claude/skills/verify/fixtures/no-screenplay`.
- **Proof.** For each journey cite `.cmd`, `.exit`, `.stderr`, and `.screenplay.py` where one exists.

## Gotchas

- Exit code `2` with a `usage:` line means the arguments were wrong, not that the screenplay was rejected. Recheck the command.
- The duplicate-label check reads the file's source, so it fires only for a literal `actions={...}` dict passed to `.scene(...)`. A Python run of the same dict silently keeps the last entry, so never prove this journey by importing the screenplay.
- Error paths in stderr are the path you passed, relative or absolute. Pass the fixture path exactly as written here.
- A screenplay with several mistakes reports only the first one the walk reaches.
