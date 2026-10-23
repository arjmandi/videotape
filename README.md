# videotape

**Interfaces, played.** Generative UI by video, not by code: an interface is declared as journeys,
played as a live generated picture of a world, and verified so that what you see is what you can
operate.

> Status: design v2, before any v2 code. The v1 spec was built and measured as `prototype-0` (a git
> tag); it showed that a server-driven UI with a generated backdrop works and is not new. The v2
> design in [docs/05-design-v2.md](docs/05-design-v2.md) redesigns the concept; experiments come
> before code.

## The idea

Generative-UI projects today write front-end code on the fly. Videotape writes no front-end code at
all. There is a declaration of what the interface must do, and there is a picture; between them is
an engine.

- **Developers declare intent:** tapes (journeys) of frames, with components, their roles and
  relations, data, and handlers. No layout, styling, screens, or routing.
- **Designers declare a world:** the place the interface lives in, its mood and materials. A tree
  trunk can be the button; a flag can be the field you write on.
- **Devices declare context:** canvas size, orientation, input methods. Nothing is detected; it is
  measured, continuously.
- **The engine composes** each frame for the canvas (breaking it into steps on a watch, merging it
  with its neighbours on a wall), **embodies** each component as an object of the world, **renders**
  the world as live video, and **grounds** every frame: every declared control is really there,
  where it should be, nothing else pretends to be one, and every fact is legible.
- **The player** shows the picture, maps touches to the objects under them, draws the facts from
  code onto the objects' surfaces, and keeps an accessibility tree that never depends on pixels.

A canvas is a camera on a set larger than any screen. Rotate a phone and the camera reframes at
once, the objects recompose a moment later, and the world re-renders shortly after.

## The rules that keep it honest

- **Facts come from code.** Every string, number, and value is exact, from the app, drawn onto the
  world, never invented by the generator.
- **Interactivity comes from the composition.** The picture must agree with it; a pixel can never
  create a control.
- **Everything works with the AI off.** A deterministic proxy of the world is always playable, and
  it is how the engine is tested.

## Documents

| Document | What it is |
|----------|------------|
| [docs/05-design-v2.md](docs/05-design-v2.md) | **The current design**: intent, world, and context as inputs; the composition engine with breakdown and merge; embodiment; the grounding harness; set and camera; live video as the main path; open questions. |
| [docs/03-landscape.md](docs/03-landscape.md) | Which models could sit behind each renderer, with sources, and the measured results of prototype-0's live runs. Goes stale; re-check before each experiment. |
| [docs/02-spec-v1.md](docs/02-spec-v1.md) | The v1 specification, built as `prototype-0`. Superseded as a concept by v2; kept for its contracts and history. |
| [docs/01-review-and-risks.md](docs/01-review-and-risks.md) | The first review of the idea and its risk register. Its risks still apply; its recommendation (a picture behind ordinary controls) is superseded by v2. |

## Plan

Experiments first, each answering whether one part of v2 can work: the composer (breakdown and
merge across canvases), embodiment in three worlds, stills with objects placed by inpainting, the
live tier on a real-time video model, and camera reframing between watch, phone, and desktop. The
build follows in order: composer, proxy tier, and player with the AI off; embodiment and stills with
grounding; the live tier; breakdown and merge hooks and the demo. See
[docs/05-design-v2.md](docs/05-design-v2.md) §17.

Packages will publish under the `@videotape/*` npm scope. The bare `videotape` name on npm belongs
to an unrelated package last touched in 2017; the CLI's command is still `videotape`.

## Licence

[Apache-2.0](LICENSE).
