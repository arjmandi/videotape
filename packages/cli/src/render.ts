export async function runRender(_dir: string, _opts: { renderers?: string; viewports?: string }): Promise<number> {
  process.stderr.write("videotape: render arrives with generated stills (M2)\n");
  return 1;
}
