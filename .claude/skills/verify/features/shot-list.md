# Shot list

`videotape shots <dir>` prints the screenplay's title, then every shot a video model would render, numbered in walk order. Each shot names the scene it starts on (`opening` for the first), the scene it lands on, the button label pressed, its mode, and its full prompt.

## Sub-features

- `shots-order` walks from the first scene, breadth first, in the order actions are written. Every action is one shot.
- `shots-modes` labels the opening `text-to-video`, the first shot to land on a scene `image-to-video`, and any later shot to that scene `first-and-last-frame`.
- `shots-prompt` builds each prompt from the look, the press, the move, the landing scene's direction, its quoted lines and button labels, and the close.

## How to get to it (user POV)

- Run `videotape shots examples/surf_shop` from the repo root.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- `git diff --quiet -- examples/surf_shop` exits 0, unless the change under test edits the example.

- **List the shots.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" shots-order -- shots examples/surf_shop`. `$RUN/shots-order.exit` is `0` and `$RUN/shots-order.stderr` is empty.
- **Order and modes.** Run `grep -E '^[0-9]+\. ' "$RUN/shots-order.stdout"`. The output is exactly these six lines:
  ```
  1. opening -> welcome  (text-to-video)
  2. welcome -> entrance  "Enter shop"  (image-to-video)
  3. entrance -> login  "I have an account"  (image-to-video)
  4. entrance -> signup  "Create an account"  (image-to-video)
  5. entrance -> gallery  "Browse as guest"  (image-to-video)
  6. signup -> login  "Sign up"  (first-and-last-frame)
  ```
- **Title.** Run `head -1 "$RUN/shots-order.stdout"`. It prints `Brushstroke Surf Co.`.
- **Opening prompt.** Run `sed -n 4p "$RUN/shots-order.stdout"`. It prints, after three spaces of indent: `A small surf shop on the California coast in warm afternoon light: whitewashed wood, sea air, and surfboards hand-painted in bright patterns. The camera slowly pushes in. The shop's front by the beach, its name painted over the open door. The lettering reads "Brushstroke Surf Co." and "Hand-painted surfboards from California". A button is labelled "Enter shop". The camera settles and holds still. Large, crisp, legible lettering.`
- **Custom move.** Run `sed -n 7p "$RUN/shots-order.stdout"`. It contains `The button labelled "Enter shop" is pressed. The camera walks through the open door. Just inside, by the counter.` and `Buttons are labelled "I have an account", "Create an account" and "Browse as guest".`
- **Default move into a keyed scene.** Run `tail -1 "$RUN/shots-order.stdout"`. It contains `The button labelled "Sign up" is pressed. The camera glides smoothly to the next view. A card on the counter. The lettering reads "Log in", "Email" and "Password".` and ends with `The camera settles and holds still. Large, crisp, legible lettering.`
- **Breadth first.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" shots-walk -- shots .claude/skills/verify/fixtures/walk`. `.exit` is `0`, and `grep -E '^[0-9]+\. ' "$RUN/shots-walk.stdout"` is exactly:
  ```
  1. opening -> hall  (text-to-video)
  2. hall -> left  "Left door"  (image-to-video)
  3. hall -> right  "Right door"  (image-to-video)
  4. left -> desk  "Open desk"  (image-to-video)
  5. right -> fridge  "Open fridge"  (image-to-video)
  ```
  A walk that takes the newest queued scene first swaps lines 4 and 5.
- **Proof.** Cite `$RUN/shots-order.cmd`, `.exit`, `.build`, doctor's `info build` line, and the grep output above. For `shots-walk` cite `.exit` and its grep.

## Gotchas

- The surf shop and the cafe in [authoring.md](./authoring.md) come out in the same order under a walk that takes the newest queued scene first. Only the `walk` fixture tells the two apart, so drive **Breadth first** after any change to the walk.
- The prompt for `entrance` ends its lettering with `"How would you like to come in?".` The period after the closing quote is current behavior, not a bug in the drive.
- Line numbers in the `sed` commands assume the title, then three lines per shot: a blank line, the header, the prompt. Shot N's header is line 3N and its prompt line 3N+1, and the last line is the last shot's prompt, with no blank line after it. If the output format changes, update this file.
