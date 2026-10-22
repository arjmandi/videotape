# videotape

**Interfaces, played.** A framework where a user interface is written as a journey, rendered as
generated video, and shown by a player that knows which parts of the picture you can touch.

> Status: M0 and M1 are done: the loop runs end to end with the AI off, in a browser, at phone,
> tablet, and desktop sizes. M2 has started: region validation, re-roll, budgets, ahead-of-time
> rendering, and a fal.ai still renderer, tested against fakes and not yet run with a live key.

## Try it

Needs Node 20.18+ and pnpm 9.

```bash
pnpm install
pnpm dev                      # the demo at http://127.0.0.1:4173/?debug=1 (backtick toggles the HUD)
pnpm check                    # videotape check on the demo
pnpm test                     # unit, engine, and wire tests
pnpm test:e2e                 # Playwright walks every edge at three sizes
```

Sign in with `ada` / `lovelace`. To try generated scenes, set `FAL_KEY` and run
`node packages/cli/bin/videotape.mjs dev apps/site --renderers still-fal`.

## The idea

Today a UI is a pile of components and routes, and the user's journey through them is a side
document: a Figma flow, a user story, an end-to-end test. Videotape turns that around.

- You write **tapes**: ordered sequences of **frames**, one frame per still state of the app. A
  frame says what it is about, which components it shows, and where each interaction leads.
- An **engine** renders each frame as a picture and each transition as a short piece of video, using
  generative models conditioned on the frame's layout.
- A thin **player** fills the screen with that picture, lays real inputs and text on top of it, and
  sends your interactions back.

Because the journey is the program, every reachable state and edge is known statically. Validation,
testing, prefetching, and documentation all read from the same graph. Because presentation is
delegated, the same app plays on a phone, a tablet, a desktop, or whatever comes next, with no layout
code.

## The one rule that makes it honest

**Generation owns form. Code owns facts. Layout owns space.**

The model draws the look: backgrounds, chrome, mood, motion, transitions. The code draws every fact:
each string, number, image, and input, placed natively on top of the picture so it is always correct
and always operable. A layout engine decides every region before any pixel is generated, and the same
wireframe both conditions the model and positions the facts.

That split is why the whole thing also runs with the AI switched off, which is how it is tested, and
why the share of the screen that is generated can grow as models improve.

## Documents

| Document | What it is |
|----------|------------|
| [docs/01-review-and-risks.md](docs/01-review-and-risks.md) | An honest review of the idea: what is strong, where the pitch over-reaches, and a risk register with mitigations. |
| [docs/02-spec-v1.md](docs/02-spec-v1.md) | The v1 design specification: goals, vocabulary, architecture, the tape model and authoring API, layout, engine pipeline, renderer plugins, player, protocol, security, CLI, repo layout, milestones. |
| [docs/03-landscape.md](docs/03-landscape.md) | Which models and services could sit behind each renderer as of the check date, with sources. Kept separate because it goes stale. |
| [docs/04-test-plan.md](docs/04-test-plan.md) | How the contracts, the engine, the player, and the generative path are tested, layer by layer. |

## Roadmap (v1)

| Milestone | Delivers | Done when |
|-----------|----------|-----------|
| M0 Foundations | `@videotape/core`: tape model, schemas, validation, graph, layout engine; `videotape check` and `graph` | The demo's tapes validate; wireframe snapshots exist for every frame and viewport class |
| M1 The loop, AI off | engine, player, protocol, flat renderer, demo app | A tester signs in and reads a report at phone and desktop sizes, keyboard only, with a screen reader |
| M2 Generated stills | layout-conditioned scene generation, style packs, validation and re-roll, cache, ahead-of-time render | Scenes are generated, text is crisp, fields stay put across reloads, cache hit rate is high |
| M3 Motion | generated cuts along edges, prefetch, budgets, crossfade fallback | A click plays a generated transition within the budget when prefetched; fallback rate is visible |
| M4 Ship | public demo, docs as a tape, sample app, licence and contribution guide | A stranger defines a tape from this README and sees it |

Real-time whole-screen video (`live` renderer over WebRTC) is defined as an interface in v1 and
implemented after it.

## Layout

```
packages/core        the model, schemas, validation, graph, layout engine (pure)
packages/engine      sessions, pipeline, cache, protocol server, renderer host
packages/player      the browser client
packages/cli         videotape dev | check | graph | render | serve
packages/renderers   flat (reference) · still-fal · still-comfy, cut-*, live-* (later)
apps/site            the demo and public site
e2e                  Playwright suites against the demo
examples/hello-tape  the smallest possible app (later)
```

Packages publish under the `@videotape/*` npm scope. The bare `videotape` name on npm belongs to an
unrelated package last touched in 2017; the CLI's command is still `videotape`.

## Licence

[Apache-2.0](LICENSE).
