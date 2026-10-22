# @videotape/core

The tape model and everything that can be decided without I/O: the authoring API, Zod schemas for
the wire format and for VTP/1 (exported as JSON Schema), validation (`check`), the journey graph,
the layout engine, wireframe drawings, and the renderer plugin types.

**Contract.** Pure functions only: no network, no filesystem, no model calls. The player and the
engine both import these schemas, so they cannot drift. `layout(frame, viewportClass, style)` is
deterministic and snapshot-tested.

See [spec §5–§6, §9](../../docs/02-spec-v1.md).
