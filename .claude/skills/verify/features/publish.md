# Publish

A developer who has rendered a tape runs `videotape publish --story <name>` in the project, or `--out <tape>` for a tape that `render --out` wrote, and gets a Mac app that plays the tape on its own: `dist/<Title>-<story>.app`, where Title is the screenplay's title, zipped beside it as `dist/<Title>-<story>.zip`. The app is TapePlayer, built once per version of its source like `play` builds it, named `<Title> (<Story>)` in its `Info.plist` (`CFBundleName` and `CFBundleDisplayName`), with the bundle id `dev.videotape.<app>.<story>`, where each part keeps only letters, digits and `-`. It carries the tape in `Contents/Resources/tape/`: `tape.json` byte for byte, and every clip it names encoded as HEVC with the `hvc1` tag, and nothing else of the tape. Launched with no argument, the app plays that tape, and its app menu says `About`, `Hide` and `Quit` with its own name. Publish signs the app ad hoc and says so, since another Mac's Gatekeeper asks before it opens an app with no Developer ID. It records the tape's label, id and hashes in `videotape.lock` at the project's root, a TOML file the project commits, and publishing the same tape again leaves the lock as it is. It makes the app, the zip and the lock whole in `dist/<Title>-<story>.partial/` before it moves them into place, and a publish that fails or is stopped there puts back what dist/ and the lock held. It refuses with a code and ships nothing when the tape is out of date with its sources (`VT601`), has a failing check nobody accepted (`VT602`), has a label the lock holds with another id (`VT305`), when TapePlayer does not build (`VT603`), and when the last frame of an encoded clip, where TapePlayer rests, fails a check its key passed (`VT604`). Each error's first lines are the code's `videotape explain` example, up to the hashes, paths, numbers and story.

## Sub-features

- `publish-app` makes the starter's tape into `dist/Contrail-starter.app` and `dist/Contrail-starter.zip`, signed ad hoc, and adds its label to `videotape.lock`.
- `publish-inside` the app's `Info.plist` names it `Contrail (Starter)` with the id `dev.videotape.contrail.starter`, and it holds `tape.json` and three HEVC clips.
- `publish-again` publishing the same tape again builds the same app from the cached player and leaves `videotape.lock` unchanged.
- `publish-vt602` a tape whose kept takes fail checks nobody accepted is refused, with the commands for the first failure.
- `publish-vt601` a tape older than its sources is refused, naming what changed and the render command with the tape's model.
- `publish-vt305` a tape of changed data under a label the lock holds is refused, and the lock stays as it was.
- `publish-tests` the same journeys, the accept that lets a `VT602` tape through, a wan3.0 tape checked without `FAL_KEY`, `VT603` and `VT604`, proven by `uv run pytest tests/test_publish.py`.
- `publish-player` a copy of the published app outside the checkout, with what macOS keeps for its bundle id cleared, plays every journey of its tape, through the UI test.
- `publish-quickstart` `scripts/quickstart-test` publishes the starter after play; see [project.md](./project.md).

## How to get to it (user POV)

- In a project with a rendered tape, run `uv run videotape publish --story <story>`, or `uv run videotape publish --out <tape>`.
- Run `uv run videotape explain VT601`, and the same for `VT305`, `VT602`, `VT603` and `VT604`.
- Open `dist/<Title>-<story>.app` from Finder, or send `dist/<Title>-<story>.zip` to another Mac.
- Commit `videotape.lock`.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- A fresh project and caches: `D=$(mktemp -d)`, then `export UV_CACHE_DIR="$D/uv-cache" VIDEOTAPE_CACHE_DIR="$D/vt-cache"` and `unset FAL_KEY ANTHROPIC_API_KEY RUNPOD_API_KEY`, in the shell that runs every journey below.
- Xcode, as doctor's `info Xcode` line reports, since publish builds TapePlayer.

- **New and render.** Run `.claude/skills/verify/scripts/vt-verify exec "$RUN" publish-new -C "$D" -- uvx --from "$PWD" videotape new contrail`, then `.claude/skills/verify/scripts/vt-verify exec "$RUN" publish-render -C "$D/contrail" -- uv run videotape render --story starter --model stand-in`. Both `.exit` are `0`, and the render's last `.stdout` line is `3 shots, 4 takes filmed, $0.00, <s> s, tape 0.2 MB -> tapes/starter`.
- **Publish.** Run `.claude/skills/verify/scripts/vt-verify exec "$RUN" publish -C "$D/contrail" -- uv run videotape publish --story starter`. `.exit` is `0`, `.stderr` is empty, and `.stdout` is:

  ```
  building TapePlayer, once for this version of it
  built TapePlayer in 10.2 s
  encoded 3 clips as HEVC; on each one's last frame, where TapePlayer rests, every check its key passed still passes
  signed ad hoc, not with a Developer ID, so another Mac's Gatekeeper asks before it opens the app
  published dist/Contrail-starter.app, 1.1 MB, zipped to dist/Contrail-starter.zip, 0.4 MB
  label contrail 0.1.0 + starter 1.0.0
  id 14a9d5e9249c9e697920e722a58e0163bbd46013c080b93b0bb3d6d0098d6115
  videotape.lock holds the label now; commit it
  ```

  The build time is this machine's, and the id is `made.id` in `$D/contrail/tapes/starter/tape.json`, which changes with the checkout's code. `$D/contrail/videotape.lock` is two `#` lines, then a table `["contrail 0.1.0 + starter 1.0.0"]` with `id`, `screenplay = "contrail.screenplay:app"`, `code`, `data`, `story`, `model = "stand-in"`, `settings` and `engine`, each a quoted 64-character hash but `screenplay` and `model`.
- **The app.** Capture each of these with `vt-verify exec "$RUN" <name> -C "$D/contrail" -- <command>`:
  - `codesign --verify --deep --strict --verbose=2 dist/Contrail-starter.app` exits `0`, and its `.stderr` is `dist/Contrail-starter.app: valid on disk` and `dist/Contrail-starter.app: satisfies its Designated Requirement`.
  - `codesign -dv dist/Contrail-starter.app` prints, among its lines, `Identifier=dev.videotape.contrail.starter`, `Format=app bundle with Mach-O universal (x86_64 arm64)`, `Signature=adhoc` and `TeamIdentifier=not set`.
  - `plutil -p dist/Contrail-starter.app/Contents/Info.plist` has `"CFBundleDisplayName" => "Contrail (Starter)"`, `"CFBundleExecutable" => "TapePlayer"`, `"CFBundleIdentifier" => "dev.videotape.contrail.starter"` and `"CFBundleName" => "Contrail (Starter)"`.
  - `find dist/Contrail-starter.app -type f` lists eight files: `Contents/_CodeSignature/CodeResources`, `Contents/MacOS/TapePlayer`, `Contents/Info.plist`, `Contents/PkgInfo`, `Contents/Resources/tape/tape.json`, and `moves/opening.mp4`, `moves/home--see-the-steps.mp4` and `moves/todo--back.mp4` under `Contents/Resources/tape/`. No key image goes in, since the player reads none.
  - `sh -c 'for f in dist/Contrail-starter.app/Contents/Resources/tape/moves/*.mp4; do ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,codec_tag_string -of csv=p=0 "$f"; done'` prints `hevc,hvc1` three times.
  - `unzip -l dist/Contrail-starter.zip` lists every entry under `Contrail-starter.app/`, with a 163-byte `._` entry beside each file and folder inside the app, though not beside `Contrail-starter.app/` itself, for its `com.apple.provenance` attribute, which `ditto -x -k` restores.
- **Again.** Copy the lock aside, run the publish again as `publish-again`, and `cmp` the two. `.exit` is `0`, `.stdout` has no `building TapePlayer` line, starts with the `encoded 3 clips` line and ends with `videotape.lock held the label already`, and `cmp` exits `0`.
- **Failing checks.** Run `sed -i '' 's/under a warm lamp/under a green lamp/' "$D/contrail/stories/starter.toml"`, then `vt-verify exec "$RUN" publish-render-failing -C "$D/contrail" -- uv run videotape render --story starter --model stand-in --takes 1`, which exits `1` with two of the stand-in's flaws on `.stderr`, a misread line on the rehearsed `todo()` key and a cut on the move back, then the publish as `publish-vt602`. `.exit` is `1`, `.stdout` is empty, and `.stderr` is exactly:

  ```
  error VT602 tapes/starter: 2 checks fail that nobody accepted: key todo() rehearsed from home() VT502, todo() -> home() "Back" VT506
  fix: review them with videotape dailies --story starter, then retake the shot or accept the failing check with a reason; for the first:
  videotape retake "todo()" --story starter
  videotape accept "todo()" VT502 --story starter --reason "..."
  ```

- **Out of date.** Then run `printf '\n# a note for the next scene\n' >> "$D/contrail/contrail/screenplay.py"` and the publish as `publish-vt601`, without rendering. `.exit` is `1` and `.stderr` is exactly:

  ```
  error VT601 tapes/starter: the app's code changed since the tape was rendered
  fix: render the tape again with the model that made it, then publish it:
  videotape render --story starter --model stand-in
  ```

- **Label published already.** Put `stories/starter.toml` and `contrail/screenplay.py` back as `new` wrote them, run `sed -i '' 's/Add your data/Connect your data/' "$D/contrail/data/steps.json"`, render with the stand-in again as `publish-render-data`, which exits `0`, then publish as `publish-vt305`. `.exit` is `1`, `$D/contrail/videotape.lock` is unchanged, and `.stderr` is:

  ```
  error VT305 videotape.lock: contrail 0.1.0 + starter 1.0.0 was published with made id 14a9d5e9249c, and this tape under the same label has made id 2a692c068e7c: the data changed
  fix: give the tape a label of its own: bump version in pyproject.toml, or in stories/starter.toml for a change to the story, then render and publish again
  ```

  The two ids are the first 12 characters of the lock's `id` and of this tape's `made.id`.
- **Tests.** Run `.claude/skills/verify/scripts/vt-verify exec "$RUN" publish-tests -- uv run pytest tests/test_publish.py -v`. `.exit` is `0` with 27 tests passed: publish before any render, which prints `error VT405 tapes/starter: has no tape.json, which a render writes when it finishes` and the render that makes one; the starter's app, its plist, its tape, its codecs, its signature before and after a `ditto` round trip through the zip, its lock and a second publish; a republish stopped as by Ctrl-C at each step that writes (codesign, the zip, and each move of the app, the zip and the lock into place), and one whose zip fails with `VT606`, each leaving the old app, zip and lock whole; a republish whose zip fails and which is then stopped while it puts the old app back, which leaves the old app and zip in `dist/Contrail-starter.partial/aside` for the next publish to put back; one stopped while it puts the old lock back, after which the next publish keeps the old label beside its new one, and one after which a publish of another story keeps the old label beside its own; a tape whose made id predates the screenplay in it, which is `VT601`; `VT601` on a screenplay edit, on a switch of `[tool.videotape] screenplay` to another module of the same package, and on a version, code and data change; a wan3.0 tape with no `FAL_KEY`, checked fresh and then `VT601`; `VT602` until an accept; `VT305` until a version bump, after which the lock holds two labels; `VT603` from a build that fails; and `VT604` from an encoder that paints over todo()'s Back button, and from an eye that, after the encoding, misreads the copy of a line that todo() shows twice that the key passed, while the copy that failed was accepted, but not from Qwen's recorded read of flight(CT 104, 2026-12-13) with the period it added, which render forgave because Claude read the line exactly and which publish judges with Claude's reading from the record, while the same read changed to `1 stp.` is `VT604`, unless Qwen reads `1 stp.` on the clip's last frame before the encoding too, which is the reader's misread and not the encoding's; nor from a chart's value that the free reader misreads on the encoded frame, since the render left the chart's lines to the reader that reports charts and publish judges only the checks the record holds; `VT606` from a codesign that fails; `VT607` from a file left aside by a stopped publish whose place holds another, and from a lock another story's publish left aside while the project holds one, each keeping both; `VT605` from a `videotape.lock` that is not TOML; `VT407` from a key's picture of another size than its clips; doctor's `VT102`, in doctor's words, without ffmpeg on PATH; and `VT404` from a clip ffmpeg cannot encode, naming the command. Each refusal leaves no app and no lock.
- **The published app on screen.** Ask the user first: it takes over the mouse and screen. Run `.claude/skills/verify/scripts/vt-verify player-test "$RUN" --published "$D/contrail/dist/Contrail-starter.app" -only-testing:TapePlayerUITests/TapePlayerUITests/testWalksEveryJourneyOfAPublishedApp`. `test.sh` copies the app into a new temporary folder outside the checkout, removes `~/Library/Caches/<id>`, `~/Library/Saved Application State/<id>.savedState`, `~/Library/HTTPStorages/<id>`, `~/Library/WebKit/<id>` and `~/Library/Application Support/<id>` and runs `defaults delete <id>` for the copy's bundle id, and hands the copy to the test, which checks it is outside the checkout and that those paths are gone, launches the copy with no argument, and walks its tape as [player.md](./player.md)'s walk does, reading `tape.json` from inside the copy. On the starter that is 5 steps: Back at the entry, `See the steps`, `Back`, and Back from home() and then from todo(), since the starter has two states and no search bar. Then it asserts the app menu holds `About Contrail (Starter)`, `Hide Contrail (Starter)` and `Quit Contrail (Starter)`. `.exit` is `0` and `.stdout` has `Test Case '-[TapePlayerUITests.TapePlayerUITests testWalksEveryJourneyOfAPublishedApp]' passed`, `walked 5 steps in <s> s` and `** TEST SUCCEEDED **`. Without `--published` the test is skipped. Driven on 2026-11-15: `walked 5 steps in 12 s`, passed in 16 s. Driven on 2026-11-23 with the user's yes on `examples/contrail/dist/Contrail-terminal.app` and `Contrail-posters.app`, the gemini-omni-flash-1.2 tapes of 150 shots each: `walked 164 steps in 1139 s` and `walked 164 steps in 1145 s`, both passed.
- **Proof.** For each journey cite `.cmd`, `.exit` and the asserted lines, and for `publish` the lock's text and the `codesign` and `plutil` captures.

## Gotchas

- Never `open` a published app, or run the UI test, without the user's yes: both take over the screen.
- A publish stopped while it puts the earlier app, zip or lock back leaves them in `dist/<app>.partial/aside`. The next publish, of that story or any other, moves each one back to an empty place before it reads the lock, and refuses with `error VT607 dist/<app>.partial/aside: holds ...` when a place already holds another file, so no earlier file is deleted. Move back what to keep, delete the folder, and publish again.
- publish makes the made block again, and its engine hash covers videotape's own Python files. After any change to videotape, or an upgrade, every tape is `VT601`, and once rendered again a label already in the lock is `VT305`. Bump a version for a new label.
- The `VT601` fix names the tape's model. The starter's project model is wan3.0, which bills per call, so `videotape render --story starter` without `--model stand-in` would start a paid render behind a cap of $200.
- The `VT602` drive depends on the stand-in's flaws for the edited prompts, which are the same on every machine for the same edit. Another edit fails other shots.
- The id and the lock's hashes change with the checkout's code, so compare them with `tape.json`, never with the lines above.
- publish reads the story's name from `tape.json`, so `--out` works for a tape of any story, and the `VT601` fix keeps `--out`.
- On the stand-in's flat clips HEVC is a little larger than the H.264 a render writes, about 152 KB against 124 KB for the starter's three clips. On the surf shop's Wan clips it was about 27% smaller with Wan 2.2 and 77% smaller with Wan 3.0.
- Publish is a minute's work on a big tape: on a stand-in render of Contrail's terminal tape, 103 clips encoded and checked again with no `VT604`, and the publish took 51 s with a 10 s player build, into an app of 8.1 MB.
- `VT604` is not reachable with the stand-in on a live drive: its encoded last frames read the same as its keys. Only the test, whose encoder paints over a button, triggers it.
- Gatekeeper's question on another Mac has not been driven: it needs the zip downloaded on a second Mac.
- `dist/` is in the starter's `.gitignore` and the repo's; `videotape.lock` is not, so `git status` shows it after the first publish.
