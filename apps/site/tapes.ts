// The demo app (spec Appendix A, with enter hooks and the settings/reset stubs).
import { app, back, bind, button, frame, handler, image, input, jump, link, list, stay, tape, text } from "@videotape/core";
import "./services";

const landing = tape("landing", {
  title: "Videotape",
  frames: [
    frame("home", {
      layout: "hero",
      scene: "Landing scene for Videotape, a framework where interfaces are generated video. " +
             "A cassette tape dissolving into light, dusk gradient, deep space behind.",
      components: [
        text("wordmark", "videotape", { slot: "nav.leading", variant: "subtitle" }),
        link("signin", "Sign in", { slot: "nav.trailing", on: { press: jump("login") } }),
        text("headline", "Interfaces, played.", { slot: "hero.title", variant: "title" }),
        text("sub", "Describe the journey. Let the picture happen.", { slot: "hero.subtitle" }),
        button("docs", "Read the docs", { slot: "hero.primary", on: { press: jump("docs") } }),
        link("github", "Source on GitHub", { slot: "hero.secondary", on: { press: jump("docs", { "docs.page": "repo" }) } }),
      ],
    }),
  ],
});

const docs = tape("docs", {
  title: "Docs",
  frames: [
    frame("read", {
      layout: "reader",
      scene: "A reading room at dusk, paper-like warmth, soft shadows, calm.",
      enter: ({ data, services }) => services.docs.page(data.docs?.page ?? "intro"),
      components: [
        link("home", "← videotape", { slot: "nav.leading", on: { press: back() } }),
        text("title", bind("docs.title"), { slot: "reader.title", variant: "title" }),
        text("body", bind("docs.body"), { slot: "reader.body" }),
        list("toc", { slot: "reader.toc", label: "Contents", items: bind("docs.toc"), on: { select: "open" } }),
      ],
      on: {
        open: handler(async ({ values, services }) => stay(await services.docs.page(values.item)), { outcomes: [stay()] }),
      },
    }),
  ],
});

const login = tape("login", {
  title: "Sign in",
  frames: [
    frame("form", {
      layout: "form",
      scene: "A quiet sign-in moment for Videotape. Dusk gradient, a faint cassette silhouette, " +
             "soft volumetric light, generous negative space, cinematic.",
      components: [
        link("home", "← videotape", { slot: "nav.leading", on: { press: back() } }),
        text("title", "Welcome back", { slot: "form.title", variant: "title" }),
        input("username", { label: "Username", slot: "form.field.1" }),
        input("password", { label: "Password", type: "secret", slot: "form.field.2" }),
        text("error", bind("login.error"), { slot: "form.error", variant: "caption" }),
        button("submit", "Sign in", { slot: "form.primary", on: { press: "submit" } }),
        link("forgot", "Forgot password?", { slot: "form.secondary", on: { press: jump("reset") } }),
        text("hint", "Demo account: ada / lovelace", { slot: "form.aside", variant: "caption" }),
      ],
      on: {
        submit: handler(
          async ({ values, services }) => {
            const user = await services.auth.login(values.username, values.password);
            return user ? jump("dashboard", { user, "login.error": "" }) : stay({ "login.error": "Wrong credentials" });
          },
          { outcomes: [jump("dashboard"), stay()] },
        ),
      },
    }),
  ],
});

const dashboard = tape("dashboard", {
  title: "Dashboard",
  frames: [
    frame("home", {
      layout: "grid",
      scene: (f) => `A control room overlooking a city at night, ${f.mood} instrument glow, ` +
                    "four softly lit panels arranged on a dark console.",
      flavour: (data) => ({ mood: data.user?.plan === "pro" ? "warm" : "cool" }),
      enter: ({ data, services }) => services.stats.load(data.user),
      components: [
        text("hello", bind("user.greeting"), { slot: "grid.title", variant: "title" }),
        link("settings", "Settings", { slot: "nav.trailing", on: { press: jump("settings") } }),
        text("views", bind("stats.views"), { slot: "grid.cell.1", variant: "number" }),
        text("watch", bind("stats.watchTime"), { slot: "grid.cell.2", variant: "number" }),
        text("subs", bind("stats.subscribers"), { slot: "grid.cell.3", variant: "number" }),
        button("report", "Open report", { slot: "grid.cell.4", on: { press: jump("report") } }),
      ],
    }),
  ],
});

const report = tape("report", {
  title: "Report",
  frames: [
    frame("view", {
      layout: "detail",
      scene: "A single illuminated chart panel on a dark desk, paper texture, one desk lamp.",
      enter: ({ services }) => services.reports.load(),
      components: [
        link("backlink", "← Dashboard", { slot: "nav.leading", on: { press: back() } }),
        text("title", bind("report.title"), { slot: "detail.title", variant: "title" }),
        image("chart", bind("report.chartUrl"), { slot: "detail.media", alt: "Views per day, last 30 days" }),
        text("summary", bind("report.summary"), { slot: "detail.body" }),
        text("exported", bind("report.exported"), { slot: "detail.meta" }),
        button("export", "Export CSV", { slot: "detail.primary", on: { press: "export" } }),
      ],
      on: {
        export: handler(async ({ services }) => stay(await services.reports.exportCsv()), { outcomes: [stay()] }),
      },
    }),
  ],
});

/** A one-frame tape with a way back, for edges the demo does not build out. */
const stub = (id: string, title: string, note: string, backLabel: string) =>
  tape(id, {
    title,
    frames: [
      frame("main", {
        layout: "hero",
        scene: "An empty workbench at dusk, tools put away, one warm lamp, calm.",
        components: [
          link("back", backLabel, { slot: "nav.leading", on: { press: back() } }),
          text("title", title, { slot: "hero.title", variant: "title" }),
          text("note", note, { slot: "hero.subtitle" }),
        ],
      }),
    ],
  });

const settings = stub("settings", "Settings", "Nothing to configure yet. This tape is a stub.", "← Dashboard");
const reset = stub("reset", "Reset password", "Ask whoever runs this demo for a new password.", "← Sign in");

export default app({ entry: "landing", tapes: [landing, docs, login, dashboard, report, settings, reset] });
