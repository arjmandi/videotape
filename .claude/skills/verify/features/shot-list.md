# Shot list

`videotape shots <dir>` prints the screenplay's title, then every shot a video model would render, numbered in the order they render. First comes a key for each scene, in the order the scenes are walked, each `text-to-video`. Then comes a move for each action, each `first-and-last-frame` between the two keys it joins, naming the scene it starts on, the scene it lands on and the button label pressed. Each shot's full prompt follows its header.

## Sub-features

- `shots-order` walks from the first scene, breadth first, in the order actions are written. Every scene is one key and every action is one move, and every key comes before any move.
- `shots-modes` labels every key `text-to-video` and every move `first-and-last-frame`.
- `shots-prompt` builds a key's prompt from `Static shot.`, the look, the scene's direction, its quoted lines, its buttons as big flat buttons with bold black letters, and `Sharp, legible lettering.` A move's prompt is the press and the move only.

## How to get to it (user POV)

- Run `videotape shots examples/surf_shop` from the repo root.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- `git diff --quiet -- examples/surf_shop` exits 0, unless the change under test edits the example.

- **List the shots.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" shots-order -- shots examples/surf_shop`. `$RUN/shots-order.exit` is `0` and `$RUN/shots-order.stderr` is empty.
- **Order and modes.** Run `grep -E '^[0-9]+\. ' "$RUN/shots-order.stdout"`. The output is exactly these ten lines:
  ```
  1. key welcome  (text-to-video)
  2. key entrance  (text-to-video)
  3. key login  (text-to-video)
  4. key signup  (text-to-video)
  5. key gallery  (text-to-video)
  6. welcome -> entrance "Enter shop"  (first-and-last-frame)
  7. entrance -> login "I have an account"  (first-and-last-frame)
  8. entrance -> signup "Create an account"  (first-and-last-frame)
  9. entrance -> gallery "Browse as guest"  (first-and-last-frame)
  10. signup -> login "Sign up"  (first-and-last-frame)
  ```
- **Title.** Run `head -1 "$RUN/shots-order.stdout"`. It prints `Brushstroke Surf Co.`.
- **Key with one button.** Run `sed -n 4p "$RUN/shots-order.stdout"`. It prints, after three spaces of indent: `Static shot. A small surf shop on the California coast in warm afternoon light: whitewashed wood, sea air, and surfboards hand-painted in bright patterns. The shop's front by the beach, its name painted over the open door. The text reads "Brushstroke Surf Co." and "Hand-painted surfboards from California". Below it, one big flat button sits, with bold black letters reading "Enter shop". Sharp, legible lettering.`
- **Key with three buttons.** Run `sed -n 7p "$RUN/shots-order.stdout"`. It prints, after three spaces of indent: `Static shot. A small surf shop on the California coast in warm afternoon light: whitewashed wood, sea air, and surfboards hand-painted in bright patterns. Just inside, by the counter. The text reads "How would you like to come in?". Below it, three big flat buttons are stacked, with bold black letters reading "I have an account", "Create an account" and "Browse as guest". Sharp, legible lettering.`
- **Key with no buttons.** Run `sed -n 10p "$RUN/shots-order.stdout"`. It ends `A card on the counter. The text reads "Log in", "Email" and "Password". Sharp, legible lettering.` and has no `button` in it.
- **Custom move.** Run `sed -n 19p "$RUN/shots-order.stdout"`. It is, after three spaces of indent: `The button labelled "Enter shop" is pressed. The camera walks through the open door.`
- **Default move.** Run `tail -1 "$RUN/shots-order.stdout"`. It is, after three spaces of indent: `The button labelled "Sign up" is pressed. The camera glides smoothly to the next view.` No move prompt quotes a line or a button of the scene it lands on.
- **Breadth first.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" shots-walk -- shots .claude/skills/verify/fixtures/walk`. `.exit` is `0`, and `grep -E '^[0-9]+\. ' "$RUN/shots-walk.stdout"` is exactly:
  ```
  1. key hall  (text-to-video)
  2. key left  (text-to-video)
  3. key right  (text-to-video)
  4. key desk  (text-to-video)
  5. key fridge  (text-to-video)
  6. hall -> left "Left door"  (first-and-last-frame)
  7. hall -> right "Right door"  (first-and-last-frame)
  8. left -> desk "Open desk"  (first-and-last-frame)
  9. right -> fridge "Open fridge"  (first-and-last-frame)
  ```
  A walk that takes the newest queued scene first swaps keys 4 and 5 and moves 8 and 9. `sed -n 4p "$RUN/shots-walk.stdout"` is, after the indent, `Static shot. A plain room. A long hall. Two big flat buttons are stacked, with bold black letters reading "Left door" and "Right door". Sharp, legible lettering.`, a scene with buttons and no lines. `sed -n 13p` is `Static shot. A plain room. An open drawer. Sharp, legible lettering.`, a scene with neither.
- **Proof.** Cite `$RUN/shots-order.cmd`, `.exit`, `.build`, doctor's `info build` line, and the grep output above. For `shots-walk` cite `.exit` and its grep.

## Gotchas

- The surf shop and the cafe in [authoring.md](./authoring.md) come out in the same order under a walk that takes the newest queued scene first. Only the `walk` fixture tells the two apart, so drive **Breadth first** after any change to the walk.
- The prompt for `entrance` ends its text with `"How would you like to come in?".` The period after the closing quote is current behavior, not a bug in the drive.
- Line numbers in the `sed` commands assume the title, then three lines per shot: a blank line, the header, the prompt. Shot N's header is line 3N and its prompt line 3N+1, and the last line is the last shot's prompt, with no blank line after it. If the output format changes, update this file.
- A key's button sentence counts in words, `one`, `two`, `three`, and says `sits` for one button and `are stacked` for more. A scene with buttons and no lines starts the sentence without `Below it,`.
