# videotape

**UI as a Game.** A UI engine that plays apps the way a game engine plays games: declared as
journeys, rendered live as generated worlds, streamed to native clients on every screen.

> Status: design v2, before any v2 code. The v1 spec was built and measured as `prototype-0` (a git
> tag); it showed that a server-driven UI with a generated backdrop works and is not new. The v2
> design is [docs/05-design-v2.md](docs/05-design-v2.md); experiments come before code.

## The idea

Generative-UI projects write front-end code on the fly. Videotape writes no front-end code at all.

- **Developers declare intent** in TypeScript or Python, in three words: types (records the engine
  turns into inputs, lists, validation, and labels), places (frames: what is on stage and what can
  be done there), and decisions (handlers that say where the journey goes). No layout, styling,
  screens, or routing.
- **Designers direct a world** the app already implies: flat, layered, or 3D; its mood, materials,
  and props. A console key can be the button; a tape reel can be a list item. The journey's graph is
  laid out in it at release: frames become places, joined by camera paths.
- **Clients report context:** screen size, orientation, input methods, preferences. Nothing is
  detected; it is measured, continuously.
- **The engine plays the app.** It composes every frame for the real screen with a camera, embodies
  each component as an object of the world with in-world text drawn from code, keeps the app's
  state as typed documents, and sends the scene to the device, which renders it, hit-tests touches
  against real geometry, and answers at once. The world reacts to the journey. Where a session needs
  the server's render (the first seconds while a world downloads, or the live neural layers), the
  server streams it cloud-gaming style.
- **One app, native everywhere.** `videotape export` produces clients for the web, iOS, Android, and
  desktop from day one. Each client is small: it renders the scene, gives immediate feedback, and
  hosts the platform's own text editors and accessibility tree. That last part is what a game engine
  does not give you.

Generation owns the look in layers: worlds and props generated once and rendered live, a live neural
restyle whose look is baked into those assets at release, and, as real-time world models mature,
rendering from the engine's state. The engine stays the source of truth, and a harness checks that
every control is real and every fact exact.

## The rules that keep it honest

- **Facts come from code.** Every string, number, and value is drawn by the engine, never by a model.
- **Interactivity comes from geometry.** Touches hit declared objects; pixels never create controls.
- **Everything works with generation off.** That is how the engine is tested.

## Documents

| Document | What it is |
|----------|------------|
| [docs/05-design-v2.md](docs/05-design-v2.md) | **The current design**: decisions, the engine and its loops, SDKs, worlds and generation layers, composition, embodiment, streaming and native clients, the harness, milestones, and open questions. |
| [docs/06-getting-started.md](docs/06-getting-started.md) | **Getting started (draft)**: how a Python developer builds an app, thinks in journeys, and how a web app, a video platform, a photo-sharing app, a chat app, and a CRM take shape. Written before the code, to test the design. |
| [docs/07-review-from-apps.md](docs/07-review-from-apps.md) | **Review from apps**: the design gaps the getting-started guide exposed (F1–F27) and its questions (Q16–Q23), all decided and folded into the design on 2026-10-23. |
| [docs/08-leverage-review.md](docs/08-leverage-review.md) | **Leverage review**: eight proposals (P1–P8) that make authoring types, places, and decisions, and make the output a game (the graph as the level, a world that reacts, the look baked at release, scene state on every client). Q24–Q30 were decided and folded into the design on 2026-10-23. |
| [docs/03-landscape.md](docs/03-landscape.md) | Providers for each generation layer and candidate engines, with sources, plus prototype-0's measured live runs. Goes stale; re-check before each experiment. |
| [docs/02-spec-v1.md](docs/02-spec-v1.md) | The v1 specification, built as `prototype-0`. Superseded as a concept; kept for its contracts and history. |
| [docs/01-review-and-risks.md](docs/01-review-and-risks.md) | The first review of the idea and its risk register. Its risks still apply; its recommendation (a picture behind ordinary controls) is superseded. |

## Plan

Experiments first: the on-device renderer on every platform, native text editors and accessibility
from intent, the Python SDK and the document loop; then the server renderer and streaming for the
paths that need it, level layout in a generated world, and baking. M1 delivers apps and user flows
(engine, composer, exported clients that render on the device, both SDKs) without OS capabilities;
M2 generated worlds and world packs; M3 breakdown, merge, and live looks; M4 native capabilities
through the exporter. See [docs/05-design-v2.md](docs/05-design-v2.md) §15.

Packages will publish under the `@videotape/*` npm scope. The bare `videotape` name on npm belongs
to an unrelated package last touched in 2017; the CLI's command is still `videotape`.

## Licence

[Apache-2.0](LICENSE).
