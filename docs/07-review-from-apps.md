# Review: what five apps showed about the design

**Date:** 2026-10-23 · **Status:** decided and folded into [05-design-v2.md](05-design-v2.md) the
same day: Q16 and Q22 by Q24 of [08-leverage-review.md](08-leverage-review.md), Q17–Q21 and Q23 as
recommended (05 §18); F4–F27 are in 05 in the form the leverage review gave them, and F1, F2, F20,
and F26 are moot once every client renders · **Source:**
[06-getting-started.md](06-getting-started.md)

The getting-started guide was written as if Videotape existed, for a Python developer building
five kinds of app: a web app (the M1 demo), a video platform, a photo-sharing app, a chat app, and a
CRM. Each time the code needed something the design does not have, or the design promised
something an app would break, it became a finding here.

## 1. The short version

1. **Streamed clients were designed for games, and apps stress them differently.** Apps are mostly
   text, and video encoders blur text (F1). Apps are mostly scrolling, and a stream answers a
   finger one round trip late (F2). These two decide whether streamed clients can carry
   text-heavy apps at all, so E2 must measure them before M1.
2. **Not everything should be a prop.** A twelve-column contacts table is not a set of objects on a
   shelf. Games put dense information on screen-aligned panels and keep the world for the rest; the
   composer needs the same choice (F3).
3. **The intent model is a form model.** Every app beyond the demo needed collections, top-level
   destinations, detours that return a value, pushes from the app, a signed-in user, and addresses
   (F4–F8). These belong in the M1 schema.
4. **User content needs more than the design gives it.** Real text in any script with emoji (F14),
   photos and video as facts (F15), and a native player for video (F16).
5. **Server rendering sets product limits.** No end-to-end encryption (F22), no search-engine
   presence without a separate answer (F21), and sessions that cost money while idle (F20).

## 2. Findings at a glance

Severity: **M1** means the M1 schema, protocol, or composer must include it; **Experiment** means E1
or E2 must measure it before M1; **Decision** means a question for you (§4); **Later** means after
M1.

| # | Finding | Seen in | Severity |
|---|---------|---------|----------|
| F1 | Text through the video encoder | All; worst in docs, chat, CRM | Experiment, Decision (Q16) |
| F2 | Scrolling and dragging over a stream | Feed, chat, tables, board, docs | Experiment |
| F3 | Surfaces next to embodied props | CRM, docs, chat, long forms | M1, Decision (Q17) |
| F4 | Collections | All five | M1 |
| F5 | Hubs, calls that return, sheets | Video, social, chat, CRM | M1 |
| F6 | Events that do not come from the user | Chat, social, CRM, stories, video | M1 |
| F7 | Who is signed in | Every app with accounts | M1 |
| F8 | Addresses and deep links | Web, social, video, chat | M1 |
| F9 | Conditional components and empty states | CRM, video, social | M1 |
| F10 | Named actions, gestures, and keys | Social, chat, CRM | M1 |
| F11 | Instant feedback: validation and optimistic patches | Chat, social, CRM | M1 |
| F12 | Insets: keyboard, safe areas, hinges | Chat, every phone | M1 |
| F13 | Strings, locales, and right-to-left | All | M1 (schema) |
| F14 | A real text engine | Chat, social, CRM, any non-Latin UI | Experiment |
| F15 | Images and media are facts | Social, video, chat, CRM | M1 (decision text) |
| F16 | Native surfaces beyond the editor | Video, social, chat, CRM | Decision (Q18) |
| F17 | Rich text and HTML | Docs, social, chat, CRM | M1 |
| F18 | Selection, copy, find, print | Docs, chat, CRM | M1 |
| F19 | Charts | CRM, dashboard | Later |
| F20 | Idle sessions and their cost | CRM, video, any app left open | Experiment |
| F21 | Public pages and search engines | Web, social, video | Decision (Q19) |
| F22 | All content passes through the engine | Chat, social | Decision (Q20) |
| F23 | Links and downloads before M4 | Chat, docs, CRM | Decision (Q21) |
| F24 | Releases while users are mid-journey | All | M1 |
| F25 | Custom components | Video editing, maps, boards | Decision (Q23) |
| F26 | The developer's loop without a GPU | All | Decision (Q22) |
| F27 | SDK details | All | M1 (small) |

## 3. Findings

### A. Streamed clients

**F1 Text through the video encoder.** Decision E and goal G5 promise exact facts, and the engine
does draw them exactly. On streamed clients the next step is a lossy video encoder. Common stream
settings sample colour at a quarter of the resolution (4:2:0), which fringes coloured text; small
type smears at mobile bitrates; and streams often run below the screen's pixel density. Remote
desktop products use full-colour (4:4:4) or lossless text modes for this reason. A docs page, a
chat thread, or a CRM table is mostly small text.
*Proposal.* E2 measures text legibility after encoding: OCR accuracy and contrast on 12–16 px text,
on phones and desktops, at the target bitrates. It tries higher quality on text regions where the
encoder supports per-region quality, 4:4:4 where decoders support it, and the codecs' screen-content
tools. If none is good enough, surfaces are drawn by the client (Q16).
*Changes.* §11, §12, §15 (E2), §17.

**F2 Scrolling and dragging over a stream.** Content that follows a finger must move on the next
display frame, 8–16 ms. A stream answers in a round trip plus encoding and decoding; the design's
target is 100 ms. The object map gives instant feedback for presses, not for content that moves.
Feeds, chat threads, tables, the deal board, and long documents all scroll or drag.
*Proposal.* The object map declares scrollable regions and their content extents. The engine sends
frames with extra content beyond the visible edge, and during a gesture the client shifts the last
frame locally until the engine's frame catches up, as cloud VR does for head movement. Dragging lifts
a picture of the object, sent with the object map. iOS is unaffected, since it renders on the device
(decision K). E2 measures a fling through a feed and a drag on a board.
*Changes.* §5 (loops), §11 (client duties), §14 (`objects`), §15 (E2).

**F3 Surfaces next to embodied props.** The design embodies every component as a prop. That works
for a sign-in console, and fails for a contacts table, a docs page, a chat transcript, or a
thirty-field record. Games keep dense information on flat, screen-aligned panels (the HUD) and use
the world for the rest.
*Proposal.* The composer places each component either in the world as a prop, or on a **surface**:
a flat, screen-aligned panel that the world styles with its materials, palette, and type, and that is
itself a prop ("a glass pane", "a clipboard"). The composer chooses per component from its kind, its
density, and the screen; collections with comparable fields and long text default to surfaces.
Worlds declare their surface materials. Surfaces are also where F1, F2, F15, and F18 are easiest to
solve (Q16). This follows how games work, so it is not a trade against the vision.
*Changes.* §8, §9, §10, §13 (legibility checks on surfaces).

### B. The intent model

**F4 Collections.** v1's `list` showed labels from a bind. The apps needed:
an item template made of components; paged sources with cursors; nesting (shelves of videos);
grouping (deals by stage); selection (one, many, bulk); item states the composer and embodiment use
(mine, unread, pending, selected); order anchored at the end (chat); an empty state; and placeholders
so static actions can use the item (`vt.item("id")`). The composer needs shapes (table, cards, grid,
column, one at a time) chosen from the fields and the screen, and embodiment must work for ten
thousand items, which no shelf holds.
*Proposal.* A `collection` kind with `source` (a bind or `pages(loader)`), `item`, `fields`,
`group_by`, `order`, `anchor`, `select`, `item_states`, and `empty`; patch operations `append`,
`prepend`, `replace`, and `remove` by key; virtualised by the engine.
*Changes.* §6, §8, §9, §14. The demo's dashboard needs this, so it blocks M1.

**F5 Hubs, calls that return, sheets.** Four of the five apps have top-level destinations (home,
search, profile) with persistent navigation and a history per destination, and detours that return
a value (pick a company, confirm a deletion). Tapes have `jump` and `back` only, with one history.
*Proposal.* `hub(destinations)`: destinations are tapes, each with its own history, embodied by the
composer as a tab bar, a sidebar, a list, or a crown menu. `call(tape, then=handler)` and
`done(result)`: the result reaches the caller's handler as `ctx.result`; the composer may show a
call as a sheet over the caller.
*Changes.* §6; the reel's single history becomes one per destination.

**F6 Events that do not come from the user.** New messages, like counts, a colleague moving a deal,
a story's timer, a video ending. The app protocol only lets the engine call the app.
*Proposal.* The app process publishes patches to topics (`app.publish(topic, patch)`) or to a user
(`app.publish_to(user, patch)`); frames subscribe with `live=[...]` topic templates; the engine
applies the patch to every subscribed session as if a handler had returned `stay(patch)`. Frames run
timers (`after(seconds, then)`), and native surfaces report events such as `ended` (F16).
*Changes.* §6 (app protocol), §14. Chat and social cannot be built without it.

**F7 Who is signed in.** The engine keeps reels but does not know who the user is. It needs that to
resume a journey on another device, to address pushes to a user, to limit abuse per user, and to
end every session of a deleted account (design §11.1).
*Proposal.* Outcomes carry `sign_in=user_id` and `sign_out=True`; handlers and loaders see
`ctx.user`; reels are keyed by user and device. Credentials stay with the app.
*Changes.* §6, §14.

**F8 Addresses and deep links.** The web needs a URL per place, a working back button, and
bookmarks; social and video apps share links to a post or a video; a chat notification opens a
conversation.
*Proposal.* A frame may declare `address="/watch/{video_id}"`. The engine maps an address to a tape,
a frame, and data, runs the loader, and keeps the browser's history in step with the reel's.
Exports register the app's universal links and app links. This names frames that already exist; it
is not a route table.
*Changes.* §6, §11, §11.1 (addresses count as features in the manifest).

**F9 Conditional components and empty states.** A subscribe button that hides once subscribed, an
export button for some roles, an empty list.
*Proposal.* `visible=` and `hidden=` bound to a boolean in the store, and `empty=` on collections.
No expression language; loaders compute the booleans.
*Changes.* §6.

**F10 Named actions, gestures, and keys.** Double-tap to like, swipe to reply, drag a deal to a
stage, long-press for a menu, `n` for a new deal.
*Proposal.* Components and collections declare named actions with a label, an optional gesture
hint, an optional key, and an optional target (a group, for moves). Clients map hints to their
platform. Every action is also an accessibility action and appears in a menu, so nothing is
gesture-only.
*Changes.* §6, §11 (accessibility duty), §14 (`input`).

**F11 Instant feedback: validation and optimistic patches.** Every handler goes to the app process
before anything changes, so a sent message, a like, or a moved deal waits for Python and the
network.
*Proposal.* Inputs declare constraints (required, format, length, range) that the engine checks
without a handler. Handlers may declare an `optimistic` patch built from placeholders (`value`,
`item`, `data`, `increment`, `key`), which the engine applies at once and reconciles by key when
the handler returns, or rolls back if it fails.
*Changes.* §5 (loops), §6.

**F12 Insets.** A chat's reply bar must sit above the software keyboard; notches, home indicators,
foldable hinges, and desktop title bars take space.
*Proposal.* `insets` (safe area, keyboard, hinge) in the context; the keyboard opening or closing
is a context change the composer handles without moving anything else.
*Changes.* §8 (`Context`).

**F13 Strings, locales, and right-to-left.** Literal strings in intent cannot be translated, and
"Hello, {name}" needs templates and plurals. Right-to-left languages need mirrored composition.
*Proposal.* Strings are message keys with catalogues (ICU plurals); the locale comes from the
context; the composer mirrors reading order for right-to-left; worlds do not mirror, and text
surfaces follow the script's direction.
*Changes.* §6, §8. The string type belongs in the M1 schema; translation tooling can follow.

### C. Facts and content

**F14 A real text engine.** Signed-distance-field text draws glyphs from an atlas. User content
needs shaping for Arabic, Persian, and Indic scripts, bidirectional runs, colour emoji, font
fallback across scripts, line breaking, and glyph positions for carets and selection. Whether
Babylon.js's text rendering does any of this was not checked.
*Proposal.* Add to E1: shape with HarfBuzz (compiled to WebAssembly) into signed-distance-field
atlases, with colour emoji as bitmaps; test Persian, Arabic, Hindi, Chinese, and emoji in user
content, on the server and on an iPhone.
*Changes.* §10, §15 (E1).

**F15 Images and media are facts.** Decision E covers strings and values. Avatars, photos,
thumbnails, and videos are the user's content too, and on a photo app they are the product.
*Proposal.* Extend decision E: images and media from data are shown exactly, never generated, and
never restyled; L2 sees them masked and they are composited back like text. On streamed clients
their quality is the stream's (F1, Q16).
*Changes.* §2 (E), §12, §13.

**F16 Native surfaces beyond the editor.** A stream cannot carry protected video, because the
server cannot decrypt it; re-encoding a film into the interface stream costs GPU time and quality;
and picture-in-picture, casting, background audio, and captions belong to the platform's player.
CRM emails and sign-in pages from other providers raise the same problem for web content.
*Proposal.* Generalise the native editor into **native surfaces**: the editor, a media player, and
later a web view and a map. A surface is placed from the object map (on iOS, from the local scene),
drawn by the client above the stream, and reports events to the engine. Rules: a flat rectangle
with a perspective transform, never hidden behind world objects.
*Changes.* §11, §14, §3.2. A video platform cannot exist without the media surface (Q18).

**F17 Rich text and HTML.** Docs pages in Markdown, captions with mentions and hashtags, chat
formatting, CRM notes and emails.
*Proposal.* A `rich_text` kind with a closed model (paragraphs, emphasis, links, lists, code,
mentions, hashtags), drawn by the text engine, with links as named actions. Arbitrary HTML, such
as an email, goes in a web-view surface (F16) or is converted to the closed model.
*Changes.* §6, §10.

**F18 Selection, copy, find, print.** Copying a message, a code sample, or an address; Ctrl+F in
the docs; printing a report. Nothing in a stream is selectable.
*Proposal.* Text runs in the object map carry glyph positions. A long-press or drag starts a native
selection over them, and copy takes the exact string from the facts, never from pixels. Find is an
engine action bound to the platform's shortcut. Print renders a document from intent (later).
*Changes.* §11, §14.

**F19 Charts.** The dashboard and the CRM's forecast.
*Proposal.* A `chart` kind drawn by the engine from data, as a fact, with a data table as its
accessible form. After M1.

### D. Platform, cost, and limits

**F20 Idle sessions and their cost.** Sales teams keep a CRM open all day; a film plays for two
hours in the native player while the interface does nothing; phones leave apps in the background.
A streamed session holds GPU memory even when idle.
*Proposal.* Suspend idle sessions: release the GPU, keep the reel; the client keeps the last frame
and the accessibility tree; the session resumes on input within a budget that E2 measures.
Background apps disconnect. Sessions per GPU are counted as active, not open.
*Changes.* §11, §17, Q5.

**F21 Public pages and search engines.** A landing page, docs, and shared posts or videos must be
found by search engines and show link previews. Crawlers see nothing in a stream.
*Proposal.* For frames marked public, the engine serves semantic HTML built from intent and data
(the same content as the accessibility tree), with a preview image it renders, to crawlers and
link-preview bots. The alternative is to keep public pages outside Videotape (Q19).

**F22 All content passes through the engine.** Rendering on a server needs the plain content, and
on iOS the scene state carries it too. End-to-end encryption is impossible on every client, and every
message and photo passes through the engine, so retention, data residency, and privacy labels apply
to the engine.
*Proposal.* State it as a limit. The engine keeps facts in memory only, never logs them, and never
sends them to generation (Q20).

**F23 Links and downloads before M4.** Tapping a link in a chat, opening the docs' source on
GitHub, and exporting a CSV are basic behaviours, but decision G defers OS capabilities.
*Proposal.* `open_url` in M1 on every client (the system browser opens it), and downloads on the
web client in M1; files elsewhere stay in M4 (Q21).

**F24 Releases while users are mid-journey.** A release can change a tape a user is halfway
through, and old store builds keep running with older feature manifests.
*Proposal.* A reel finishes its current journey on the release it started on, so the engine serves
several releases side by side; a change that breaks a journey's steps bumps that tape's version; the
manifest gates features as in §11.1.
*Changes.* §7.1.

**F25 Custom components.** A video editor's timeline, a map, a seat picker, a whiteboard: something
outside the vocabulary.
*Proposal.* Custom components as TypeScript plugins to the scene runtime, declaring their intent
(events, values, accessibility role), compiled into the engine and into the shells, so they are
reviewed features and not downloaded code. Designed in M2 (Q23).

**F26 The developer's loop without a GPU.** A Python developer has a laptop, not a GPU server.
*Proposal.* `videotape dev` sends scene state to the browser, which renders it with Babylon.js:
the same path as the iOS client (decision K), so no server GPU is needed. `--stream` tests
streaming where a GPU is available (Q22).

**F27 SDK details.** Small things the guide settled or exposed:
- `import videotape as vt` keeps `vt.input` from shadowing Python's built-in `input`.
- Handlers are passed directly (`on_press=sign_in`) and serialise to handler names.
- Some string arguments are data paths (`hidden="item.liked"`, `alt="item.title"`) and others are
  literal text (`label="Email"`). The SDK must make the difference explicit, for example
  `vt.bind("item.title")` for paths, or a separate parameter for each.
- Placeholders (`vt.item`, `vt.data`, `vt.value`, `vt.key`) keep static actions and optimistic
  patches as data, so they need no call to Python.
- `input` gains a `money` type (with a currency) and `lines=` for multi-line text, replacing v1's
  `textarea`.

## 4. Questions to decide

Numbered after the design's Q1–Q15. The recommendation comes first.

| # | Question | Recommendation | Alternatives |
|---|----------|----------------|--------------|
| Q16 | On streamed clients, are surfaces (F3) drawn in the stream or by the client? | Design the protocol so a surface can be drawn either way (the iOS `scene` message already carries what a client needs), measure F1 and F2 in E2, then decide | (b) the client draws surfaces from scene state, and the world is streamed behind them; (c) every client renders scene state as iOS does, and streaming is kept for L2, L3, and weak devices. Both trade against decision A |
| Q17 | Should the composer place components on surfaces as well as props (F3)? | Yes | Embody everything, and accept that dense apps suffer |
| Q18 | Native media surfaces (F16): in M1? | Yes for playback, captions, full screen, and picture-in-picture; DRM and casting with the M4 capabilities | M2, which leaves the video platform out of M1 |
| Q19 | Public pages and search engines (F21)? | Crawler snapshots of public frames in M2; until then, public marketing sites stay ordinary websites | Keep public pages outside Videotape permanently |
| Q20 | End-to-end encryption is impossible (F22): accept it as a stated limit? | Yes, and keep facts in memory only | None found that keeps server rendering |
| Q21 | Links and web downloads (F23): in M1? | Yes: `open_url` on every client, downloads on the web | Wait for M4 |
| Q22 | Does `videotape dev` render scene state in the browser (F26)? | Yes, for development; production web stays streamed unless Q16 decides otherwise | Require a GPU for development |
| Q23 | Custom components (F25) as TypeScript plugins compiled into engine and shells? | Yes, designed in M2 | No extension point; grow the vocabulary only |

Findings F4–F13, F15, F17, F18, F24, and F27 have no real alternative and can go into the design as
they are, unless you see one.

## 5. What would change in the design

If the recommendations are adopted:

- **§2 Decisions.** E extends to images and media (F15).
- **§3.2 Non-goals.** Media playback and `open_url` leave the M1 non-goals (Q18, Q21).
- **§5 Loops.** Local scrolling and dragging, optimistic patches (F2, F11).
- **§6 Intent and SDKs.** Collections, hubs, calls, live topics, timers, identity, addresses,
  conditions, actions, validation, rich text, message keys (F4–F11, F13, F17); SDK notes (F27).
- **§8 Composition.** Surfaces, collection shapes, insets, right-to-left (F3, F4, F12, F13).
- **§10 Scene runtime.** Text shaping, rich text (F14, F17).
- **§11 Client.** Native surfaces, selection, idle suspension, browser history (F8, F16, F18, F20).
- **§14 Protocols.** App-to-engine publishing, scroll regions, glyph positions, surface events
  (F2, F6, F16, F18).
- **§15 Experiments.** E1 adds shaping and emoji (F14); E2 adds text legibility, scrolling, and idle
  resume (F1, F2, F20).
- **§17 Risks.** Text fidelity and scrolling on streamed clients; content through the engine.

## 6. Not covered by this review

Games built on Videotape; shops and checkout (payments are M4); maps and location apps; offline-first
apps; real-time co-editing of documents; enterprise single sign-on. Each would likely add findings.
