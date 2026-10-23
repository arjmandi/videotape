# Backend landscape — what could sit behind each renderer

**Checked:** 2026-10-22 · **Status:** notes, deliberately kept out of the spec because they go stale.
Re-check before each v2 experiment ([05-design-v2.md](05-design-v2.md) §17), and before any `live` work.
The measured results in §2.1–2.7 were produced by `prototype-0` (git tag), which holds the code
and commands they refer to.

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

### 2.2 Fixes, and the login re-render (same day, measured)

Three changes, then `--frames login --viewports desktop,phone` again:

1. **Conditioning on the scene drawing** (panels and media frames on the palette gradient) instead
   of the full wireframe.
2. **"UI" dropped from the `dusk` prefix** ("Cinematic backdrop, …").
3. **A lettering check** in region validation, covering reserved regions, button faces, and panels.
   Edge density was tried first and rejected on this data: at its best setting it scored the fake
   phone-login text at 0.019–0.054 and the good dashboard regions over city lights at 0.063–0.083,
   so no threshold separated them. OCR (tesseract, local English model, words of three or more
   letters at confidence ≥ 80) did: it read 7, 9, and 10 words in the three bad phone-login tries
   and none in any scene judged good, at 50–400 ms per scene.

Result: **2 fal calls, both scenes passed first time.** Desktop: a silhouetted figure beside a
cassette in a teal glow, with no interface or lettering. Phone: a calm dark panel where the form
goes; no fake fields, buttons, or text. Contrast-stretching the phone scene still shows ghost
marks shaped like lettering inside the panel, within about 2 luma levels (the whole image spans
32–53), far below anything readable, so OCR does not register it. The phone scene is now safe but
close to the flat render; giving it more form without inviting a mock-up is the next prompt
question.

The cache key now also covers the style pack, the conditioning drawing, and the prompt, so these
changes invalidated the old scenes instead of serving them.

### 2.3 Landing and dashboard under the fixed pipeline (same day, measured)

`--frames landing,dashboard --viewports desktop,phone`: 6 scenes, **6 fal calls, every scene
passed first time** (the same scenes took 16 calls before the fixes). No lettering anywhere.

- **Dashboard improved.** The grid's cell panels are now the main structure in the conditioning
  image, and the model built on them: on desktop each stat sits in its own monitor bezel (cool) or
  window (warm), with an operator silhouetted at the consoles below. On phone the scene is a calm
  room with a band of city lights. One stray yellow badge-like square was painted at the right edge,
  outside the safe area and off screen in the player.
- **Landing regressed.** The hero layout has no panels, so its conditioning image is only the
  palette gradient, and at strength 0.82 the model repainted that gradient: a plain radial glow on
  desktop, a flat field with a stray dot on phone. The cassette from the first run is gone.

So conditioning on structure works where there is structure. Frames whose drawing is nearly empty
need either more freedom (a higher strength) or a subject shape in the drawing; that is the next
experiment. Total fal calls across the three runs: 28.

### 2.4 More freedom for empty drawings

The engine now sets `freedom: 0.95` (fal `strength`) when panels and media frames cover under 2 %
of the canvas; in the demo that is landing and the two stub tapes. Login and dashboard keep their
keys and cached scenes. The landing re-render did not produce scenes: fal answered 503 (upstream
connection reset) for desktop and then 403 `User is locked. Reason: TOP_UP.` for phone, so the
account needs credit before this can be judged. Both scenes fell back to flat, as designed; the
renderer now also stops calling fal after a 401, 402, or 403, so a locked account costs one
failed call rather than one per scene and prefetch.

**After the top-up** (6 fal calls): the subject came back. Desktop tries painted a light streak, a
moon, and a backlit cassette with reflections; the phone painted a small cassette. OCR found no
lettering in any of them. But the model puts its subject dead centre, which on the landing page is
where the headline and subtitle sit: all four desktop tries failed region validation as busy there,
so the served scene is try 4 with flat fills patched into those two regions. In the player the
patch reads as a dark card behind the headline, with the cassette's glow above it and its
reflections below; most of the cassette is hidden. The phone scene passed on its second try.

### 2.5 Steering the subject into free space (did not work at this strength)

When `freedom` is set, the engine now finds the largest empty rectangle in the safe area (for the
landing page, the band between the nav row and the headline, at both sizes) and steers the subject
there twice: the prompt says "the main subject placed in the upper part of the frame, across its
width, nothing in the middle band of the frame", and the scene drawing moves its glow and vignette
onto that band.

Result (2 fal calls, both passed first time): the model ignored both. Each scene is a small
glowing cassette dead centre with its own centred halo. At strength 0.95 FLUX [dev] image-to-image
takes almost nothing from the drawing, and it does not follow placement words. In the player the
small cassette sits directly under the subtitle, which is worse for legibility than v3's patched
card. It passed validation because spread is averaged over the whole subtitle region and a small
object barely moves it.

Two follow-ups, in order:

1. **Validation gap.** Check spread over tiles of each reserved region, not the whole region, so a
   small object behind a few words fails.
2. **Real placement.** Prompt words and glows are suggestions; an inpainting endpoint with a mask
   is a constraint. Generating the subject only inside the free-area mask would put it there by
   construction.

Totals: 36 fal calls that returned an image, plus three refused (one 503, two 403s).

### 2.6 Tile spread, and re-checking the cache (no fal calls)

Calibrated on every fal image in the cache. No tile size separates "a dark object behind words"
from "a lit monitor bezel or city lights behind words": v4's subtitle tiles reach about 35, and the
good cool dashboard's bezels 31–37. By the spec both mean the area behind text is not calm, so the
threshold is the stricter reading: the worst 64-px tile at or below 30, alongside the whole-region
24. `videotape render --cache-only` then re-checked the eight cached scenes:

| Scene | Whole / worst tile | Result |
|-------|--------------------|--------|
| landing v4, desktop | sub 16 / 34.8 | failed, subtitle patched |
| landing v4, phone | sub 19.8 / 74.3 | failed, subtitle patched |
| dashboard desktop, cool | watch 16.9 / 31.4, subs 17.7 / 32.9 | failed, both patched inside their monitors |
| login (both), dashboard warm desktop, both phone dashboards | all ≤ 30 | passed |

The cool dashboard is the cost of the stricter reading; its two patches sit inside the monitor
screens and read as dark cards.

### 2.7 Proposal: place the subject by inpainting (not yet built)

Inpainting repaints only inside a mask, so a subject masked to the largest free area cannot land
behind text. Candidates checked on fal's model pages (2026-10-22):

| Endpoint | Inputs | Price |
|----------|--------|-------|
| `fal-ai/flux-lora/inpainting` | `image_url`, `mask_url`, `prompt`, `strength` (default 0.85), `seed`, steps, guidance, `sync_mode` | $0.035 / MP |
| `fal-ai/flux-pro/v1/fill` | `image_url`, `mask_url`, `prompt`, `seed`, `sync_mode`; no `strength` | $0.05 / MP |

Neither page states whether white or black marks the area to repaint; one probe call settles it.
The plan: an optional `subject` on frames (the scene text names the whole picture; the subject is
what goes in the free area); the renderer first paints the backdrop as today, then inpaints the
subject into a feathered mask of the free area; the mask and subject prompt join the cache key;
validation is unchanged. A 1920 × 1080 scene is about 2 MP, so the inpainting pass is about $0.07
(flux-lora) or $0.10 (fill) per scene on top of the backdrop.

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

## 7. UI as a Game: providers and engines (checked 2026-10-23)

For the "UI as a Game" redesign: a server-side scene runtime on a TypeScript web engine, streamed
to thin clients over WebRTC, with L1 (generated assets), L2 (live neural restyle) and, later, L3
(world models). Nothing here was measured; figures are vendor or paper claims.

**Tags.** [C] confirmed on an official source (vendor docs, API reference, pricing page, repo,
model card, official blog) on the date above. [S] secondary coverage only, unverified. [U] official
sources disagree or are unclear. "Not found" means official sources turned up nothing.

### 7.1 Real-time world models (L3) and real-time video-to-video (L2)

| System | Access | Speed, resolution | Conditioning | Price | Licence |
|--------|--------|-------------------|--------------|-------|---------|
| Genie 3 / Project Genie (Google DeepMind) | Consumer only: Google Labs prototype for Google AI Ultra ($200 plan), 18+, rolling out globally since 2026-05-19 [C]. Developer API: not found (DeepMind model page, Google blog, Vertex release notes) | 720p, 20–24 fps; consistent for a few minutes, memory of changes about 1 min [C] | Text and image prompts; Street View grounding for US places [C]. Video-stream, depth or segmentation input: not found | Subscription only | Proprietary |
| Odyssey-2 Pro (Odyssey) | **Public developer API**: account, API key, API License Agreement [C]. Interactive, broadcast and offline-simulation endpoints [C] | A new frame every 50 ms (about 20 fps) [C]. Output size not stated; input images resized to 1280×704 or 704×1280 [C]. Streams capped at 150 s, connections at 60 min by default [C] | Text, start image, mid-stream prompts via `interact()`; model is action-conditioned [C]. Video-stream, depth, segmentation input: not found | Not found. The 2025 Odyssey-1 demo cost $1–2 per user-hour in infrastructure [C, old] | Proprietary; JS SDK `@odysseyml/odyssey` MIT [C] |
| Odyssey-3, 3 Pro, 3 Flash | Browser research preview; developers asked to get in touch [C]; announced 2026-10-08 [C] | 832×480 (3), 1280×720 (3 Pro) [C]; fps not stated | Text, actions and events, prior observations [C] | Not found | Not found |
| GWM Worlds 2 (Runway) | Research preview behind a contact form; no public API [C]. Runway's API has one realtime model, Characters (`gwm1_avatars`, talking avatars, 2026-08-06) [C] | 720p at 24 fps with 48 kHz audio [C] | WorldPrompt (scene, subjects, laws, first frame), timestamped text actions, per-frame camera pose, prefilled-video continuation [C] | Worlds: not found. Characters: $0.02 to start, then $0.02 per 6 s [C] | Proprietary |
| Lucy 2.5 (Decart) | Public self-serve API, free trial credits [C] | 1280×720 in docs [C]; fps not stated. Only official fps found: 720p at 20 fps for the Lucy 2 RT preview, 2026-01 [C]. 1080p and 30 fps appear in launch coverage [S] | Live video stream plus text prompt and/or reference image; self-anchoring on by default [C]. Depth or segmentation: not found | $0.02/s; fast mode $0.04/s [C] | Proprietary service; SDK `@decartai/sdk` MIT [C] |
| Lucy Restyle 2 (Decart) | Same; Mirage was renamed "Lucy Restyle Live" in 2026-03, and MirageLSD is no longer on the price list [C] | 720p [C] | Live video stream plus text prompt [C] | $0.01/s realtime or batch [C] | As above |
| Oasis 3 Preview (Decart) | API key; gRPC client `decart-oasis`; enterprise pricing on request [C] | 768×512, three camera views, 4 frames per `infer` call [C]; under 200 ms end-to-end [S] | Text scene prompt plus throttle and steering; driving only [C] | $0.02/s [C] | Proprietary. Older Oasis 500M weights: MIT [C] |
| Cosmos 3 (NVIDIA) | Open weights; browser trials on build.nvidia.com; self-host via NIM or vLLM [C]. Hosted price: not found | Super 64B (H200/B200), Nano 16B (H100, RTX Pro 6000, B200), Edge 4B (Jetson Orin/Thor) [C]; real-time fps not stated | Nano-Sim-Transfer: autoregressive transfer from depth, segmentation, edge, blur [C]. Action-conditioned sim variants; "Interactive World Simulation" news 2026-10 [C] | Self-host | OpenMDW-1.1, code and models [C]. Transfer 2.5: code Apache-2.0, weights NVIDIA Open Model License; no longer developed [C] |
| Waypoint-1.5 (Overworld) | Open weights; no hosted inference provider [C] | Up to 720p: 56 fps (4 steps, RTX 5090), 72 fps quantised (RTX 5090), 30 fps quantised (RTX 3090) [C] | Start image or video, keyboard and mouse; text in the diffusers example [C] | Self-host | Apache-2.0 [C] |
| HY-World 1.5 WorldPlay (Tencent) | Open weights [C] | 24 fps streaming, 480p checkpoints [C]; GPU behind the real-time claim not stated | Image or text, keyboard, mouse, camera trajectory [C] | Self-host | Tencent community licence; not valid in the EU, UK or South Korea [C] |
| RTFM (World Labs) | Research-preview demo; no API found [C] | "Interactive framerates" on one H100 [C] | Not found | Not found | Not found |
| StreamDiffusion via Daydream | Hosted API on Livepeer GPUs [C, Livepeer docs] | Sub-second latency [S] | Input video stream; ControlNets including depth [S] | Not found | Not checked |

Licences that §5 left open, from model-card metadata [C]: Matrix-Game 2.0 MIT; Krea Realtime 14B
(`krea/krea-realtime-video`) Apache-2.0.

**Findings.**

- No Genie 3 developer API exists [C, by absence]. Odyssey-2 Pro does have a public API, which
  corrects §1's "unclear developer access"; it has no published price and no structural input.
- Decart is the only hosted, self-serve video-in, video-out service found. It takes a WebRTC
  video stream, so the engine's render can be the input. No hosted service documents depth,
  segmentation or object-ID conditioning; structure reaches the model only through the pixels we
  send. Cosmos 3 Sim-Transfer is the only model found that takes depth and segmentation as explicit
  controls; it is self-hosted and has no real-time figure.
- Decart's realtime SDKs moved onto LiveKit in 2026-05, and its JS SDK has measured glass-to-glass
  latency since 2026-08 [C]. Its public status page probes `lucy-2.1` with headless Chromium on
  Cloud Run in several GCP regions; values are shown only as charts [C].
- Open L3 weights that fit one consumer GPU now exist (Waypoint-1.5, Apache-2.0; vendor figures).

### 7.2 Generated worlds as assets (L1)

**World Labs Marble: the World API exists and is self-serve** [C unless marked].

| Item | Detail |
|------|--------|
| Call | `POST /marble/v1/worlds:generate` returns an operation; poll `/operations/{id}`; "usually about 5 minutes" per world |
| Models | `marble-1.0-draft`, `marble-1.0`, `marble-1.1` (default), `marble-1.1-plus` (sizes the world dynamically) |
| Inputs | Text; image (panorama detected automatically); multi-image (4, or 8 with `reconstruct_images`); video up to 100 MB |
| Price | $1 per 1,250 credits, $5 minimum, billed apart from the Marble app. Per world: draft $0.12–0.20, 1.0 and 1.1 $1.20–1.28, 1.1-plus $1.20–2.48. HQ GLB export 3,500 credits ($2.80); PLY export free |
| Rate limit | About 3 starts a minute and 60 an hour by default; more on approval |
| Assets | `splats.spz_urls`, `mesh.collider_mesh_url`, `mesh.full_res_mesh_url`, `mesh.hq_mesh_url`, `imagery.pano_url`, `thumbnail_url`, `caption`, and `semantics_metadata` (`metric_scale_factor`, `ground_plane_offset`) |
| Export specs | SPZ and PLY about 2M splats (500k low-res); collider GLB 100–200k triangles; HQ GLB about 600k triangles textured or 1M vertex-coloured, up to an hour, 4 an hour; panorama 2560×1280 |
| Axes | OpenCV convention; flip Y and Z for OpenGL or three.js; Marble's viewer rotates generated SPZ 180° about X |
| Structure in | `pano:depth_to_rgb`: a depth panorama (EXR or PNG) plus a prompt gives an RGB panorama; price per call not stated |
| Engines | Export guides for Unreal, Unity, Blender, Houdini, and Spark (three.js) |
| Terms | ToS effective 2026-01-21: paid and API users own outputs and may use them commercially; free users are non-commercial only |

[U] The Marble export docs say commercial rights "come with the Pro plan"; the ToS grants them to
all paid accounts. The API pricing page says API credits do not expire; ToS §6.7(c) says they
expire one year after purchase. Get World Labs to confirm in writing before relying on either.
World Labs also announced Atlas (2026-09-01), an omni model that outputs splats, depth and video
and "will power future versions of Marble"; early access by form only [C].

**Tencent HunyuanWorld** [C].

| Version | Date | Output |
|---------|------|--------|
| 1.0 | 2025-07-26 | Panorama proxy turned into a semantically layered mesh, foreground layers chosen by label; Draco export |
| 1.0-lite | 2025-08-15 | Quantised for consumer GPUs such as the 4090 |
| Voyager | 2025-09-02 | RGB-D video diffusion |
| 1.1 WorldMirror | 2025-10-22 | 3D from video or multi-view images |
| 1.5 WorldPlay | 2025-12-17 | Real-time interactive video (7.1) |
| HY-World 2.0 | 2026-04-16; weights through 2026-05-18 | Meshes or Gaussian splats, plus depth, normals, cameras and point clouds, from text, images or video. Weights: WorldMirror-2 (~1.2B), HY-Pano-2 (~80B), WorldStereo-2 (~17B). A 2.1 update was announced for 2026-07; not checked |

Every version ships under a Tencent community licence that "does not apply in the European Union,
United Kingdom and South Korea" and needs Tencent's separate grant above 1M monthly active users
[C]. Hosted: fal runs HunyuanWorld 1.0 as `fal-ai/hunyuan_world/image-to-world`, returning one
`world_file` [C]; price not found.

**Other world and scene generators.**

| System | Output | Access | Terms |
|--------|--------|--------|-------|
| SpAItial Echo-2 | Gaussian-splat worlds (SPZ, SOG) from text or one image [C]; mesh export [S]; 5–10 min each [S] | REST API, docs.spaitial.ai [C] | Pricing not found |
| NVIDIA Lyra 2.0 | Image plus camera path to video to 3DGS `.ply`; about 9 min per 80 frames on one H100, about 35 s distilled [C] | Open code and weights [C] | Code Apache-2.0; weights under NVIDIA's internal research licence, not for products [C] |
| Blockade Labs Skybox AI | Equirectangular panoramas 1K–8K (16K on model 3), HDRI, cube maps, 2K depth-map PNG [C] | API; price via sales [C] | Not checked |
| Hunyuan3D v3.1 on fal (props) | Image to 3D object [C] | fal API | Not checked |

**Image models for 2.5D layered sets.**

| Model | What it gives | Licence, access |
|-------|---------------|-----------------|
| Qwen-Image-Layered | Splits an image into a chosen number of RGBA layers (3–8 shown); 640 or 1024 buckets; 20B [C] | Apache-2.0 [C]; no Hugging Face inference provider; hosted on Replicate [C] |
| OpenAI GPT Image | `background: "transparent"` with PNG or WebP; support varies by model, preview on gpt-image-2 [C]; a forum report of errors on gpt-image-2 [S] | Paid API |
| Depth Anything 3 | Monocular and metric depth for parallax layers | Mono, metric, base, small: Apache-2.0; large any-view: CC BY-NC 4.0 [C] |
| Apple Depth Pro, SHARP | Depth; single image to 3DGS | `apple-amlr` licence per model-card metadata [C]; terms not read |

### 7.3 TypeScript web engines for the scene runtime

| | Babylon.js | PlayCanvas | three.js |
|-|------------|------------|----------|
| Licence, version | Apache-2.0; `@babylonjs/core` 9.32.0; 9.0 announced 2026-03-26 [C] | MIT; `playcanvas` 2.23.3 [C] | MIT; r186, 2026-09-24 [C] |
| WebGPU | WebGPU engine; 9.0 features (clustered lighting, volumetrics) on WebGPU and WebGL 2 [C] | Manual lists "WebGPU (Beta)" with automatic WebGL 2 fallback [C] | `WebGPURenderer` with WebGL 2 fallback [C]; `WebGLRenderer` gets no big new features [C]; a maintainer called `WebGPURenderer` experimental [S, forum, 2025] |
| Headless, server | `NullEngine` "can be used in server side scenario or for testing": scene logic, no pixels [C]. Pixels need a browser (Puppeteer) [S] or Babylon Native (MIT; Windows, macOS, iOS, Android, Linux) [C] | `NullGraphicsDevice` or `backend="null"` for Node: no pixels [C] | No Node renderer. WebGL 1 removed in r163 [C]; headless-gl is WebGL 1 with experimental WebGL 2 [C] |
| Text | SDF text in 9.0 [C]; MSDF `TextRenderer` in `@babylonjs/addons`, WebGL and WebGPU [C, official forum, 2025-05] | MSDF fonts: TTF and OTF converted to an MSDF atlas; `@playcanvas/font-tools` [C] | Mesh text only built in; troika-three-text (SDF, MIT, active) [C]; three-mesh-ui (MSDF) idle since 2023-12 [C] |
| Picking | Ray picking; `GPUPicker` (unique-colour pass, async) [C] | `Picker`: ID-colour buffer, optional depth for the world point; works on splats [C] | `Raycaster`; three-mesh-bvh (MIT) for speed [C]; GPU ID picking only as an example [C] |
| Depth, object-ID | `GeometryBufferRenderer` types include DEPTH, NORMAL, POSITION, VELOCITY and OBJECT_ID [C, source]; `DepthRenderer`; Frame Graph v1 in 9.0 [C] | `CameraComponent.requestSceneDepthMap()` and `requestSceneColorMap()` [C]; the Picker buffer gives IDs [C] | `RenderTarget` with `depthTexture` and `count` for MRT; `webgpu_mrt` example [C]. Object-ID pass is ours to write |
| Gaussian splats | Built in: PLY, .splat, SPZ, SOG/SOGS; shadows; LOD streaming experimental; GPU picking through proxy meshes [C] | Built in: SOG recommended, SPZ via a shipped parser, PLY for interchange; streamed SOG LOD; WebGPU compute radix sort since 2.19.0 (2026-05-28) [C]; SuperSplat editor MIT [C] | Spark (MIT, World Labs, `@sparkjsdev/spark` 2.4.0): PLY, SPZ, SPLAT, KSPLAT, SOG; 2.0 (2026-04-14) adds LOD streaming and `.RAD`; targets WebGL 2 through `WebGLRenderer` [C]. `WebGPURenderer` support not stated |

Engine layers on three.js: React Three Fiber (MIT) and pmndrs/uikit (MIT text in its LICENSE,
though GitHub reports no SPDX id) [C]; not evaluated. Outside a browser, Dawn's Node binding
(`webgpu` on npm, 0.6.2) exposes WebGPU on Vulkan, Metal, D3D12 or a null backend [C]; npm says
MIT and GitHub says BSD-3-Clause [U]. Whether any of the three engines renders on it: not found.

**Reading.** None of the three renders pixels in plain Node. For all three, server-side pixels
mean a GPU-backed headless Chromium (7.4), or Babylon Native for Babylon. Babylon ships the most of
what grounding and L2/L3 conditioning need: an object-ID and depth G-buffer, a GPU picker, SDF and
MSDF text, and splats including SPZ. PlayCanvas leads on splats and WebGPU compute. three.js has
the largest ecosystem, but the object-ID pass and crisp text are add-ons, and Spark ties splats to
WebGL 2.

### 7.4 Cloud-streaming building blocks

| Block | What it is |
|-------|------------|
| Headless Chrome with GPU | Google's recipe for Linux with NVIDIA: `--headless=new --use-angle=vulkan --enable-features=Vulkan --disable-vulkan-surface --enable-unsafe-webgpu`; WebGL, WebGL 2 and WebGPU then report hardware acceleration "at reduced performance"; sandbox off; tested on Colab T4/V100 [C, 2024-01] |
| Chrome's own WebRTC encoder on headless Linux with NVENC | Not found |
| `@livekit/rtc-node` (Apache-2.0) | Publish raw frames from Node (`VideoSource`, `VideoFrame`) [C]. LiveKit's native WebRTC layer has NVENC (H.264, H.265, AV1) and VA-API encoders, picked with `LIVEKIT_PREFERRED_HW_ENCODER` [C, source]. Whether the npm binaries include NVENC: not verified |
| werift (MIT) | WebRTC written in TypeScript; active [C] |
| LiveKit Egress (Apache-2.0) | Opens Chrome on a URL and transcodes with GStreamer; built for recording and RTMP, Chrome sandbox off by default [C] |
| Selkies (MPL-2.0) | GPU-accelerated Linux desktop streaming to HTML5, started by Google engineers; plain WebSockets by default, WebRTC opt-in [C] |
| Neko (Apache-2.0) | Self-hosted virtual browser in Docker, streamed over WebRTC; calls itself an open alternative to Hyperbeam [C] |
| Pixel Streaming infrastructure (Epic, MIT) | Signalling and web front end for Unreal; encoder estimates: H.264 about 9 ms at 1080p and 24 ms at 4K (RTX 3060), AV1 about 9 and 16 ms (RTX 6000 Ada) [C] |

Client SDKs for the native shells: LiveKit Swift targets iOS 13+, macOS, Mac Catalyst and tvOS 17+,
with no watchOS target [C]; Decart ships JS, Python, Swift and Android SDKs [C]; Odyssey ships JS and
Python [C]. A WebRTC client for watchOS: not found.

**Latency figures.**

| Figure | Source | Kind |
|--------|--------|------|
| Just-noticeable touch latency: 69 ms direct, 96 ms indirect | Deber et al., as cited in Kämäräinen et al., MMSys 2017 | Lab study |
| Phone plus access network alone, before the wired path: about 70–107 ms on 2016 Android phones | Kämäräinen et al., MMSys 2017 | Measured |
| Going from 1 to 10 European server sites cut 90th-percentile network delay by about 20 ms | Same | Measured |
| One-way delay under 150 ms is "essentially transparent" for most applications; 400 ms is the planning ceiling; highly interactive tasks suffer below 100 ms | ITU-T G.114 (05/2003) | Standard |
| GeForce NOW with Reflex: click-to-pixel under 40 ms on RTX 4080 SuperPODs; method not stated | NVIDIA, CES 2023 | Vendor claim |
| Odyssey-2 Pro: a frame every 50 ms (generation interval, not glass-to-glass) | Odyssey docs [C] | Vendor claim |

### 7.5 Implications for Videotape

**L1 is usable today.** Marble's World API gives a world in about 5 minutes for about $1.20–2.50,
with SPZ splats, a collider GLB and metric-scale metadata, and commercial use on paid and API
accounts. Spark, Babylon and PlayCanvas all load SPZ. HunyuanWorld weights are not licensed in the
EU, UK or South Korea, so check where we operate before using them. For 2.5D sets,
Qwen-Image-Layered (Apache-2.0), transparent GPT Image output and Depth Anything 3 mono
(Apache-2.0) are usable now.

**L2 is usable today, with a constraint.** Decart's Lucy 2.5 and Lucy Restyle 2 take a WebRTC
stream at 720p for $0.01–0.04 a second ($36–144 per stream-hour). No hosted L2 takes depth or IDs,
so the engine must render a conditioning view designed for the model, and crisp text and controls
should be composited after L2, as §1 already concluded. That means either the server takes the
restyled stream back and composites (an extra network leg) or the thin client overlays a UI layer
itself. A self-hosted L2 with explicit depth and segmentation (Cosmos 3 Sim-Transfer) exists, but
real-time is unproven.

**L3 is not usable for products yet.** Genie 3 and GWM Worlds 2 have no public API; Odyssey-2 Pro
has one but no published price; Waypoint-1.5 and WorldPlay are self-hostable. None takes engine
state beyond a start image, actions and camera.

**Engine.** All three engines cover the needs in a browser; none renders in plain Node. Plan on a
GPU headless Chromium per session, or Babylon Native. Babylon has the most built in for grounding.

**Main unknowns.** Glass-to-glass latency with L2 in the loop (two WebRTC legs); sessions per GPU
for headless Chromium, and whether its encoder or NVENC through LiveKit does the encoding; whether
restyling keeps controls readable; Odyssey pricing; World Labs' two term conflicts; a watchOS
client.

### 7.6 Sources

L2 and L3:
- https://deepmind.google/models/genie/ · https://blog.google/innovation-and-ai/models-and-research/google-deepmind/project-genie-expands/
- https://documentation.api.odyssey.ml/ · https://documentation.api.odyssey.ml/odyssey-2-overview · https://documentation.api.odyssey.ml/api-quick-start · https://documentation.api.odyssey.ml/stream-duration-limits · https://odyssey.systems/meet-odyssey-3 · https://odyssey.ml/introducing-interactive-video
- https://runway.com/research/introducing-gwm-worlds-2 · https://docs.dev.runwayml.com/guides/models/
- https://docs.platform.decart.ai/getting-started/overview.md · https://docs.platform.decart.ai/getting-started/models · https://docs.platform.decart.ai/getting-started/pricing · https://docs.platform.decart.ai/models/realtime/lucy-2.5 · https://docs.platform.decart.ai/models/realtime/oasis-3 · https://docs.platform.decart.ai/changelog · https://docs.platform.decart.ai/resources/faq · https://lucy-status.decart.ai/
- https://aireiter.com/blog/lucy-2-5-realtime-video-guide (secondary) · https://startupfortune.com/decart-opens-its-world-model-to-developers-for-two-cents-a-second-betting-it-can-own-physical-ais-simulation-layer-before-the-big-players-build-one-themselves/ (secondary)
- https://github.com/NVIDIA/Cosmos · https://github.com/nvidia-cosmos/cosmos-transfer2.5
- https://huggingface.co/Overworld/Waypoint-1.5-1B · https://github.com/Tencent-Hunyuan/HY-WorldPlay · https://www.worldlabs.ai/blog/rtfm · https://github.com/etched-ai/open-oasis
- https://docs.livepeer.org/v2/gateways/using-gateways/gateway-providers/daydream-gateway · https://lobehub.com/ja/mcp/qianghan-ddmcp (secondary)
- https://huggingface.co/krea/krea-realtime-video · https://huggingface.co/Skywork/Matrix-Game-2.0

L1 and 2.5D:
- https://docs.worldlabs.ai/api · https://docs.worldlabs.ai/api/reference/worlds/generate · https://docs.worldlabs.ai/api/reference/worlds/get.md · https://docs.worldlabs.ai/api/pricing · https://docs.worldlabs.ai/api/rate-limits.md · https://docs.worldlabs.ai/api/faq · https://docs.worldlabs.ai/api/rendering-spz.md · https://docs.worldlabs.ai/api/reference/pano/depth_to_rgb.md
- https://docs.worldlabs.ai/marble/export/specs · https://docs.worldlabs.ai/marble/export/gaussian-splat/index.md · https://worldlabs.ai/terms-of-service · https://www.worldlabs.ai/blog/atlas · https://www.worldlabs.ai/blog/spark-2.0
- https://github.com/Tencent-Hunyuan/HunyuanWorld-1.0 · https://github.com/Tencent-Hunyuan/HY-World-2.0 (and each repo's licence file) · https://fal.ai/models/fal-ai/hunyuan_world/image-to-world/api
- https://docs.spaitial.ai/ · https://spaitial.ai/use-cases · https://radiancefields.com/spaitial-ai-unveils-first-frontier-model-echo (secondary)
- https://github.com/nv-tlabs/lyra · https://api-documentation.blockadelabs.com/api/skybox-exports.html · https://skybox.blockadelabs.com/api-membership · https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d
- https://huggingface.co/Qwen/Qwen-Image-Layered · https://replicate.com/qwen/qwen-image-layered · https://developers.openai.com/api/docs/guides/image-generation · https://github.com/ByteDance-Seed/Depth-Anything-3 · https://huggingface.co/apple/DepthPro · https://huggingface.co/apple/Sharp

Engines:
- https://github.com/BabylonJS/Babylon.js (`packages/dev/core/src/Rendering/geometryBufferRenderer.pure.ts`, `Engines/nullEngine.pure.ts`) · https://blogs.windows.com/windowsdeveloper/2026/03/26/announcing-babylon-js-9-0/ · https://blogs.windows.com/windowsdeveloper/2026/04/02/part-3-babylon-js-9-0-openpbr-and-additional-engine-updates/ · https://doc.babylonjs.com/features/featuresDeepDive/mesh/gaussianSplatting · https://doc.babylonjs.com/features/featuresDeepDive/mesh/interactions/picking_collisions · https://forum.babylonjs.com/t/msdf-text-renderer/58406 · https://forum.babylonjs.com/t/nullengine-and-server-side-rendering/52907 · https://github.com/BabylonJS/BabylonNative
- https://developer.playcanvas.com/user-manual/graphics/ · https://developer.playcanvas.com/user-manual/engine/running-in-node/ · https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/ · https://developer.playcanvas.com/user-manual/editor/assets/inspectors/font/ · https://api.playcanvas.com/engine/classes/Picker.html · https://api.playcanvas.com/engine/classes/CameraComponent.html · https://github.com/playcanvas/engine/releases/tag/v2.19.0
- https://threejs.org/docs/pages/WebGPURenderer.html · https://github.com/mrdoob/three.js/releases/tag/r163 · https://github.com/mrdoob/three.js/blob/dev/src/core/RenderTarget.js · https://discourse.threejs.org/t/webgpurenderer-forcewebgl-true-vs-webglrenderer/87805/2 (secondary) · https://github.com/sparkjsdev/spark · https://github.com/protectwise/troika · https://github.com/gkjohnson/three-mesh-bvh · https://github.com/stackgl/headless-gl · https://github.com/dawn-gpu/node-webgpu

Streaming and latency:
- https://developer.chrome.com/blog/supercharge-web-ai-testing
- https://github.com/livekit/node-sdks · https://github.com/livekit/rust-sdks (`webrtc-sys/src/video_encoder_factory.cpp`) · https://github.com/livekit/egress · https://github.com/livekit/client-sdk-swift
- https://github.com/shinyoshiaki/werift-webrtc · https://github.com/selkies-project/selkies · https://github.com/m1k1o/neko · https://github.com/EpicGamesExt/PixelStreamingInfrastructure · https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-pixel-streaming-reference
- https://users.aalto.fi/~siekkine/pub/kamarainen17mmsys.pdf · https://www.itu.int/dms_pubrec/itu-t/rec/g/T-REC-G.114-200305-I!!SUM-HTM-E.htm · https://www.nvidia.com/en-us/geforce/news/gfecnt/20231/ces-2023-reflex-games-1440p-360hz-monitors/

## 8. App stores and streamed interfaces (checked 2026-10-23)

The question: will the stores accept a Videotape export, a thin native shell (a system web view
running our web client on iOS and Android, a desktop shell elsewhere) whose screens are rendered on
our server and streamed over WebRTC, and whose screens and flows can change without a store update?
The shell owns native text input and the accessibility tree, and later camera, files,
notifications and payments. Tags as in §7. Guideline wording is paraphrased under its number; one
line is quoted. Apple's guidelines were last updated 2026-10-16 [C]; Microsoft Store Policies are
version 7.20, dated 2026-09-14 [C]. Nothing here was tested by a submission.

### 8.1 Apple App Store (iOS, iPadOS; Mac in 8.3)

| Area | Guideline (paraphrased) | Bearing on Videotape |
|------|-------------------------|----------------------|
| Thin clients | 4.2.7 Remote Desktop Clients sets rules for apps that mirror specific software on a user-owned host over a LAN, and ends with (e): "Thin clients for cloud-based apps are not appropriate for the App Store." [C] | The one rule that reads directly on us. It sits under remote desktop apps, so whether it binds other apps is [U]. Read plainly, an app whose every screen is server-rendered video is a thin client for a cloud-based app. |
| Streaming games | The old 4.9 "Streaming games" was deleted on 2024-01-25 and its subject moved into 4.7; 4.9 is now Apple Pay [C]. The 2020 requirement that each streamed game be its own App Store app went with it [C] | 4.7 permits software that is not in the binary: HTML5 or JavaScript mini apps and mini games, streaming games, chatbots, plug-ins, and emulator games [C]. Streamed apps that are not games are not on that list. |
| Hosted software, 4.7.1–4.7.5 | The host is responsible for each piece: privacy (5.1) and purchase (3.1) rules, filtering, reporting and blocking (4.7.1); no exposing native APIs to it without Apple's prior permission (4.7.2); consent each time data or permissions are shared with it (4.7.3); an index of all of it with universal links (4.7.4); age gating above the app's rating (4.7.5) [C] | Applies when one binary offers several streamed titles. A shell that hands camera, files or notifications to third-party streamed apps needs Apple's permission first. The Mini Apps Partner Program (85 % of qualifying IAP) covers HTML5 or JavaScript mini apps under DPLA 3.3.1(B) [C]; video is not mentioned. |
| Minimum functionality | 4.2: the app must offer more than a repackaged website and be useful and app-like [C]. 4.2.2: not mainly web clippings, aggregated content or links [C]. 4.2.6: apps from a commercial template or app generator are rejected unless the content owner submits them; one "picker" app hosting all clients is the alternative [C]. 4.3(a): no separate bundle IDs for variants of one app [C] | The web view must run a bundled client, not our website. If other companies build on Videotape, each export is submitted from the client's own account and must differ in substance. |
| Code, and changes after review | 2.5.2: no downloading or running code that adds or changes features [C]. DPLA 3.3.1(B): interpreted code may be downloaded only if it keeps the app's advertised primary purpose, does not bypass OS security, and does not create a store for other apps [C]. 2.3.1(a): every new feature, function and product change must be described specifically in the review notes [C]. 2.3.12: significant changes go in What's New [C]. 2.5.19 (added 2026-10-16; the policy was formerly part of 2.3.1): no hidden, dormant or undocumented features [C] | A video stream is not code, so 2.5.2 does not touch the pixels. 2.3.1(a) and 2.5.19 are about features, not code: a flow switched on server-side after review is an undocumented feature. Changes to content, copy, layout and style inside reviewed features look safe; where Apple draws the line is [U]. |
| Payments | 3.1.1: unlocking features, subscriptions or premium content requires in-app purchase [C]. 3.1.1(a), 3.1.3: buttons and links to other purchase methods are allowed on the US storefront, and elsewhere only by entitlement in some regions [C]. 3.1.3(e): physical goods and services used outside the app must not use IAP [C]. 3.1.2(a): a streaming-game subscription may be shared across apps if the games come from the App Store and nobody pays twice [C] | Pixels drawn by the server are still the app. A payment form painted in the stream for digital goods breaks 3.1.1 outside the US storefront. |
| Login, privacy | 4.8: social or third-party login for the primary account needs an equivalent option that collects only name and email, can hide the email and does not track for ads; apps with only their own accounts are exempt [C]. 5.1.1(v): in-app account deletion when accounts can be created; no login without account-based features [C]. 5.1.1(i): privacy policy linked in metadata and in the app [C]. 5.1.2(i): disclose and get explicit permission before sharing personal data, with third-party AI named [C]. 2.5.14: consent plus a visible or audible indicator when recording camera, microphone or screen [C]. 2.1: demo account and a live backend during review [C] | The session is data collection: touches, typed text and camera frames go to our server, and on to Decart when L2 restyles frames that show user content. Privacy details and consent must cover both legs. |
| Accessibility | No App Review guideline requires accessibility [C, by absence]. Accessibility Nutrition Labels (VoiceOver, Voice Control, Larger Text, Dark Interface, Differentiate Without Color Alone, Sufficient Contrast, Reduced Motion, Captions, Audio Descriptions) are voluntary for now; Apple says they will become required for new apps and updates over time [C]. A feature may be claimed only if every common task (first launch, login, purchase, settings, core function) works with it [C] | Not a blocker today. Video alone supports none of the nine; any claim depends on the shell's tree and on the server following the device's text size, contrast, motion and appearance settings. |
| Upkeep | Section 4 intro: apps that stop working or degrade may be removed at any time [C] | A dead server or a bad network makes a degraded app; the shell needs its own offline and reconnect screens. |

### 8.2 Google Play

| Area | Policy (paraphrased) | Bearing on Videotape |
|------|----------------------|----------------------|
| Executable code | Device and Network Abuse: apps update only through Play and may not fetch executable code (dex, JAR, .so) from elsewhere; code running in a VM or interpreter, such as JavaScript in a web view, is exempt, but interpreted code loaded at run time must not enable policy violations [C] | Video is not code. A remotely loaded web client is allowed in principle; bundling it is simpler. |
| Hidden features, changes | Deceptive Behavior §5: functionality must be reasonably clear; no hidden, dormant or undocumented features, including ones built to be switched on remotely; no remote code that adds features absent at review; the app must behave the same for users and reviewers [C]. §3: apps that change significantly between versions without telling users, and without updating the listing, violate it [C]. Metadata must describe and show the app's real functionality [C] | Same constraint as Apple 2.3.1(a) and 2.5.19: server-side changes are fine for content and presentation, not for undocumented new features. No review-only mode. |
| Webviews, spam | Spam: no apps whose main purpose is affiliate traffic or a webview of a site without its owner's permission [C]; no apps that only repeat other apps' experience (Repetitive Content) [C] | We own the content, so the webview rule does not apply. Many near-identical exports risk Repetitive Content. |
| Minimum functionality | Apps need basic, adequate utility as mobile apps; apps with only limited functionality and content are not allowed; no crashing, freezing or abnormal behaviour [C] | A lower bar than Apple 4.2. A blank stream on a bad network reads as broken; the shell needs native offline states. |
| Cloud gaming, streamed apps | No Play policy specific to cloud gaming or streamed apps found [C, by absence]. Cloud gaming services such as GeForce NOW are distributed on Play [S] | Nothing comparable to Apple 4.2.7(e) found. |
| Payments | Play Billing is required for paid downloads and in-app digital goods, including subscriptions (game, video and others) and cloud software and services; physical goods and services and peer-to-peer payments are exempt [C]. Alternative billing (§8) and external links (§9) by enrolment in eligible regions [C]. US: since 2025-10-29 Google does not require Play Billing or ban links out for US users; a revised settlement of 2026-03-04 awaits the court [C]. Billing choice in the US, EEA and UK from 2026-06-30, with a separate 5 % fee only on Play Billing [C] | Same design as Apple: the shell owns purchases. Outside the US and enrolled programmes, the streamed UI must not take payment for digital goods. |
| Accessibility API | Applies to apps that implement an AccessibilityService: only tools that help people with disabilities may declare `isAccessibilityTool`; autonomous planning and acting through the API is banned; other uses need in-app disclosure and consent [C] | Exposing our own tree (virtual views, `AccessibilityNodeProvider`) needs no AccessibilityService, and the policy does not address it [U]. Do not ship a service. |
| Accounts, AI content | Apps with account creation need an in-app deletion path and a web link to request deletion [C]. Apps that generate images or video from user prompts must let users report offensive output without leaving the app [C] | Applies when users prompt L1, L2 or L3 generation. A "report this screen" action in the shell also serves Apple 4.7.1. |

### 8.3 Mac App Store and Microsoft Store

- **Mac App Store.** The same guidelines apply, plus 2.4.5 [C]. 2.4.5(iv) is stricter than iOS: no
  downloading code *or resources* that add functionality or significantly change the app from what
  review saw; 2.4.5(vii): updates only through the Mac App Store [C]. Direct distribution
  (Developer ID, notarisation) avoids App Review; not re-checked in this pass.
- **Microsoft Store (Policies 7.20).** 10.2.2: no fundamentally changing or extending described
  functionality by dynamically included code [C]. 10.1.1: web apps must be published by the site
  owner, and the value must be clear on first run [C]. 10.1: remote-play and game-subscription
  products are listed as games [C]. 10.8.1: non-game PC products may use a secure third-party
  purchase API for digital items; games must use Microsoft's [C]. No rule against cloud thin
  clients found [C, by absence].

### 8.4 Risks and design responses

| # | Rule | Blocks or constrains when | Design response |
|---|------|---------------------------|-----------------|
| S1 | Apple 4.2.7(e) | A reviewer reads the export as a thin client for a cloud app | The shell does real native work in every session: native text editing, the accessibility tree, notifications, share sheet, files, camera, StoreKit, Sign in with Apple, offline and reconnect screens, the last state cached. Ask Apple before building the iOS shell (8.5). |
| S2 | Apple 4.7 | A non-game app leans on the streaming-games allowance | Do not present a non-game app as a game. Games rest on 4.7; other apps rest on S1. |
| S3 | Apple 4.2, 4.2.2; Play Spam | The shell loads our website in a web view | Bundle the web client in the binary and update it through the stores. |
| S4 | Apple 2.3.1(a), 2.3.12, 2.5.19, DPLA 3.3.1(B), Mac 2.4.5(iv); Play Deceptive Behavior; MS 10.2.2 | The server adds a feature or flow after review without an update | Each shell build carries a feature manifest, and the server serves only features in it. Content, copy, layout and style change freely; new features ship with a shell update and review notes. Same behaviour for reviewers and users. |
| S5 | Apple 4.7.1–4.7.5 | One binary hosts several streamed apps or games (a catalogue) | Default to one shell per app; no catalogue is then required. A catalogue needs an index with universal links, age gating, report and block, and Apple's permission before exposing native APIs to hosted apps. |
| S6 | Apple 4.2.6, 4.3(a); Play Repetitive Content | Videotape submits many template-like exports for clients | Each client submits from its own developer account; exports must differ in substance. |
| S7 | Apple 3.1.1; Play Payments; MS 10.8.1 | The streamed UI sells digital goods through its own form | Purchases are a shell capability: the server asks, the shell runs StoreKit or Play Billing, the server verifies the receipt. Storefront rules (US links, EEA and UK programmes) are server configuration. Physical goods use Apple Pay, Google Pay or cards. |
| S8 | Apple 4.8, 5.1.1, 5.1.2(i), 2.5.14; Play account deletion | The thin client skips duties the store checks on the device | The shell ships Sign in with Apple whenever social login is offered, in-app account deletion, a privacy policy link, consent before camera frames or user content reach third-party AI (Decart), and recording indicators. |
| S9 | Apple Accessibility Nutrition Labels | Labels become mandatory and video UI fails common tasks | Native tree plus server-side respect for OS settings (text size, contrast, reduced motion, appearance); claim only features that pass every common task. |
| S10 | Apple 2.1, Section 4; Play functionality | Review on a poor network, or a server outage | Servers up during review, a demo account, native error, offline and reconnect screens, and the latency budget met on cellular. |

### 8.5 Implications for Videotape

**Google Play: acceptable.** No Play rule against thin clients or streamed interfaces was found;
the webview rule targets other people's sites, and a video stream is not code. The constraints
are ordinary: Play Billing for digital goods outside the US and enrolled programmes, no remotely
activated undocumented features, an accurate listing, account deletion, and AI-content reporting.
**Microsoft Store: acceptable**, with the most permissive payment rules for non-game apps.

**Apple: uncertain, and the deciding question.** 4.2.7(e) says thin clients for cloud apps do not
belong on the App Store, and 4.7 allows streaming only for games. No Apple text supports the
assumption "acceptable with a native shell that owns text input, accessibility, and OS
integration"; it rests on a reviewer judging the shell to be more than a thin client. Native text
input and accessibility make the stream usable but do not change what the app is; OS integration,
native purchase and login, and offline behaviour carry more weight. A Videotape game is on firmer
ground under 4.7. Separately, on both stores, "features change without a store update" holds only
for content and presentation: new features switched on server-side conflict with Apple 2.3.1(a) and
2.5.19 and with Play's Deceptive Behavior policy, and on the Mac 2.4.5(iv) also names resources.

**The exported shell must include:** the bundled web client; native text input and the
accessibility tree; the OS features each app needs (notifications, share, files, camera); StoreKit
and Play Billing purchases; Sign in with Apple when social login is used; in-app account deletion;
a privacy policy and consent covering streamed input and third-party AI; report and block; native
offline and reconnect screens; and a feature manifest the server obeys.

**Confirm directly.** With Apple, before building the iOS shell: whether 4.2.7(e) applies outside
remote desktop apps; whether a non-game app streamed this way, with these native features, passes
4.2; where server-side change becomes a new feature under 2.3.1(a) and 2.5.19; and, for any
catalogue, what 4.7.2 permission involves. An external TestFlight build, which Apple reviews, is the
cheapest real probe. With Google: that a virtual accessibility tree needs no declaration, and the
US billing terms once the court rules on the settlement. In the EU, alternative distribution
reviews only a subset of guidelines (Notarization); whether 4.2 is in that subset was not checked.

**Design response (2026-10-23).** iOS clients render on the device from M1, fed scene state by the
engine; streaming stays on the web, Android, and desktop ([05-design-v2.md](05-design-v2.md),
decision K and §11.1).

### 8.6 Sources

Apple:
- https://developer.apple.com/app-store/review/guidelines/ (last updated 2026-10-16)
- https://developer.apple.com/news/?id=92th7e5i (2026-10-16 changes) · https://developer.apple.com/news/?id=7j1f99yf (2024-01-25: 4.7 rewritten, 4.9 deleted) · https://developer.apple.com/news/?id=xqk627qu (2020-09-11: original 4.9) · https://developer.apple.com/news/?id=0kjli9o1 (2024-04-05) · https://developer.apple.com/news/?id=ty0avr2s (2024-08-01: 4.7, 4.7.2, 4.7.3 added to Notarization)
- https://developer.apple.com/support/terms/apple-developer-program-license-agreement/ (3.3.1 A and B)
- https://developer.apple.com/programs/mini-apps-partner/
- https://developer.apple.com/help/app-store-connect/manage-app-accessibility/overview-of-accessibility-nutrition-labels

Google:
- https://support.google.com/googleplay/android-developer/answer/9888379 (Device and Network Abuse) · https://support.google.com/googleplay/android-developer/answer/17006354 (Deceptive Behavior)
- https://support.google.com/googleplay/android-developer/answer/9899034 (Spam) · https://support.google.com/googleplay/android-developer/answer/9898783 (Functionality, Content, and User Experience)
- https://support.google.com/googleplay/android-developer/answer/9858738 (Payments) · https://support.google.com/googleplay/android-developer/answer/15582165 (US users) · https://android-developers.googleblog.com/2026/06/play-expanded-billing.html
- https://support.google.com/googleplay/android-developer/answer/10964491 (AccessibilityService API) · https://support.google.com/googleplay/android-developer/answer/13327111 (account deletion) · https://support.google.com/googleplay/android-developer/answer/13985936 (AI-Generated Content)
- https://www.similarweb.com/app/google/com.nvidia.geforcenow/poland/ (secondary: GeForce NOW on Play)

Microsoft:
- https://learn.microsoft.com/en-us/windows/apps/publish/store-policies (version 7.20)
