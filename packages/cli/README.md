# @videotape/cli

`videotape check | graph | schema | dev | serve | render`. Loads `videotape.config.ts` (or
`tapes.ts`) from the app directory through tsx, so apps are plain TypeScript.

Renderer ids on the command line or in config (`flat`, `still-fal`) are resolved here, so the
engine never imports a vendor package. Backend credentials come from the environment only.

See [spec §11](../../docs/02-spec-v1.md).
