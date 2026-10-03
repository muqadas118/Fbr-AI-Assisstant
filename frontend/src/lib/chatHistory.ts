/**
 * Chat history persistence — keeps assistant conversations across
 * navigation and reloads, per workspace variant (personal/business).
 *
 * Storage: localStorage (chat survives browser restarts too). Payloads
 * are sanitized on load: only the fields the renderer actually uses
 * (verification, sources, grounded, mode) are kept — anything unknown
 * or corrupted from a previous app version is dropped defensively.
 */

import type { AnswerPayload, ChatMessage } from "@/components/assistant/AssistantChat";

const KEY_PREFIX = "fbr.chat.history.";
const MAX_MESSAGES = 60;

function keyFor(variant: string): string {
  return `${KEY_PREFIX}${variant}`;
}

function sanitizePayload(raw: unknown): AnswerPayload | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const r = raw as Record<string, unknown>;
  const verification =
    r.verification && typeof r.verification === "object"
      ? (r.verification as AnswerPayload["verification"])
      : undefined;
  const sources = Array.isArray(r.sources) ? (r.sources as AnswerPayload["sources"]) : [];
  return {
    answer: typeof r.answer === "string" ? r.answer : "",
    verification: verification ?? {
      passed: false,
      checks: {},
      failed_checks: [],
      reason: "unavailable",
    },
    sources,
    grounded: Boolean(r.grounded),
    mode: typeof r.mode === "string" ? r.mode : undefined,
  } as AnswerPayload;
}

export function loadChatHistory(variant: string): ChatMessage[] {
  try {
    const raw = window.localStorage.getItem(keyFor(variant));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const out: ChatMessage[] = [];
    for (const m of parsed) {
      if (!m || typeof m !== "object") continue;
      const mm = m as Record<string, unknown>;
      if (typeof mm.id !== "string" || typeof mm.text !== "string") continue;
      if (mm.role !== "user" && mm.role !== "assistant") continue;
      out.push({
        id: mm.id,
        role: mm.role,
        text: mm.text,
        payload: sanitizePayload(mm.payload),
        kind: mm.kind === "greeting" || mm.kind === "hint" ? mm.kind : undefined,
        errorKind:
          mm.errorKind === "api" || mm.errorKind === "network" || mm.errorKind === "unexpected"
            ? mm.errorKind
            : undefined,
        errorText: typeof mm.errorText === "string" ? mm.errorText : undefined,
        fileName: typeof mm.fileName === "string" ? mm.fileName : undefined,
      });
    }
    // Newest conversation wins; cap length so localStorage stays small.
    return out.slice(-MAX_MESSAGES);
  } catch {
    return [];
  }
}

export function saveChatHistory(variant: string, messages: ChatMessage[]): void {
  try {
    // Only persisted fields; transient flags (streaming) are dropped.
    const slim = messages.slice(-MAX_MESSAGES).map((m) => ({
      id: m.id,
      role: m.role,
      text: m.text,
      payload: m.payload,
      kind: m.kind,
      errorKind: m.errorKind,
      errorText: m.errorText,
      fileName: m.fileName,
    }));
    window.localStorage.setItem(keyFor(variant), JSON.stringify(slim));
  } catch {
    // Quota exceeded / privacy mode — history is best-effort.
  }
}

export function clearChatHistory(variant: string): void {
  try {
    window.localStorage.removeItem(keyFor(variant));
  } catch {
    /* ignore */
  }
}
