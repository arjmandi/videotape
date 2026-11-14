# Player

TapePlayer is the macOS app a person uses to click through a rendered tape as if it were the app. From the repo root, `open clients/macos/build/TapePlayer.app --args examples/contrail/tape` opens one window titled `contrail` in the tape's shape. It plays the opening and rests on the home key. While a state rests, each hotspot is an invisible area that shows a pointing hand and that accessibility sees as a button named by its label, which is what a screen reader speaks. Clicking one plays its move into the next state. Start Over (⌘R) plays from the beginning, and File > Open picks another tape. The app draws nothing of its own over the tape. TapePlayer reads the tape as it always has: `tape.json` names one scene per state.

The UI tests, `player-cuts` and the journeys a person drives have not been driven on the Contrail tape yet, because each takes over the screen and needs the user's yes. `player-build` and `player-press` have. Correct any expected line below that the first drive proves wrong.

## Sub-features

- `player-build` builds `clients/macos/build/TapePlayer.app`.
- `player-press` books the flight through TapeKit's loader and player without a window, and names a label the resting state does not offer.
- `player-booking` goes home, `Where to?`, search, `Seattle (SEA)`, the dates, `Saturday, December 12, $89`, that day's flights, the 8:15 AM flight, `Book for $89`, the booking, `Done`, and home again, and the window then shows the home key.
- `player-hotspots` shows a pointing hand and accessibility buttons over hotspots only while a state rests, and ignores clicks while a clip plays.
- `player-start-over` plays the opening again on ⌘R, mid-clip or at rest.
- `player-open` shows the Open panel when launched without a tape, and File > Open (⌘O) switches to a tape folder or its `tape.json`.
- `player-bad-tape` shows an alert headed `This tape cannot play.` with the reason, and File > Open still works after it.
- `player-window` keeps the tape's shape through resizing and zoom with the video reaching every edge.
- `player-cuts` cuts from clip to clip with no blank, black or half-faded frame between them.

## How to get to it (user POV)

- Render the tape with `uv run videotape render` in `examples/contrail`, build with `clients/macos/build.sh`, then run `open clients/macos/build/TapePlayer.app --args examples/contrail/tape` from the repo root.
- Open `clients/macos/build/TapePlayer.app` with no arguments and pick a tape in the Open panel.
- In a running TapePlayer, choose File > Open… (⌘O) or Playback > Start Over (⌘R).

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold, and doctor prints an `info Xcode` line with a version.
- `examples/contrail/tape/tape.json` exists. If not, drive `render-first` from [render.md](./render.md).
- `player-test` and every journey a person drives take over the mouse and screen. `player-cuts` plays a window on screen without touching the mouse, for about a minute on a stand-in tape and proportionally longer for longer clips, such as Wan's 81-frame clips. Ask the user before each one, and wait for a yes.
- For the journeys a person drives, TapePlayer is not running, and `$RUN/player-build.exit` is `0`.

- **Build.** Run `.claude/skills/verify/scripts/vt-verify player-build "$RUN"`. `$RUN/player-build.exit` is `0`, `.stderr` is empty, and `.stdout` is `built <repo>/clients/macos/build/TapePlayer.app`.
- **Booking without a window.** Run `.claude/skills/verify/scripts/vt-verify player-press "$RUN" examples/contrail/tape "Where to?" "Seattle (SEA)" 'Saturday, December 12, $89' "8:15 AM*" 'Book for $89' "Done"`. `$RUN/player-press.exit` is `0`, `.stderr` is empty, and `.stdout` is exactly:
  ```
  58 scenes at 1280x704, and the opening rests on home()
  press "Where to?" -> search()
  press "Seattle (SEA)" -> dates(SEA)
  press "Saturday, December 12, $89" -> results(SEA, 2026-12-12)
  press "8:15 AM to 10:25 AM, 2h 10m, Nonstop, $89" -> flight(CT 300, 2026-12-12)
  press "Book for $89" -> booked(CT 300, 2026-12-12)
  press "Done" -> home()
  rests on home(), which offers ["Where to?", "San Francisco to New York, Friday, December 18", "Trips", "Profile"]
  ```
  With the labels `"Trips" "Seattle (SEA)"` instead, `.exit` is `1` and the last line is `FAIL my_trips() offers no "Seattle (SEA)"; it offers ["San Francisco to New York, Friday, December 18", "San Francisco to Honolulu, Friday, January 8", "Home", "Profile"]`. With `examples/contrail` as the tape, `.exit` is `2` and `.stdout` starts `error: No tape.json at `. `swift test --package-path clients/macos/TapeKit` passes 23 tests against TapeKit's own fixture tape.
- **Booking.** Run `.claude/skills/verify/scripts/vt-verify player-test "$RUN"`. It runs TapeKit's unit tests, then `testBookingTheMorningFlightToSeattleLandsBackOnHome`, a UI test that launches TapePlayer on `examples/contrail/tape` and clicks `Where to?`, `Seattle (SEA)`, `Saturday, December 12, $89`, the button whose label begins `8:15 AM`, `Book for $89` and `Done`. On the way it waits for the tape to rest on `results(SEA, 2026-12-12)` and on `booked(CT 300, 2026-12-12)`. The test passes only when the tape rests on `home()` again and its screenshot, with each image's mean colour removed, is within 3 of `keys/home.png` and more than 5 farther from `keys/booked-ct-300-2026-12-12.png`, on a 0 to 255 scale. The two key images themselves are 10.45 apart on that scale. `$RUN/player-test.exit` is `0` and `.stdout` contains `** TEST SUCCEEDED **`. `.stdout` has a line `tape vs keys/home.png H, vs keys/booked-ct-300-2026-12-12.png B` with both distances. `$RUN/player-test.attachments/manifest.json` names the screenshot's PNG as `exportedFileName`; its `suggestedHumanReadableName` mangles the distances, so read them from `.stdout`. The PNG shows the home key edge to edge.
- **Staying open.** The same `player-test` run also runs `testABadTapeLeavesOpenAvailable` and `testCancellingTheOpenPanelKeepsTheApp`. They dismiss the bad-tape alert and cancel the launch Open panel, then assert TapePlayer is still running with File > Open… enabled. `$RUN/player-test.stdout` has a `passed` line for each.
- **By hand.** To watch the booking, run `open clients/macos/build/TapePlayer.app --args examples/contrail/tape` and ask the user to click the same six things. The window rests on the home key at the end.
- **Hotspots.** Ask the user to hover `Where to?` on the home key. The pointer is a pointing hand over the box and an arrow elsewhere. While a clip plays, the hand never shows and a click on a box does nothing. Ask the user to press ⌘R and hold the pointer still where `Where to?` will be while the opening plays. With no movement, the pointer turns into a hand the moment the home key comes to rest. Ask them to click `Where to?` and keep the pointer still. It turns back into an arrow as the move starts. Accessibility Inspector (Xcode > Open Developer Tool) shows an image with identifier `tape` labelled with the resting state's name, and one button per hotspot with its exact label, such as `San Francisco to New York, Friday, December 18` for home's next trip. While a clip plays, the label is empty and there are no buttons.
- **Start Over.** Ask the user to press ⌘R once mid-clip and once at rest. Each time the opening plays and the window rests on the home key.
- **Open.** Quit TapePlayer, then run `open clients/macos/build/TapePlayer.app`. An Open panel asks `Choose a tape folder or its tape.json.` Choose `examples/contrail/tape`. The `contrail` window plays the opening. File > Open… (⌘O) with `examples/contrail/tape/tape.json` replaces the window with a new one that plays the opening.
- **Bad tape.** Quit TapePlayer, then run `open clients/macos/build/TapePlayer.app --args examples/contrail`. An alert headed `This tape cannot play.` reads `No tape.json at examples/contrail in / or in any folder above <repo>/clients/macos/build/TapePlayer.app.` After OK, File > Open… still opens the Open panel.
- **Window.** Ask the user to drag a window corner, then click the green zoom button. The window keeps the tape's shape, the video reaches all four edges with no grey band, and zoom grows the window as far as the screen allows in that shape.
- **Cuts.** Run `.claude/skills/verify/scripts/vt-verify player-cuts "$RUN"`. It plays `examples/contrail/tape` in a borderless window through TapePlayer's own playback code, presses the next hotspot the moment each state rests, starts over at a state with none, and captures the window about every 8 ms. Then it does the same with a control projector that swaps clips the naive way. `$RUN/player-cuts.exit` is `0` and `.stdout` ends with `ok: no flash in 30 cuts, and the control flashed`. Under `== TapePlayer's projector`, `largest edge change from the first frame` is a few units of 255 with `captures over 40: 0`, and `fewest captures in the 200 ms after a cut` is at least 5. Under `== control`, `captures over 40` is above 0 with `flash at` lines a few ms after a cut. A second argument sets the number of cuts.
- **Proof.** For `player-build` and `player-press` cite `.cmd`, `.exit` and `.stdout`. For `player-test` cite `.exit`, the three `Test Case ... passed` lines for `testBookingTheMorningFlightToSeattleLandsBackOnHome`, `testABadTapeLeavesOpenAvailable` and `testCancellingTheOpenPanelKeepsTheApp`, the distances line, the `** TEST SUCCEEDED **` line and the screenshot from `player-test.attachments`. For `player-cuts` cite `.exit` and both summaries from `.stdout`. For the journeys a person drives, quote what the user reported and the command you ran. Report any you could not run as skipped, with the reason.

## Gotchas

- The UI test and every journey a person drives take over the real mouse and screen. Ask the user before running them. Nobody should touch the mouse while `player-test` runs.
- `player-press` proves what the tape offers and where each press lands, through the code TapePlayer loads and plays with. It does not prove the window, the clips on screen, the pointer or accessibility. Those need `player-test` and a person.
- `player-press` builds a small Swift package in `.claude/skills/verify/scripts/player-press/` against `clients/macos/TapeKit`, into `clients/macos/build/player-press`. A change to TapeKit's `Tape` or `Player` can break that build. Then its exit is `2`.
- To compile the UI tests without running them, run `xcodebuild build-for-testing -quiet -project TapePlayer.xcodeproj -scheme TapePlayer -destination "platform=macOS,arch=$(uname -m)" -derivedDataPath build/DerivedData` in `clients/macos`. It exits 0 and opens nothing.
- `open` launches TapePlayer with `/` as its working directory. TapePlayer resolves a relative tape path against `/` first, then against each folder above the app bundle. So `examples/contrail/tape` works only for a copy of the app inside this checkout. Pass an absolute path to any other copy.
- The Open panel hides folders whose names start with a dot, so a checkout under one, such as `~/.t3/projects/`, cannot be browsed to. Press ⌘⇧G in the panel and paste the absolute path of the tape folder or its `tape.json`.
- `open ... --args` is ignored when TapePlayer is already running. `open` only brings the running window forward. Quit TapePlayer (⌘Q) first.
- The UI test plays `examples/contrail/tape` as it is on disk. If it is missing, the test fails and names the render command. After a screenplay or data edit, render again before testing.
- A UI test run needs macOS Automation Mode. On a Mac where `automationmodetool` prints `This device requires user authentication to enable Automation Mode.`, each run asks the user for their password. Unanswered, it fails after a minute with `Timed out while enabling automation mode.` and `Executed 0 tests`. The user can answer the prompt, or once run `automationmodetool enable-automationmode-without-authentication` with an admin password. Never run it yourself.
- On the prototype 1 tape, the screenshot's colours sat off the keys by 7.78 on that scale on the Dell P3223QE where it was measured. macOS decodes the untagged clips with the BT.709 matrix they were not encoded with, and the display's profile shifts them again. The UI test removes each image's mean colour, so it compares which key shows, not its exact colours.
- Window tiling (dragging to a screen edge, or Window > Move & Resize) ignores the tape's shape. The video then crops at two edges. That is expected and is not a `player-window` failure.
- The pointer turns into a hand as soon as a state comes to rest under it, and back into an arrow when a move starts, without the pointer moving. The UI tests can't read the cursor, so a person checks both cases by hand in the Hotspots journey.
- `player-cuts` builds its harness from TapePlayer's and TapeKit's Swift sources with `swiftc`, outside Xcode. A change to the player's view or playback code can break that build even when `player-build` passes. Then `player-cuts.exit` is `2`, and the harness in `.claude/skills/verify/scripts/player-cuts/` needs the same change.
- `player-cuts` needs no Screen Recording permission, because a process may capture its own windows. It does not move the mouse, but its window plays on screen for about a minute on a stand-in tape, and proportionally longer for longer clips.
- The control projector proves the captures can see a flash. A flash is judged before capture coverage, so a capture stall during the control run no longer fails the pass. Only TapePlayer's clean verdict needs every cut densely sampled.
- An action the checks did not find on its key has no hotspot in `tape.json`, so TapePlayer shows no hand and no accessibility button for it, and the journey through it cannot be clicked. The render prints a `fail:` line for it and the Keys section of `dailies.html` lists it as `not found`. On a stand-in tape every action is found. On a Wan tape, read the `fail:` lines first and report such a journey as blocked by the model.
