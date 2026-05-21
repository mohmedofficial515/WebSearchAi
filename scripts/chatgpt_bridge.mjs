#!/usr/bin/env node
/**
 * Stdio JSON-lines bridge between the Python `ChatGPTProvider` and the
 * `ai-providers-direct` Node package (which speaks chatgpt.com's backend
 * protocol via a persistent Playwright Chrome — see ../ai-providers-direct
 * /src/providers/chatgpt/transport.ts for why a real browser is required).
 *
 * Protocol (mirrors deepseek_bridge.mjs):
 *
 *   In  → {"op":"chat","prompt":"...","model":"auto",
 *          "conversation_id":null,"parent_message_id":null,"timeout_ms":180000}
 *   Out → {"event":"chunk","text":"..."}                   (0..N)
 *   Out → {"event":"done","text":"...","finish_reason":"stop",
 *          "conversation_id":"...","message_id":"...","continuations":0,
 *          "latency_ms":4321}
 *   Out → {"event":"error","type":"ChatGPTAuthError","message":"..."}
 *
 * Key difference from DeepSeek:
 *   - No token. Auth is via a persistent Chrome profile under
 *     `<consumer_root>/.chatgpt-research/chrome-profile`. First-time setup
 *     is `npm run chatgpt:setup` inside the ai-providers-direct package.
 *   - We deliberately point AI_PROVIDERS_CONSUMER_ROOT at the ai-providers-direct
 *     install dir so the profile lives next to its DeepSeek counterpart
 *     (rather than creating a second profile inside this Python project).
 *   - The bridge tracks `conversationId + parentMessageId` between turns so
 *     successive `op:"chat"` requests thread the same chatgpt.com conversation.
 */

import readline from "node:readline";
import path     from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync }    from "node:fs";

// Pin the consumer root to the ai-providers-direct install (sibling of the
// WebSearchAi project) so Chrome profile state is shared with the package's
// own `npm run chatgpt:setup` command.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const WEBSEARCH_ROOT = path.resolve(HERE, "..");
const PKG_ROOT = path.resolve(WEBSEARCH_ROOT, "..", "ai-providers-direct");
if (existsSync(PKG_ROOT)) {
  process.env.AI_PROVIDERS_CONSUMER_ROOT = PKG_ROOT;
}

const { chatgpt } = await import("ai-providers-direct");

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

let sessionId = null;
let conversationId = null;
let parentMessageId = null;

async function handleChat(req) {
  try {
    if (!sessionId) {
      // requireSession() / createSession() throw ChatGPTNotSignedInError
      // when the Chrome profile is fresh. Surface that clearly.
      const handle = await chatgpt.createSession();
      sessionId = handle.sessionId;
      emit({
        event: "session",
        session_id: sessionId,
        user_id: handle.user?.id ?? null,
        user_email: handle.user?.email ?? null,
      });
    }

    const cid = req.conversation_id ?? conversationId;
    const pid = req.parent_message_id ?? parentMessageId;

    const result = await chatgpt.chat({
      sessionId,
      prompt: req.prompt,
      conversationId: cid,
      parentMessageId: pid,
      model: req.model ?? "auto",
      timeoutMs: req.timeout_ms ?? 180_000,
      onChunk: (piece) => emit({ event: "chunk", text: piece }),
    });

    conversationId  = result.conversationId  ?? conversationId;
    parentMessageId = result.finalMessageId ?? parentMessageId;

    emit({
      event: "done",
      text: result.text,
      finish_reason: result.finishReason,
      conversation_id: conversationId,
      message_id: parentMessageId,
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
    conversationId = null;
    parentMessageId = null;
    emit({ event: "reset_ok" });
  } else if (req.op === "ping") {
    const profileExists = existsSync(path.join(PKG_ROOT, ".chatgpt-research", "chrome-profile"));
    emit({ event: "pong", profile_exists: profileExists, profile_dir: PKG_ROOT });
  } else {
    emit({ event: "error", type: "ProtocolError", message: `unknown op: ${req.op}` });
  }
});

rl.on("close", async () => {
  try { await chatgpt.close(); } catch { /* ignore */ }
  process.exit(0);
});
