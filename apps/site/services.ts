// Fake services for the demo (spec N5: fake auth, no persistence).
import type { DataPatch } from "@videotape/core";

interface User {
  id: string;
  name: string;
  plan: "pro" | "free";
  greeting: string;
}

const USERS: Record<string, { password: string; name: string; plan: User["plan"] }> = {
  ada: { password: "lovelace", name: "Ada", plan: "pro" },
  grace: { password: "hopper", name: "Grace", plan: "free" },
};

const PAGES: Record<string, { title: string; body: string }> = {
  intro: {
    title: "What Videotape is",
    body:
      "You write tapes: ordered sequences of frames, one frame per still state of the app. " +
      "A frame says what it is about, which components it shows, and where each interaction leads.\n\n" +
      "An engine renders each frame as a picture and each transition as a short piece of video. " +
      "A thin player fills the screen with that picture and lays real inputs and text on top of it.\n\n" +
      "Generation owns form. Code owns facts. Layout owns space.",
  },
  tapes: {
    title: "Tapes and frames",
    body:
      "A tape is one user journey. Each frame declares a layout archetype, a scene, its components, " +
      "and handlers. Components name static actions (goto, jump, back) or a frame handler, and " +
      "handlers declare their outcomes, so every edge of the app is known before it runs.",
  },
  layout: {
    title: "Layout owns space",
    body:
      "The layout engine places every component in a named slot of an archetype, per viewport " +
      "class, before any pixel is generated. The same wireframe conditions the generator and " +
      "positions the facts, so a field never moves between renders.",
  },
  repo: {
    title: "Source",
    body:
      "Videotape is Apache-2.0 licensed. The design lives in docs/: the review and risk register, " +
      "the v1 specification, the backend landscape, and the test plan. Packages publish under the " +
      "@videotape scope.",
  },
};

const TOC = [
  { id: "intro", label: "What Videotape is" },
  { id: "tapes", label: "Tapes and frames" },
  { id: "layout", label: "Layout owns space" },
  { id: "repo", label: "Source" },
];

export const services = {
  auth: {
    async login(username: unknown, password: unknown): Promise<User | null> {
      if (typeof username !== "string" || typeof password !== "string") return null;
      const id = username.trim().toLowerCase();
      const u = USERS[id];
      if (!u || u.password !== password) return null;
      return { id, name: u.name, plan: u.plan, greeting: `Welcome back, ${u.name}` };
    },
  },
  docs: {
    async page(id: unknown): Promise<DataPatch> {
      const key = typeof id === "string" && id in PAGES ? id : "intro";
      const page = PAGES[key]!;
      return { "docs.page": key, "docs.title": page.title, "docs.body": page.body, "docs.toc": TOC };
    },
  },
  stats: {
    async load(user: User | undefined): Promise<DataPatch> {
      const pro = user?.plan === "pro";
      return {
        "stats.views": pro ? "12,480 views" : "3,210 views",
        "stats.watchTime": pro ? "731 h watched" : "96 h watched",
        "stats.subscribers": pro ? "1,204 subscribers" : "188 subscribers",
      };
    },
  },
  reports: {
    async load(): Promise<DataPatch> {
      return {
        "report.title": "Views, last 30 days",
        "report.chartUrl": "/app/chart.svg",
        "report.summary":
          "Views rose 18 % over the period, with a peak on day 23 after the docs went live. " +
          "Watch time followed views closely; subscribers grew steadily without a spike.",
        "report.exported": "",
      };
    },
    async exportCsv(): Promise<DataPatch> {
      return { "report.exported": "Exported 30 rows as views-30d.csv" };
    },
  },
};

export type DemoServices = typeof services;

declare module "@videotape/core" {
  interface Services {
    auth: DemoServices["auth"];
    docs: DemoServices["docs"];
    stats: DemoServices["stats"];
    reports: DemoServices["reports"];
  }
}
