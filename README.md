# videotape

**UI as a Game.** A UI engine that plays apps the way a game engine plays games: declared as
journeys, rendered live as generated worlds, streamed to native clients on every screen.

> Status: design v2, before any v2 code. The v1 spec was built and measured as `prototype-0` (a git
> tag); it showed that a server-driven UI with a generated backdrop works and is not new. The v2
> design is [docs/05-design-v2.md](docs/05-design-v2.md); experiments come before code.

## The idea

Generative-UI projects write front-end code on the fly. Videotape writes no front-end code at all.

- **Developers declare intent** in TypeScript or Python: tapes (journeys) of frames, components with
  their roles and relations, data, and handlers. No layout, styling, screens, or routing.
- **Designers declare a world:** flat, layered, or 3D; its mood, materials, and props. A console key
  can be the button; a tape reel can be a list item.
- **Clients report context:** screen size, orientation, input methods, preferences. Nothing is
  detected; it is measured, continuously.
- **The engine plays the app.** It composes every frame for the real screen, embodies each component
  as an object of the world, renders the scene live with in-world text drawn from code, hit-tests
  touches against real geometry, and streams the result cloud-gaming style.
- **One app, native everywhere.** `videotape export` produces clients for the web, iOS, Android, and
  desktop from day one. Each client is thin: it plays the stream, gives immediate feedback, and hosts
  the platform's own text editors and accessibility tree. That last part is what a game engine does
  not give you.

Generation owns the look in layers: worlds and props generated once and rendered live, a live neural
restyle on top, and, as real-time world models mature, rendering from the engine's state. The engine
stays the source of truth, and a harness checks that every control is real and every fact exact.

## The rules that keep it honest

- **Facts come from code.** Every string, number, and value is drawn by the engine, never by a model.
- **Interactivity comes from geometry.** Touches hit declared objects; pixels never create controls.
- **Everything works with generation off.** That is how the engine is tested.

## Documents

| Document | What it is |
|----------|------------|
| [docs/05-design-v2.md](docs/05-design-v2.md) | **The current design**: decisions, the engine and its loops, SDKs, worlds and generation layers, composition, embodiment, streaming and native clients, the harness, milestones, and open questions. |
| [docs/03-landscape.md](docs/03-landscape.md) | Providers for each generation layer and candidate engines, with sources, plus prototype-0's measured live runs. Goes stale; re-check before each experiment. |
| [docs/02-spec-v1.md](docs/02-spec-v1.md) | The v1 specification, built as `prototype-0`. Superseded as a concept; kept for its contracts and history. |
| [docs/01-review-and-risks.md](docs/01-review-and-risks.md) | The first review of the idea and its risk register. Its risks still apply; its recommendation (a picture behind ordinary controls) is superseded. |

## Plan

Experiments first: the engine bake-off on a server GPU, streaming latency and sessions per GPU,
native text editors over a stream, native accessibility from intent, the Python SDK, and an App
Review probe (Apple's rules read against streamed non-game apps). Then M1
delivers apps and user flows (engine, composer, streaming, exported clients, both SDKs) without OS
capabilities; M2 generated worlds; M3 breakdown, merge, and live looks; M4 native capabilities
through the exporter. See [docs/05-design-v2.md](docs/05-design-v2.md) §15.

Packages will publish under the `@videotape/*` npm scope. The bare `videotape` name on npm belongs
to an unrelated package last touched in 2017; the CLI's command is still `videotape`.

## Licence

[Apache-2.0](LICENSE).
