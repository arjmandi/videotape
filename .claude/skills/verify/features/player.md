# Player

TapePlayer is the macOS app a person uses to click through a rendered tape as if it were the app. From the repo root, `open clients/macos/build/TapePlayer.app --args examples/surf_shop/tape` opens one window titled `surf_shop` in the tape's shape. It plays the opening and rests on the welcome key. While a scene rests, each hotspot is an invisible region that shows a pointing hand and that accessibility sees as a button named by its label. Clicking one plays its move into the next scene. Start Over (⌘R) plays from the beginning, and File > Open picks another tape. The app draws nothing of its own over the tape.

## Sub-features

- `player-build` builds `clients/macos/build/TapePlayer.app`.
- `player-gallery` goes welcome, Enter shop, entrance, Browse as guest, gallery, and the window then shows the gallery key.
- `player-login` goes welcome, Enter shop, entrance, I have an account, login.
- `player-signup` goes entrance, Create an account, signup, Sign up, login.
- `player-hotspots` shows a pointing hand and accessibility buttons over hotspots only while a scene rests, and ignores clicks while a clip plays.
- `player-start-over` plays the opening again on ⌘R, mid-clip or at rest.
- `player-open` shows the Open panel when launched without a tape, and File > Open (⌘O) switches to a tape folder or its `tape.json`.
- `player-bad-tape` shows an alert headed `This tape cannot play.` with the reason, and File > Open still works after it.
- `player-window` keeps the tape's shape through resizing and zoom with the video reaching every edge.

## How to get to it (user POV)

- Render the tape with `videotape render examples/surf_shop --model stand-in`, build with `clients/macos/build.sh`, then run `open clients/macos/build/TapePlayer.app --args examples/surf_shop/tape` from the repo root.
- Open `clients/macos/build/TapePlayer.app` with no arguments and pick a tape in the Open panel.
- In a running TapePlayer, choose File > Open… (⌘O) or Playback > Start Over (⌘R).

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold, and doctor prints an `info Xcode` line with a version.
- `examples/surf_shop/tape/tape.json` exists. If not, drive `render-first` from [render.md](./render.md).
- Every journey except `player-build` takes over the mouse and screen. Ask the user before each one, and wait for a yes.
- For the journeys a person drives, TapePlayer is not running, and `$RUN/player-build.exit` is `0`.

- **Build.** Run `.claude/skills/verify/scripts/vt-verify player-build "$RUN"`. `$RUN/player-build.exit` is `0`, `.stderr` is empty, and `.stdout` is `built <repo>/clients/macos/build/TapePlayer.app`.
- **Gallery.** Run `.claude/skills/verify/scripts/vt-verify player-test "$RUN"`. It runs TapeKit's unit tests, then `testBrowsingAsGuestRestsOnTheGallery`, a UI test that launches TapePlayer on `examples/surf_shop/tape` and clicks `Enter shop` and `Browse as guest`. The test passes only when the tape rests on `gallery` with no buttons left and its screenshot, with each image's mean colour removed, is within 2 of `keys/gallery.png` and more than 8 farther from `keys/entrance.png`, on a 0 to 255 scale. `$RUN/player-test.exit` is `0` and `.stdout` contains `** TEST SUCCEEDED **`. `$RUN/player-test.attachments/manifest.json` lists the screenshot under a name that gives both distances. Read the PNG beside it. It shows the gallery key edge to edge.
- **Login and signup.** The same `player-test` run also runs `testLoginAndSignupBothRestOnLogin`. It clicks `Enter shop` and `I have an account` and waits for the tape to rest on `login` with no buttons. It presses ⌘R, then clicks `Enter shop`, `Create an account` and `Sign up`, and waits for `signup` and then `login`. `$RUN/player-test.stdout` has `Test Case '-[TapePlayerUITests.TapePlayerUITests testLoginAndSignupBothRestOnLogin]' passed`. To watch it by hand, run `open clients/macos/build/TapePlayer.app --args examples/surf_shop/tape` and ask the user to click the same buttons. The window rests on the login key each time.
- **Hotspots.** Ask the user to hover `Enter shop` on the welcome key. The pointer is a pointing hand over the button and an arrow elsewhere. While a clip plays, the hand never shows and a click on a button does nothing. Accessibility Inspector (Xcode > Open Developer Tool) shows an image with identifier `tape` labelled with the resting scene's name, and one button per hotspot with its exact label. While a clip plays, the label is empty and there are no buttons.
- **Start Over.** Ask the user to press ⌘R once mid-clip and once at rest. Each time the opening plays and the window rests on the welcome key.
- **Open.** Quit TapePlayer, then run `open clients/macos/build/TapePlayer.app`. An Open panel asks `Choose a tape folder or its tape.json.` Choose `examples/surf_shop/tape`. The `surf_shop` window plays the opening. File > Open… (⌘O) with `examples/surf_shop/tape/tape.json` replaces the window with a new one that plays the opening.
- **Bad tape.** Quit TapePlayer, then run `open clients/macos/build/TapePlayer.app --args examples/surf_shop`. An alert headed `This tape cannot play.` reads `No tape.json at examples/surf_shop in / or in any folder above <repo>/clients/macos/build/TapePlayer.app.` After OK, File > Open… still opens the Open panel.
- **Window.** Ask the user to drag a window corner, then click the green zoom button. The window keeps the tape's shape, the video reaches all four edges with no grey band, and zoom grows the window as far as the screen allows in that shape.
- **Proof.** For `player-build` cite `.cmd`, `.exit` and `.stdout`. For `player-test` cite `.exit`, the `** TEST SUCCEEDED **` line and the screenshot from `player-test.attachments`. For the journeys a person drives, quote what the user reported and the command you ran. Report any you could not run as skipped, with the reason.

## Gotchas

- The UI test and every journey a person drives take over the real mouse and screen. Ask the user before running them. Nobody should touch the mouse while `player-test` runs.
- `open` launches TapePlayer with `/` as its working directory. TapePlayer resolves a relative tape path against `/` first, then against each folder above the app bundle. So `examples/surf_shop/tape` works only for the app in this checkout's `clients/macos/build/`. Pass an absolute path to any other copy.
- `open ... --args` is ignored when TapePlayer is already running. `open` only brings the running window forward. Quit TapePlayer (⌘Q) first.
- The UI test plays `examples/surf_shop/tape` as it is on disk. If it is missing, the test fails and names the render command. After a screenplay edit, render again before testing.
- A UI test run needs macOS Automation Mode. On a Mac where `automationmodetool` prints `This device requires user authentication to enable Automation Mode.`, each run asks the user for their password. Unanswered, it fails after a minute with `Timed out while enabling automation mode.` and `Executed 0 tests`. The user can answer the prompt, or once run `automationmodetool enable-automationmode-without-authentication` with an admin password. Never run it yourself.
- The screenshot's colours sit off the keys by 7.78 on that scale on the Dell P3223QE where it was measured. macOS decodes the untagged clips with the BT.709 matrix they were not encoded with, and the display's profile shifts them again. The UI test removes each image's mean colour, so it compares which screen shows, not its exact colours.
- Window tiling (dragging to a screen edge, or Window > Move & Resize) ignores the tape's shape. The video then crops at two edges. That is expected and is not a `player-window` failure.
- A pointer already over a hotspot when its scene comes to rest stays an arrow until it moves.
