# Authoring a screenplay

A developer writes their own `screenplay.py` with `vt.Screenplay`, `scene(...)` and `vt.go(...)`, and the shot list reflects what they wrote. They can name an action's target with a plain string or with `vt.go(target, move=...)`, leave a scene without lines or buttons, and send an action back to a scene that already has its key.

## Sub-features

- `authoring-order` keys the scenes in walk order, then lists both actions of the first scene before any action of a later scene.
- `authoring-move` uses a `vt.go(..., move=...)` move in place of the default glide.
- `authoring-bare-scene` omits the text and button sentences from the key of a scene with no `shows` and no actions.
- `authoring-return` renders an action back to the first scene as a move between the two keys, like any other move.
- `authoring-buttons` writes `one big flat button sits` for one action and `two big flat buttons are stacked` for two.

## How to get to it (user POV)

- Write `<dir>/screenplay.py` and run `videotape shots <dir>`. The fixture `.claude/skills/verify/fixtures/cafe` is such a screenplay.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- `.claude/skills/verify/fixtures/cafe/screenplay.py` is unchanged from git.

- **List the cafe's shots.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" authoring-order -- shots .claude/skills/verify/fixtures/cafe`. `$RUN/authoring-order.exit` is `0`.
- **Order and return.** Run `grep -E '^[0-9]+\. ' "$RUN/authoring-order.stdout"`. The output is exactly:
  ```
  1. key menu  (text-to-video)
  2. key order  (text-to-video)
  3. key reviews  (text-to-video)
  4. menu -> order "Order coffee"  (first-and-last-frame)
  5. menu -> reviews "Read reviews"  (first-and-last-frame)
  6. order -> menu "Back to menu"  (first-and-last-frame)
  ```
- **Two buttons.** Run `sed -n 4p "$RUN/authoring-order.stdout"`. It contains `The text reads "Today's menu", "Coffee" and "Toast". Below it, two big flat buttons are stacked, with bold black letters reading "Order coffee" and "Read reviews".`
- **One button.** Run `sed -n 7p "$RUN/authoring-order.stdout"`. It contains `The text reads "Your order". Below it, one big flat button sits, with bold black letters reading "Back to menu".`
- **Bare scene.** Run `sed -n 10p "$RUN/authoring-order.stdout"`. It is, after three spaces of indent: `Static shot. A tiny seaside cafe at dawn, chalkboards and blue tiles. Handwritten notes pinned to a corkboard. Sharp, legible lettering.`
- **Custom move.** Run `sed -n 16p "$RUN/authoring-order.stdout"`. It is, after three spaces of indent: `The button labelled "Read reviews" is pressed. The camera pans left to a corkboard.`
- **Proof.** Cite `$RUN/authoring-order.screenplay.py`, `.cmd`, `.exit`, and the lines above.

## Gotchas

- Scenes may name targets defined later in the file. A forward reference is not an error.
- A new case in a scratch screenplay must live under `"${TMPDIR:-/tmp}"/videotape-verify-<name>` so cleanup removes it.
- The cafe's `reviews` scene has no `shows`, so its key prompt has no `The text reads` sentence at all. An empty `The text reads .` would be a bug.
- A move's prompt never names the scene it lands on. The words live on the two keys it is drawn between.
