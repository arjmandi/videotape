// Style packs (spec §7.4). Palette and fonts drive the content layer and the
// wireframe; the prompt fields, references, and LoRA drive generators.

export interface StylePack {
  id: string;
  seed: number;
  palette: { bg: string; fg: string; accent: string; muted: string };
  fonts: { display: string; body: string };
  prompt: { prefix: string; suffix: string; negative?: string };
  references: string[];
  lora: string | null;
}

export const dusk: StylePack = {
  id: "dusk",
  seed: 4210,
  palette: { bg: "#14121a", fg: "#f3ede4", accent: "#ff6a3d", muted: "#8a8494" },
  fonts: { display: "Instrument Serif", body: "Inter" },
  prompt: {
    prefix: "Cinematic backdrop, ",
    suffix: ", film grain, 35mm, no text, no letters",
    negative: "text, letters, words, typography, watermark, logo, user interface, buttons",
  },
  references: [],
  lora: null,
};

export const BUILTIN_STYLES: readonly StylePack[] = [dusk];

export function styleById(id: string, extra: readonly StylePack[] = []): StylePack | undefined {
  return extra.find((s) => s.id === id) ?? BUILTIN_STYLES.find((s) => s.id === id);
}
