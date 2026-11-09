# Authoring a screenplay

A developer writes their own `screenplay.py` with `vt.Screenplay`, `scene(...)` and `vt.go(...)`, and the shot list reflects what they wrote. They can name an action's target with a plain string or with `vt.go(target, move=...)`, leave a scene without lines or buttons, and send an action back to a scene that already has its key.

## Sub-features

- `authoring-order` lists both actions of the first scene before any action of a later scene.
- `authoring-move` uses a `vt.go(..., move=...)` move in place of the default glide.
- `authoring-bare-scene` omits the lettering and button sentences for a scene with no `shows` and no actions.
- `authoring-return` renders an action back to the first scene as `first-and-last-frame`.
- `authoring-buttons` writes `A button is labelled` for one action and `Buttons are labelled ... and ...` for several.

## How to get to it (user POV)

- Write `<dir>/screenplay.py` and run `videotape shots <dir>`. The fixture `.claude/skills/verify/fixtures/cafe` is such a screenplay.

## Driving it with vt-verify

Preconditions:

- Baseline preconditions from the README hold.
- `.claude/skills/verify/fixtures/cafe/screenplay.py` is unchanged from git.

- **List the cafe's shots.** Run `.claude/skills/verify/scripts/vt-verify run "$RUN" authoring-order -- shots .claude/skills/verify/fixtures/cafe`. `$RUN/authoring-order.exit` is `0`.
- **Order and return.** Run `grep -E '^[0-9]+\. ' "$RUN/authoring-order.stdout"`. The output is exactly:
  ```
  1. opening -> menu  (text-to-video)
  2. menu -> order  "Order coffee"  (image-to-video)
  3. menu -> reviews  "Read reviews"  (image-to-video)
  4. order -> menu  "Back to menu"  (first-and-last-frame)
  ```
- **Several buttons.** Run `sed -n 4p "$RUN/authoring-order.stdout"`. It contains `Buttons are labelled "Order coffee" and "Read reviews".`
- **One button.** Run `sed -n 7p "$RUN/authoring-order.stdout"`. It contains `The lettering reads "Your order". A button is labelled "Back to menu".`
- **Custom move, bare scene.** Run `sed -n 10p "$RUN/authoring-order.stdout"`. It is, after three spaces of indent: `A tiny seaside cafe at dawn, chalkboards and blue tiles. The button labelled "Read reviews" is pressed. The camera pans left to a corkboard. Handwritten notes pinned to a corkboard. The camera settles and holds still. Large, crisp, legible lettering.`
- **Proof.** Cite `$RUN/authoring-order.screenplay.py`, `.cmd`, `.exit`, and the lines above.

## Gotchas

- Scenes may name targets defined later in the file. A forward reference is not an error.
- A new case in a scratch screenplay must live under `"${TMPDIR:-/tmp}"/videotape-verify-<name>` so cleanup removes it.
- The cafe's `reviews` scene has no `shows`, so its prompt has no `The lettering reads` sentence at all. An empty `The lettering reads .` would be a bug.
