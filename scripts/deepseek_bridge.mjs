#!/usr/bin/env node
/**
 * Stdio JSON-lines bridge between the Python `DeepSeekProvider` and the
 * `ai-providers-direct` Node package (which speaks chat.deepseek.com's
 * web protocol: Bearer + DeepSeekHashV1 PoW + SSE).
 *
 * Protocol (one JSON object per line, newline-delimited):
 *
 *   In  → {"op":"chat","prompt":"...","thinking":false,"session_id":null,
 *          "parent_message_id":null,"timeout_ms":180000}
 *   Out → {"event":"chunk","text":"..."}            (zero or more)
 *   Out → {"event":"reasoning","text":"..."}        (zero or more)
 *   Out → {"event":"done","text":"...","finish_reason":"stop",
 *          "session_id":"...","message_id":12345,"continuations":0,
 *          "latency_ms":4321}
 *   Out → {"event":"error","type":"DirectAuthError","message":"..."}
 *
 * The bridge auto-creates a chat_session on first turn and re-uses it for
 * subsequent turns on the same process. Session/message IDs are surfaced
 * back to the Python side so it can persist them across runs if it wants
 * to thread continuation turns.
 *
 * Token: read from env DEEPSEEK_USER_TOKEN. If missing, every chat fails
 * fast with a clear error so the user knows to run the refresh script.
 */

import readline from "node:readline";
import { deepseek } from "ai-providers-direct";

const TOKEN = process.env.DEEPSEEK_USER_TOKEN || "";

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

let sessionId = null;
let lastMessageId = null;

async function handleChat(req) {
  if (!TOKEN) {
    emit({
      event: "error",
      type: "DirectAuthError",
      message:
        "Missing DEEPSEEK_USER_TOKEN — run `npm run token:refresh:headed` " +
        "inside ai-providers-direct/ to sign in once.",
    });
    return;
  }

  try {
    if (req.session_id) {
      sessionId = req.session_id;
    } else if (!sessionId) {
      sessionId = await deepseek.createSession(TOKEN);
      emit({ event: "session", session_id: sessionId });
    }

    const result = await deepseek.chat({
      token: TOKEN,
      sessionId,
      prompt: req.prompt,
      parentMessageId: req.parent_message_id ?? lastMessageId ?? null,
      thinkingEnabled: !!req.thinking,
      searchEnabled: !!req.search,
      refFileIds: Array.isArray(req.ref_file_ids) ? req.ref_file_ids : undefined,
      timeoutMs: req.timeout_ms ?? 180000,
      onChunk: (piece) => emit({ event: "chunk", text: piece }),
      onReasoning: (piece) => emit({ event: "reasoning", text: piece }),
    });

    lastMessageId = result.finalMessageId ?? lastMessageId;

    emit({
      event: "done",
      text: result.text,
      reasoning: result.reasoning,
      finish_reason: result.finishReason,
      session_id: sessionId,
      message_id: result.finalMessageId,
      continuations: result.continuations,
      latency_ms: result.totalLatencyMs,
    });
  } catch (err) {
    emit({
      event: "error",
      type: err?.name || "Error",
      message: err?.message || String(err),
    });
  }
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

rl.on("line", async (line) => {
  const s = line.trim();
  if (!s) return;
  let req;
  try {
    req = JSON.parse(s);
  } catch (e) {
    emit({ event: "error", type: "ProtocolError", message: `bad JSON: ${e.message}` });
    return;
  }
  if (req.op === "chat") {
    await handleChat(req);
  } else if (req.op === "reset") {
    sessionId = null;
    lastMessageId = null;
    emit({ event: "reset_ok" });
  } else if (req.op === "ping") {
    emit({ event: "pong", has_token: !!TOKEN });
  } else {
    emit({ event: "error", type: "ProtocolError", message: `unknown op: ${req.op}` });
  }
});

rl.on("close", () => process.exit(0));
