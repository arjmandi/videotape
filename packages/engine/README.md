# @videotape/engine

Sessions (reels), the render pipeline, the content-addressed cache, the VTP server, and the
renderer host.

**Contract.**
- `new Engine(config, opts).connect(send)` returns a connection that takes raw VTP text and calls
  `send` with validated server messages. `startServer` wraps it in HTTP + WebSocket (Hono).
- Every incoming event is checked against the current frame and the latest render; anything else
  is dropped and logged by id, never by value. Secrets reach the handler once and nowhere else.
- Scenes come from the first available renderer, inside a budget; the flat renderer is the floor.
  Generated scenes are normalised, region-validated, re-rolled up to three times, and patched.
- Reel data never enters a cache key or a prompt; only declared flavour does.

See [spec §4, §7, §9–§10](../../docs/02-spec-v1.md).
