# Backend landscape — what could sit behind each renderer

**Checked:** 2026-10-22 · **Status:** notes, deliberately kept out of the spec because they go stale.
Re-check before M2 (`still` model ids), before M3 (`cut` model ids), and before any `live` work.

Everything below came from a quick web pass on the date above. Figures are the vendors' or papers'
own claims unless marked measured. Treat vendor comparison tables as marketing.

---

## 1. Real-time interactive video (candidates for the `live` renderer)

| System | Who | Claim | Access | Fit for Videotape |
|--------|-----|-------|--------|-------------------|
| MirageLSD | Decart | Transforms a live video stream in real time, under 40 ms per frame, 720p tier | Decart platform; hosted on Crusoe Cloud; JS/Python/Swift SDKs; WebRTC | **Best fit for `live`.** Video-to-video means the `flat` render can be the input stream, so layout conditioning comes for free frame by frame. |
| Lucy 2 / Lucy 2.1 (realtime) | Decart | Live 1080p at 30 fps, no buffering, no time limit; vendor-quoted sustained cost around three dollars an hour | Decart API platform; also on fal.ai | Same as above, newer. Model ids differ between Decart docs (`lucy-2.1`) and older third-party docs (`lucy_2_rt`); verify at implementation time. |
| Odyssey-2 | Odyssey | A new frame every 50 ms (20 fps); general-purpose world model | Unclear developer access | Watch. Not video-to-video as far as the sources say. |
| Genie 3 / Project Genie | Google DeepMind | 720p at 24 fps, interactive; generations limited to 60 s in the prototype | Research prototype for Google AI Ultra subscribers in the US since 2026-01-29; no developer API found | Not usable for v1. |
| Matrix-Game 2.0 | SkyworkAI | 25 fps streaming, minute-long videos; few-step autoregressive diffusion distilled from Self-Forcing; action-conditioned | Open weights and code: github.com/SkyworkAI/Matrix-Game, Hugging Face Skywork/Matrix-Game-2.0 | Open-weights path for `live` later. Trained on Unreal Engine and GTA5 data, so it knows game worlds, not interfaces. Hardware behind the 25 fps figure is not stated in the sources. |
| Matrix-Game 3.5 | SkyworkAI | Adds "patch memory" for long-horizon consistency | Paper found; check for weights | Same as above. |
| Self-Forcing | Huang et al., NeurIPS 2025 | About 17 fps on one GPU with sub-second latency; rolling KV cache | Paper and code | The base technique most open real-time models now distil from. |
| Krea Realtime 14B | Krea | 11 fps at 4 steps on one B200; distilled from Wan 2.1 14B with Self-Forcing | Model release; licence not confirmed in this pass | Candidate for a self-hosted `live` text-to-video path. |
| StreamDiffusionV2 | chenfengxu714 et al. | Causal DiT built on CausVid; single-GPU config for a 14B model at 480×832, 16 fps output | GitHub + Hugging Face checkpoints | Candidate for self-hosted `live`; fps for real-time not confirmed. |
| LongLive, BiWM, ABot-World-0, DreamForge-World 0.1, Causal Forcing++ | various, 2026 papers | Real-time or low-compute interactive generation; ABot-World-0 claims infinite rollout on a single desktop GPU | Papers; check for code | Track. None is UI-aware. |

**Takeaway.** Faster-than-playback generation is real and sold as a service today, at roughly one
GPU per stream. None of these models knows what a user interface is. The `live` renderer should
therefore be designed as **video-to-video restyling of the flat render**, with the content layer on
top, exactly as the spec describes. That is the only framing in which "real-time generated UI" is
honest with today's models.

## 2. Still generation with layout conditioning (candidates for the `still` renderer)

**Technique.** An image model with structural conditioning: a ControlNet-style control (canny,
depth, segmentation) driven by the wireframe raster, or image-to-image over the wireframe raster at
low denoise strength, plus the composed prompt and masks for `reserved` regions. The negative
prompt always includes text and letters.

**UI-specific research** (useful for prompts and evaluation, not as backends):

- UI-Diffuser (2023, "Boosting GUI Prototyping with Diffusion Models"): Stable Diffusion plus
  ControlNet, fine-tuned on Rico screenshot–wireframe pairs. The closest published shape of our
  `still` renderer.
- ControlGUI (arXiv 2502.03330, 2025): text, wireframe, and visual-flow inputs in any combination;
  joint control over layout and attention order.
- "Controllable GUI Exploration": a dataset of about 72,500 GUI screenshots with wireframes,
  descriptions, and scanpaths across mobile and web; reports better wireframe adherence than plain
  ControlNet.

Note the difference in goal: those works generate *GUI screenshots*. Videotape wants *scenes behind
a wireframe* with calm reserved regions, because the facts are drawn on top. The prompt style will
differ ("cinematic backdrop with a calm panel in the centre third" rather than "a login screen").

**Practical backends for v1.**

| Backend | Where | Notes |
|---------|-------|-------|
| fal.ai hosted image models with structural control | `renderer-still-fal` | **Chosen at M2 start (2026-10-22): `fal-ai/flux/dev/image-to-image`**, image-to-image over the wireframe raster. Inputs used: `image_url` (data URI), `prompt`, `strength` (default 0.82 here; fal's default 0.95), `seed`, `num_inference_steps` (28), `guidance_scale` (3.5), `output_format: png`, `sync_mode: true`. No negative prompt, so "no text, no letters" stays in the style suffix. The model id is configurable and part of the renderer version, so changing it invalidates cached scenes. First live run below (§2.1). Better-documented alternative if strength or seed misbehave: `fal-ai/flux-differential-diffusion`. Source: fal model page `fal.ai/models/fal-ai/flux/dev/image-to-image`. |
| ComfyUI, local | `renderer-still-comfy` | SDXL or FLUX with a ControlNet (union or canny/depth). Export the workflow JSON into the repo and call ComfyUI's HTTP API. Open-weights path. |

### 2.1 First live run (2026-10-22, measured)

`videotape render --renderers still-fal --frames landing,login,dashboard --viewports desktop,phone`:
8 scenes (dashboard in two moods), **20 fal calls**, about 10 s per call, 10–49 s per scene
including re-rolls. No fallbacks, no patches: every scene passed region validation within three
re-rolls. Every failure was on luma spread (bright consoles, lit screens, fake fields); contrast
never failed on this dark style.

| Scene | Tries | Failed regions before passing |
|-------|-------|-------------------------------|
| landing desktop | 2 | `sub` (σ 24.2) |
| landing phone | 1 | — |
| login desktop | 1 | — |
| login phone | 3 | `title`, `forgot`, then `title`, `username`, `error` (σ 25–44) |
| dashboard desktop, cool and warm | 4 each | stat cells `views`, `watch`, `subs`, and `hello` (σ 24–57) |
| dashboard phone, cool | 4 | stat cells, `hello` (σ 26–52) |
| dashboard phone, warm | 1 | — |

**Finding: the generator draws UI, with fake text, and validation does not catch it.** The
served phone login scene is a complete fake sign-in screen: an extra input, a "NORTE" button, and
gibberish lettering ("SUCCLATIONEL", "SIGN M UP."). It passed because lettering is thin, so luma
spread stays low, and button faces are `surface` regions that v1 does not check. Behind the real
controls this shows controls that are not controls (risk R8). Likely causes, in order: the
conditioning image is the full wireframe (text bars, field strips, button shapes), which reads as
a UI mock-up; the `dusk` prefix says "Cinematic UI backdrop"; FLUX [dev] has no negative prompt.
Landing and dashboard scenes, where the wireframe is mostly empty space, came out as intended.

## 3. Transitions (candidates for the `cut` renderer)

First-and-last-frame video generation is exactly the cut problem: two scene stills in, a short clip
between them out.

| Model | Who | Claim | Access | Notes |
|-------|-----|-------|--------|-------|
| LTX-2 | Lightricks | Full open-source release 2026-01; weights, training code, docs; Apache-2.0 per coverage | Hugging Face, fal.ai endpoints | Verify the licence on the model card. |
| LTX-2.3 | Lightricks | 2026-03; desktop editor for local use | Same | — |
| LTX-2.5 | Lightricks | 22B, 2026-08 per a third-party workflow page; video and audio in one pass; strong first-and-last-frame transitions | Verify against Lightricks' own release notes | Likely the first `cut` backend. |
| Wan 2.2 | Alibaba / Wan-AI | Open weights, MoE architecture | Hugging Face | First-and-last-frame support was not confirmed in this pass; check the model card. |

## 4. Cost snapshot (vendor claims, not measured)

| Item | Figure | Source type |
|------|--------|-------------|
| Lucy Realtime 2 on fal.ai | $0.02 per second of stream (list; $72 per hour) | Vendor page |
| MirageLSD on Decart platform | 2 credits per second, pro 720p tier; dollar value of a credit not stated | Vendor page |
| Decart sustained operating cost | about $3 per hour | Press coverage of vendor claim |
| Still image, hosted | typically cents per image | Not checked in this pass; measure in M2 |
| Short clip, hosted | typically tens of cents per clip | Not checked in this pass; measure in M3 |

For the cache-first design in the spec, the figures that matter are per-asset (still, clip), not
per-second of stream. Measure them in M2 and M3 and record them here.

## 5. Licences to record before adoption

| Weights | Licence | Checked |
|---------|---------|---------|
| Matrix-Game 2.0 | — | not yet |
| LTX-2.x | Apache-2.0 per coverage | verify on model card |
| Wan 2.2 | — | not yet |
| Krea Realtime 14B | — | not yet |
| StreamDiffusionV2 checkpoints | — | not yet |

## 6. Sources

Real-time and world models:
- https://www.crusoe.ai/resources/blog/miragelsd-decarts-real-time-ai-video-model-is-now-available-on-crusoe-cloud
- https://www.forbes.com/sites/charliefink/2026/01/27/decarts-new-lucy-2-generative-ai-video-model-pushes-generative-video-into-real-time/
- https://platform.decart.ai/models/mirage-lsd · https://decart.ai/api-platform · https://docs.platform.decart.ai/getting-started/overview.md · https://docs.platform.decart.ai/sdks/javascript-realtime.md
- https://fal.ai/lucy-2
- https://odyssey.systems/introducing-odyssey-2 · https://the-decoder.com/generative-ai-startup-odyssey-demos-interactive-ai-generated-video/
- https://en.wikipedia.org/wiki/Oasis_(Minecraft_clone)
- https://blog.google/innovation-and-ai/models-and-research/google-deepmind/project-genie/ · https://en.wikipedia.org/wiki/Genie_(world_model)
- https://arxiv.org/pdf/2508.13009 (Matrix-Game 2.0) · https://arxiv.org/pdf/2608.29910 (Matrix-Game 3.5) · https://www.globenewswire.com/news-release/2025/08/11/3131160/0/en/Matrix-Game-2-0-Released-The-First-Open-Source-Interactive-World-Model-for-Real-Time-Long-Sequence-Generation.html
- https://neurips.cc/virtual/2025/poster/116208 (Self-Forcing) · https://hyper.ai/ja/papers/2506.08009
- https://www.krea.ai/blog/krea-realtime-14b
- https://github.com/chenfengxu714/StreamDiffusionV2
- https://arxiv.org/pdf/2606.10135 (BiWM) · https://arxiv.org/pdf/2607.19191 (ABot-World-0) · https://arxiv.org/pdf/2606.30292 (DreamForge-World) · https://arxiv.org/pdf/2603.28489 (survey)

Layout-conditioned GUI generation:
- https://arxiv.org/pdf/2306.06233 (UI-Diffuser)
- https://arxiv.org/html/2502.03330v2 (ControlGUI)
- https://arxiv.org/pdf/2412.20071
- https://www.themoonlight.io/es/review/controllable-gui-exploration

Transitions:
- https://en.wikipedia.org/wiki/LTX-2 · https://www.mindstudio.ai/blog/what-is-ltx-2-19b-lightricks-video
- https://www.floyo.ai/workflows/ltx-2-5-first-and-last-frame-to-vide-6ver4ls63no1
- https://vast.ai/article/wan-2-2-vs-ltx-2-which-ai-video-model-should-you-use
