import { app, button, frame, jump, link, tape, text } from "@videotape/core";

export default app({
  entry: "home",
  tapes: [
    tape("home", {
      frames: [
        frame("main", {
          layout: "hero",
          components: [
            text("title", "Broken on purpose", { slot: "hero.title" }),
            button("go", "Go"),
            link("away", "Away", { slot: "hero.secondary", on: { press: jump("nowhere") } }),
          ],
        }),
      ],
    }),
  ],
});
