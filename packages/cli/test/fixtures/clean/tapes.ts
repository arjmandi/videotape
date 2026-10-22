import { app, back, frame, jump, link, tape, text } from "@videotape/core";

export default app({
  entry: "a",
  tapes: [
    tape("a", { frames: [frame("one", { components: [text("t", "Hello"), link("next", "Next", { on: { press: jump("b") } })] })] }),
    tape("b", { frames: [frame("two", { components: [text("t", "There"), link("back", "Back", { on: { press: back() } })] })] }),
  ],
});
