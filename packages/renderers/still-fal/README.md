# @videotape/renderer-still-fal

Layout-conditioned scene generation on fal.ai: image-to-image over the wireframe raster.

```ts
falStill({ model: "fal-ai/flux/dev/image-to-image", strength: 0.82 })
```

Needs `FAL_KEY` in the environment; without it the renderer reports itself unavailable and the
engine uses `flat`. Model, strength, steps, and guidance are part of the renderer version, so any
change starts a fresh cache. The request carries only the prompt, the wireframe, and generation
settings: never reel data. The model choice and its parameters are recorded in
[docs/03-landscape.md](../../../docs/03-landscape.md).
