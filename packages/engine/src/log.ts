// Engine logging, carried over from prototype-0. Callers pass ids and codes, never document values,
// so a document or a secret cannot reach a log line by accident (05 §12, §14). Lines that carry
// text from the app (its own log lines, error messages) are scrubbed of the secrets in play first.

export type LogFields = Record<string, string | number | boolean | undefined>;
export type Level = "debug" | "info" | "warn" | "error";

export interface Logger {
  debug(msg: string, fields?: LogFields): void;
  info(msg: string, fields?: LogFields): void;
  warn(msg: string, fields?: LogFields): void;
  error(msg: string, fields?: LogFields): void;
}

const LEVELS: Level[] = ["debug", "info", "warn", "error"];

export function consoleLogger(min: Level = "info"): Logger {
  const at = LEVELS.indexOf(min);
  const write = (level: Level) => (msg: string, fields?: LogFields) => {
    if (LEVELS.indexOf(level) < at) return;
    const tail = fields
      ? " " + Object.entries(fields).filter(([, v]) => v !== undefined).map(([k, v]) => `${k}=${v}`).join(" ")
      : "";
    (level === "error" ? process.stderr : process.stdout).write(`[videotape] ${level.padEnd(5)} ${msg}${tail}\n`);
  };
  return { debug: write("debug"), info: write("info"), warn: write("warn"), error: write("error") };
}

export interface LogLine {
  level: Level;
  msg: string;
  fields?: LogFields;
}

/** Records every line; for tests. */
export function memoryLogger(): Logger & { lines: LogLine[] } {
  const lines: LogLine[] = [];
  const write = (level: Level) => (msg: string, fields?: LogFields) => void lines.push({ level, msg, ...(fields ? { fields } : {}) });
  return { lines, debug: write("debug"), info: write("info"), warn: write("warn"), error: write("error") };
}

export const silentLogger: Logger = { debug() {}, info() {}, warn() {}, error() {} };

export const MASK = "••••";

/** `text` with every secret in `secrets` masked, longest first. */
export function scrub(text: string, secrets: Iterable<string>): string {
  let out = text;
  for (const s of [...secrets].filter((x) => x.length > 0).sort((a, b) => b.length - a.length)) out = out.split(s).join(MASK);
  return out;
}
