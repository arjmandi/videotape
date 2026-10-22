# @videotape/renderer-flat

The reference scene renderer: rasterises the frame's scene drawing (palette gradient, panels,
media frames) with resvg. Deterministic, so the same request gives byte-identical PNGs. Used in
CI and as every fallback. Bump `version` whenever its drawing changes, or caches serve old art.
