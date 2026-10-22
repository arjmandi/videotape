# @videotape/player

The browser client: one page, one script, no framework (about 35 KB gzipped).

**Contract.** Shows the scene the engine names, lays real DOM controls over it at the regions the
render lists, and sends what the user does. It never hit-tests the picture and decides nothing
about the app. It keeps the safe area visible at any window size, holds input while a transition
is in flight, reconnects with its resume token, and runs under a CSP with no inline scripts.

`pnpm --filter @videotape/player build` writes `dist/`, which `videotape serve` serves.

See [spec §8](../../docs/02-spec-v1.md).
