// JSON Schema export, so other languages can read tapes and speak VTP (spec §5.4, §12).

import { z } from "zod";
import { ClientMessageSchema, ServerMessageSchema } from "./protocol";
import { AppSchema } from "./schema";

export function jsonSchemas(): Record<string, unknown> {
  return {
    app: z.toJSONSchema(AppSchema, { unrepresentable: "any" }),
    "vtp-client": z.toJSONSchema(ClientMessageSchema, { unrepresentable: "any" }),
    "vtp-server": z.toJSONSchema(ServerMessageSchema, { unrepresentable: "any" }),
  };
}
