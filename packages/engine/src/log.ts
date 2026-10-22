// Engine logging. Callers pass ids and codes, never component values, so a
// secret cannot reach a log line by accident (spec §10).

export type LogFields = Record<string, string | number | boolean | undefined>;

export interface Logger {
  debug(msg: string, fields?: LogFields): void;
  info(msg: string, fields?: LogFields): void;
  warn(msg: string, fields?: LogFields): void;
  error(msg: string, fields?: LogFields): void;
}

const LEVELS = ["debug", "info", "warn", "error"] as const;
type Level = (typeof LEVELS)[number];

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

/** Records every line; for tests. */
export function memoryLogger(): Logger & { lines: Array<{ level: Level; msg: string; fields?: LogFields }> } {
  const lines: Array<{ level: Level; msg: string; fields?: LogFields }> = [];
  const write = (level: Level) => (msg: string, fields?: LogFields) => void lines.push({ level, msg, ...(fields ? { fields } : {}) });
  return { lines, debug: write("debug"), info: write("info"), warn: write("warn"), error: write("error") };
}
