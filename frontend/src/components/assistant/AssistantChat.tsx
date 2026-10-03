import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import {
  ApiError,
  NetworkError,
  type AnswerResponse,
  type AssistantAskResponse,
  type SourceItem,
  type VerificationResult,
} from "@/lib/api";
import { loadChatHistory, saveChatHistory, clearChatHistory } from "@/lib/chatHistory";
import { renderBlocks } from "@/lib/richText";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { VerificationPanel } from "@/components/ui/VerificationPanel";
import { SourceList } from "@/components/ui/SourceCitation";
import { Button } from "@/components/ui/Button";

/**
 * Shared chat experience for the personal + business assistant pages.
 * Owns the whole conversation state so the pages stay thin wrappers:
 *  - ChatGPT-style composer: attach (text files), auto-grow textarea,
 *    voice input (Web Speech API), round send button
 *  - typing/reveal effect on assistant answers (off under reduced motion)
 *  - compact source chips + expandable full citation list (reuses SourceList)
 *  - copy button with copied-state feedback
 *  - honest error states (unauthorized / api / network / unexpected)
 *  - friendly small-talk answers handled locally (hi/hello/salam/thanks)
 *  - friendly empty state with optional suggestion chips
 */

/**
 * Shape both /answer and /assistant/ask responses provide for the
 * verification panel + source chips inside a chat bubble.
 */
export interface AnswerPayload {
  answer: string;
  sources: SourceItem[];
  verification: VerificationResult;
  grounded: boolean;
  primary_domain?: string;
  domains?: string[];
  multi_domain?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  payload?: AnswerPayload;
  /** Local replies (greetings, hints) — rendered without the error banner. */
  kind?: "greeting" | "hint";
  errorKind?: "api" | "network" | "unexpected";
  errorText?: string;
  /** File name attached to a user message. */
  fileName?: string;
  /** Answer is still receiving live SSE deltas. */
  streaming?: boolean;
}

type Variant = "personal" | "business";

const IDS: Record<
  Variant,
  { shell: string; bubble: string; banner: string }
> = {
  personal: { shell: "assistant", bubble: "chat", banner: "message" },
  business: { shell: "biz-assistant", bubble: "biz-chat", banner: "biz-message" },
};

/* ------------------------------------------------------------------ */
/* Small talk — answered locally, never sent to the RAG pipeline       */
/* ------------------------------------------------------------------ */

const GREETING_RE =
  /^(hi|hii+|hiii|hello|helloo+|helo|hey|heyy+|yo|hy|salam|salaam|as-?salam(u|o)?[- ]?alaikum|assalam[- ]?o[- ]?alaikum|aoa|adios|good[- ]?(morning|afternoon|evening|day)|kya haal|kaise ho|kaisay ho|how are you|howdy|greetings)\b[\s!,.?]*$/i;

const THANKS_RE =
  /^(thanks|thank you|thankyou|thx|ty|shukriya|jazakallah|meherbani|great|nice|awesome|perfect|well done|good job|ok|okay|wow)[\s!,.?]*$/i;

const HOW_ARE_YOU_RE =
  /^(how are you|kaise ho|kaisay ho|kya haal hai|how is it going|how's it going|whats up|what's up|sup)\b[\s!,.?]*$/i;

const BYE_RE =
  /^(bye|goodbye|khuda hafiz|allah hafiz|see you|see ya|alvida)[\s!,.?]*$/i;

/** Greeting-classified only when there is no real question attached. */
export function classifySmallTalk(raw: string): "greeting" | "thanks" | "howareyou" | "bye" | null {
  const text = raw.trim().replace(/\s+/g, " ");
  if (!text || text.includes("?")) return null;
  if (GREETING_RE.test(text)) return "greeting";
  if (HOW_ARE_YOU_RE.test(text)) return "howareyou";
  if (THANKS_RE.test(text)) return "thanks";
  if (BYE_RE.test(text)) return "bye";
  return null;
}

function smallTalkReply(kind: NonNullable<ReturnType<typeof classifySmallTalk>>): string {
  switch (kind) {
    case "greeting":
      return (
        "Hello! 👋 I'm your FBR Tax & Compliance Assistant.\n\n" +
        "I can answer questions on Income Tax, Sales Tax, Federal Excise and Property " +
        "Valuation — every answer is grounded in official FBR law with citations.\n\n" +
        "Try asking:\n" +
        "• \"What is the penalty for late filing of an annual return?\"\n" +
        "• \"Who must register for sales tax?\"\n" +
        "• \"What is Section 177 of the Income Tax Ordinance?\""
      );
    case "howareyou":
      return "I'm running great, thanks for asking! 🙌 What FBR question can I help you with today?";
    case "thanks":
      return "You're welcome! 😊 If anything else comes up — filings, notices, deadlines — just ask.";
    case "bye":
      return "Goodbye! 👋 Come back any time — your compliance questions are always welcome.";
  }
}

/* ------------------------------------------------------------------ */
/* Reduced-motion detection                                            */
/* ------------------------------------------------------------------ */

/**
 * Reduced-motion / non-animation environments never animate:
 *  - matchMedia says the user prefers reduced motion, or is unavailable
 *  - the runtime cannot run CSS animations at all (SSR, jsdom — no
 *    Element.getAnimations), so tests and server render full text instantly.
 */
function useNoMotion(): boolean {
  return useMemo(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return true;
    }
    if (typeof Element === "undefined" || typeof Element.prototype.getAnimations !== "function") {
      return true;
    }
    try {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch {
      return true;
    }
  }, []);
}

/* ------------------------------------------------------------------ */
/* ChatGPT-style thinking indicator (no box, bare dots)                */
/* ------------------------------------------------------------------ */

function ThinkingIndicator({ testId }: { testId: string }) {
  const words = ["Thinking", "Analysing", "Searching", "Reading", "Composing"];
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setIdx((v) => (v + 1) % words.length), 1600);
    return () => window.clearInterval(id);
  }, []);
  return (
    <div className="chat__thinking" role="status" aria-live="polite" data-testid={testId}>
      <span className="chat__thinking-word">{words[idx]}…</span>
      <span className="chat__thinking-dots" aria-hidden>
        <span className="chat__thinking-dot" />
        <span className="chat__thinking-dot" />
        <span className="chat__thinking-dot" />
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Typewriter reveal                                                   */
/* ------------------------------------------------------------------ */

function Typewriter({
  text,
  reduced,
  streaming,
  testId,
}: {
  text: string;
  reduced: boolean;
  /** True while live SSE deltas are arriving — show growing text + caret,
   * no typewriter replay on every chunk. */
  streaming?: boolean;
  testId?: string;
}) {
  const [count, setCount] = useState(() => (reduced ? text.length : 0));

  useEffect(() => {
    if (streaming) {
      // Live deltas: always show everything received so far. The caret is
      // rendered separately below while `streaming` is true.
      setCount(text.length);
      return;
    }
    if (reduced) {
      setCount(text.length);
      return;
    }
    setCount(0);
    // Reveal over a bounded window (~1.4s) regardless of answer length.
    const tickMs = 24;
    const steps = Math.max(1, Math.ceil(1400 / tickMs));
    const per = Math.max(1, Math.ceil(text.length / steps));
    let shown = 0;
    const id = window.setInterval(() => {
      shown = Math.min(text.length, shown + per);
      setCount(shown);
      if (shown >= text.length) window.clearInterval(id);
    }, tickMs);
    return () => window.clearInterval(id);
  }, [text, reduced, streaming]);

  const done = count >= text.length;
  const showCaret = (streaming ?? false) || !done;
  return (
    <div className="chat__answer" data-testid={testId} aria-label={text}>
      {renderBlocks(text.slice(0, count))}
      {showCaret ? <span className="chat__caret" aria-hidden /> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Copy button                                                         */
/* ------------------------------------------------------------------ */

function CopyButton({ text, testId }: { text: string; testId?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  const onCopy = useCallback(async () => {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (!ok) throw new Error("copy rejected");
      }
      setState("copied");
    } catch {
      setState("failed");
    }
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 2000);
  }, [text]);

  return (
    <button
      type="button"
      className={clsx("chat__copy", state === "copied" && "chat__copy--done")}
      onClick={() => void onCopy()}
      data-testid={testId}
      aria-live="polite"
      title="Copy answer"
    >
      {state === "copied" ? "Copied ✓" : state === "failed" ? "Copy failed" : "Copy"}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Source chips                                                        */
/* ------------------------------------------------------------------ */

/** Compact chips under the answer; expands into the existing SourceList. */
function SourceChips({
  sources,
  chipsTestId,
  toggleTestId,
  listTestId,
}: {
  sources: SourceItem[];
  chipsTestId?: string;
  toggleTestId?: string;
  listTestId?: string;
}) {
  const [showAll, setShowAll] = useState(false);
  const max = 3;
  const visible = sources.slice(0, max);
  const extra = sources.length - visible.length;

  const shortName = (raw: string) =>
    raw.replace(/\.[a-z0-9]+$/i, "").replace(/_/g, " ").trim();

  return (
    <div className="chat__chips-block">
      <div className="chat__chips" data-testid={chipsTestId}>
        {visible.map((s, i) => (
          <span
            className="chat__chip"
            key={s.chunk_id || `${s.source}-${i}`}
            title={s.source}
          >
            <span className="chat__chip-doc">{shortName(s.source)}</span>
            {s.page != null ? (
              <span className="chat__chip-page">p. {s.page}</span>
            ) : null}
          </span>
        ))}
        {extra > 0 ? (
          <span className="chat__chip chat__chip--more">+{extra} more</span>
        ) : null}
        <button
          type="button"
          className="chat__chips-toggle"
          onClick={() => setShowAll((v) => !v)}
          aria-expanded={showAll}
          data-testid={toggleTestId}
        >
          {showAll ? "Hide sources" : `View sources (${sources.length})`}
        </button>
      </div>
      {showAll ? <SourceList sources={sources} testId={listTestId} /> : null}
    </div>
  );
}

function DomainBlock({
  primary,
  domains,
  multi,
  testId,
}: {
  primary: string;
  domains: string[];
  multi: boolean;
  testId?: string;
}) {
  if (!primary && (!domains || domains.length === 0)) return null;
  return (
    <div className="chat__domains" data-testid={testId}>
      <span className="chat__domain-label">Routed to</span>
      <span className="chat__domain-primary">{primary || "general"}</span>
      {multi && domains && domains.length > 1 ? (
        <span className="chat__domain-multi">+ {domains.length - 1} more</span>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Message bubble                                                      */
/* ------------------------------------------------------------------ */

function MessageBubble({
  message,
  reduced,
  ids,
}: {
  message: ChatMessage;
  reduced: boolean;
  ids: { shell: string; bubble: string; banner: string };
}) {
  const b = ids.bubble;

  if (message.role === "user") {
    return (
      <div className="chat__msg chat__msg--user" data-testid={`${b}-user`}>
        <div className="chat__bubble">
          {message.fileName ? (
            <span className="chat__bubble-file" title={message.fileName}>
              📎 {message.fileName}
            </span>
          ) : null}
          {message.text}
        </div>
      </div>
    );
  }

  if (message.errorKind) {
    const title =
      message.errorKind === "network"
        ? "Can't reach the server"
        : message.errorKind === "api"
          ? "Could not retrieve answer"
          : "Something went wrong";
    return (
      <div className="chat__msg chat__msg--assistant" data-testid={`${b}-error`}>
        <div className="chat__bubble">
          <StatusBanner
            kind="err"
            title={title}
            description={message.errorText || message.text}
            testId={`${ids.banner}-error`}
          />
        </div>
      </div>
    );
  }

  const payload = message.payload;
  const sources = payload?.sources ?? [];
  const isLocal = message.kind === "greeting" || message.kind === "hint";
  const showPipeline = !isLocal && payload != null && "primary_domain" in payload;

  return (
    <div
      className={clsx("chat__msg", "chat__msg--assistant", isLocal && "chat__msg--local")}
      data-testid={`${b}-assistant`}
    >
      <div className="chat__bubble chat__bubble--assistant">
        {message.text ? (
          <CopyButton text={message.text} testId={`${b}-copy`} />
        ) : null}
        <Typewriter
          text={message.text}
          reduced={reduced}
          streaming={message.streaming}
          testId={`${b}-answer`}
        />

        {payload ? (
          <>
            <VerificationPanel
              verification={payload.verification}
              grounded={payload.grounded}
              className="chat__verification"
              testId={`${b}-verification`}
            />
            {showPipeline ? (
              <DomainBlock
                primary={payload.primary_domain ?? ""}
                domains={payload.domains ?? []}
                multi={Boolean(payload.multi_domain)}
                testId={`${b}-domains`}
              />
            ) : null}
            {sources.length > 0 ? (
              <SourceChips
                sources={sources}
                chipsTestId={`${b}-source-chips`}
                toggleTestId={`${b}-sources-toggle`}
                listTestId={`${b}-sources`}
              />
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* File attachment helpers                                             */
/* ------------------------------------------------------------------ */

const TEXT_FILE_RE = /\.(txt|md|markdown|csv|tsv|json|xml|yml|yaml|log)$/i;
const MAX_FILE_EXCERPT = 4000;
const MAX_FILE_BYTES = 512 * 1024;

function isTextFile(file: File): boolean {
  return TEXT_FILE_RE.test(file.name) || file.type.startsWith("text/");
}

async function readFileExcerpt(file: File): Promise<string> {
  const sliced = file.slice(0, MAX_FILE_BYTES);
  if (typeof sliced.text === "function") {
    return (await sliced.text()).slice(0, MAX_FILE_EXCERPT);
  }
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? "").slice(0, MAX_FILE_EXCERPT));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(sliced);
  });
}

/** Any non-text file (PDF, image, spreadsheet...) goes to the upload pipeline. */
function isUploadFile(file: File): boolean {
  return !isTextFile(file);
}

/** Which uploaded document families the backend accepts. */
const UPLOAD_ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.gif,.txt,.md,.csv,.rtf,.json";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/* ------------------------------------------------------------------ */
/* Speech recognition (Web Speech API)                                 */
/* ------------------------------------------------------------------ */

interface SpeechRecognitionAlternativeLike {
  transcript: string;
}
interface SpeechRecognitionResultLike {
  0: SpeechRecognitionAlternativeLike;
  isFinal: boolean;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: { length: number; [i: number]: SpeechRecognitionResultLike };
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  start(): void;
  stop(): void;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/* ------------------------------------------------------------------ */
/* Main chat component                                                 */
/* ------------------------------------------------------------------ */

export interface AssistantChatProps {
  variant: Variant;
  /**
   * Ask the backend. `file` carries PDFs / images / any non-text
   * attachment so the backend upload pipeline (text extraction + OCR)
   * can read it; text attachments are already inlined in `question`.
   */
  ask: (question: string, file?: File | null) => Promise<AssistantAskResponse | AnswerResponse>;
  /** Optional streaming transport (SSE) — enables live token-by-token answers. */
  askStream?: (
    question: string,
    handlers: {
      onMeta?: (meta: Partial<AssistantAskResponse & AnswerResponse>) => void;
      onDelta?: (chunk: string) => void;
    },
  ) => Promise<AssistantAskResponse | AnswerResponse>;
  /** Kept for API compatibility; auth is handled by the backend token getter. */
  loggedIn?: boolean;
  inputLabel: string;
  inputPlaceholder: string;
  emptyTitle: string;
  emptyDescription: string;
  suggestions?: string[];
}

export function AssistantChat({
  variant,
  ask,
  askStream,
  inputLabel,
  inputPlaceholder,
  emptyTitle,
  emptyDescription,
  suggestions,
}: AssistantChatProps) {
  const ids = IDS[variant];
  const s = ids.shell;
  const reduced = useNoMotion();

  // Conversation persists across navigation and reloads (per workspace).
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadChatHistory(variant));
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [attached, setAttached] = useState<{ name: string; size: number; excerpt: string } | null>(
    null,
  );
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [listening, setListening] = useState(false);
  const voiceBaseRef = useRef("");
  const [composerNotice, setComposerNotice] = useState<string | null>(null);
  const idCounter = useRef(0);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const noticeTimer = useRef<number | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading]);

  useEffect(
    () => () => {
      if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
      recognitionRef.current?.stop();
    },
    [],
  );

  const showNotice = useCallback((text: string) => {
    setComposerNotice(text);
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setComposerNotice(null), 5000);
  }, []);

  const autoGrow = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    const h = el.scrollHeight;
    el.style.height = h > 0 ? `${Math.min(h, 168)}px` : "";
  }, []);

  const pushLocal = useCallback((text: string, kind: ChatMessage["kind"]) => {
    idCounter.current += 1;
    setMessages((m) => [
      ...m,
      { id: `l-${idCounter.current}`, role: "assistant", text, kind },
    ]);
  }, []);

  const submit = useCallback(
    async (q?: string) => {
      const raw = (q ?? input).trim();
      if ((!raw && !attached) || loading) return;

      const question =
        raw ||
        `Please review the attached file "${(attached?.name ?? attachedFile?.name)}" and summarize its key tax-related points.`;
      const fullQuery = attached
        ? `${question}\n\n[Attached file: ${attached.name}]\n${attached.excerpt}`
        : question;

      // Small talk is answered locally — no verification panel, no error.
      if (!attached) {
        const smallTalk = classifySmallTalk(question);
        if (smallTalk) {
          idCounter.current += 1;
          setMessages((m) => [
            ...m,
            { id: `u-${idCounter.current}`, role: "user", text: question },
          ]);
          setInput("");
          pushLocal(smallTalkReply(smallTalk), "greeting");
          return;
        }
      }

      idCounter.current += 1;
      const userMsg: ChatMessage = {
        id: `u-${idCounter.current}`,
        role: "user",
        text: question,
        fileName: attached?.name,
      };
      setMessages((m) => [...m, userMsg]);
      setInput("");
      setAttached(null);
      const fileForAsk = attachedFile;
      setAttachedFile(null);
      setLoading(true);

      try {
        let resp: AssistantAskResponse | AnswerResponse;
        if (askStream && !fileForAsk) {
          // Streaming path: placeholder bubble first, then live deltas.
          idCounter.current += 1;
          const streamId = `a-${idCounter.current}`;
          setMessages((m) => [
            ...m,
            { id: streamId, role: "assistant", text: "", payload: undefined },
          ]);
          const updateStream = (patch: Partial<ChatMessage>) =>
            setMessages((m) =>
              m.map((msg) => (msg.id === streamId ? { ...msg, ...patch } : msg)),
            );
          try {
            updateStream({ streaming: true });
            resp = await askStream(fullQuery, {
              onDelta: (chunk) =>
                setMessages((m) =>
                  m.map((msg) =>
                    msg.id === streamId ? { ...msg, text: msg.text + chunk } : msg,
                  ),
                ),
            });
            updateStream({ text: resp.answer, payload: resp, streaming: false });
          } catch (streamErr) {
            // Stream died mid-flight — drop the empty placeholder and rethrow
            // to the shared error handler (unless partial text already arrived).
            setMessages((m) => m.filter((msg) => !(msg.id === streamId && !msg.text)));
            throw streamErr;
          }
        } else {
          resp = await ask(fullQuery, fileForAsk);
          idCounter.current += 1;
          setMessages((m) => [
            ...m,
            {
              id: `a-${idCounter.current}`,
              role: "assistant",
              text: resp.answer,
              payload: resp,
            },
          ]);
        }
      } catch (err) {
        const detail =
          err instanceof ApiError
            ? err.detail || err.message
            : err instanceof Error
              ? err.message
              : "";

        // "Question is too short" from the API → friendly nudge, not an error.
        if (/too short/i.test(detail)) {
          pushLocal(
            "Please type a slightly longer question — for example \"What is the penalty for late filing?\" — and I'll find the answer in FBR law. 😊",
            "hint",
          );
          return;
        }

        let errorKind: ChatMessage["errorKind"] = "unexpected";
        let errorText = "An unexpected error occurred. Please try again.";
        if (err instanceof ApiError) {
          errorKind = "api";
          errorText = detail;
        } else if (err instanceof NetworkError) {
          errorKind = "network";
          errorText =
            "The assistant service could not be reached. Check your connection and try again.";
        }
        idCounter.current += 1;
        setMessages((m) => [
          ...m,
          {
            id: `e-${idCounter.current}`,
            role: "assistant",
            text: errorText,
            errorKind,
            errorText,
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [ask, askStream, attached, attachedFile, input, loading, pushLocal],
  );

  const clear = useCallback(() => {
    setMessages([]);
    setInput("");
    setAttached(null);
    setAttachedFile(null);
    clearChatHistory(variant);
  }, [variant]);

  // Persist on every settled change (mid-stream saves are wasteful but
  // harmless; the final save after `streaming: false` is what matters).
  useEffect(() => {
    if (messages.length === 0) return; // clear() already wiped storage
    saveChatHistory(variant, messages);
  }, [messages, variant]);

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
  };

  /* ------- attachments ------- */

  const onPickFile = useCallback(
    async (file: File | undefined) => {
      if (!file) return;
      // PDFs / images / any non-text file go to the backend upload
      // pipeline (PDF text extraction + OCR) via the ask callback.
      if (isUploadFile(file)) {
        if (file.size > 10 * 1024 * 1024) {
          showNotice("That file is too large — please attach files under 10 MB.");
          return;
        }
        setAttachedFile(file);
        setAttached({ name: file.name, size: file.size, excerpt: "" });
        return;
      }
      if (file.size > 2 * 1024 * 1024) {
        showNotice("That file is too large — please attach files under 2 MB.");
        return;
      }
      try {
        const excerpt = await readFileExcerpt(file);
        setAttached({ name: file.name, size: file.size, excerpt });
      } catch {
        showNotice(`Could not read "${file.name}". Please try again.`);
      }
    },
    [showNotice],
  );

  /* ------- voice input ------- */

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setListening(false);
  }, []);

  const toggleMic = useCallback(() => {
    if (listening) {
      stopListening();
      return;
    }
    // Interim results arrive as full re-transcriptions of the utterance, so we
    // remember what the input held before the session and REPLACE from there
    // on every event — appending would duplicate the growing text.
    const Ctor = getSpeechRecognition();
    if (!Ctor) {
      showNotice(
        "Voice input isn't supported in this browser — try Chrome or Edge, or just type your question.",
      );
      return;
    }
    const rec = new Ctor();
    rec.lang = "en-US";
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      let text = "";
      for (let i = e.resultIndex; i < e.results.length; i += 1) {
        text += e.results[i][0].transcript;
      }
      const base = voiceBaseRef.current.trim();
      if (text.trim()) setInput(base ? `${base} ${text.trim()}` : text.trim());
    };
    rec.onend = () => {
      recognitionRef.current = null;
      setListening(false);
    };
    rec.onerror = (e) => {
      recognitionRef.current = null;
      setListening(false);
      // Give a specific, actionable message per failure mode instead of a generic one.
      switch (e.error) {
        case "aborted":
          // User stopped it (or a newer session replaced it) — onend handles the UI.
          break;
        case "no-speech":
          showNotice("No speech detected — tap the mic again and speak a little closer to it.");
          break;
        case "audio-capture":
          showNotice("No microphone was found. Connect a mic (or check it isn't muted) and try again.");
          break;
        case "not-allowed":
        case "service-not-allowed":
          showNotice("Microphone access was blocked. Allow the mic in your browser's address-bar permissions, then try again.");
          break;
        case "network":
          showNotice("Voice service is unreachable right now — check your internet connection, or type your question.");
          break;
        case "language-not-supported":
          showNotice("Voice language isn't supported in this browser — try Chrome, or type your question.");
          break;
        default:
          showNotice("Voice input hit a problem — please try again or type your question.");
      }
    };
    voiceBaseRef.current = input;
    recognitionRef.current = rec;
    setListening(true);
    try {
      rec.start();
    } catch {
      recognitionRef.current = null;
      setListening(false);
      showNotice("Voice input couldn't start — please try again.");
    }
  }, [listening, input, showNotice, stopListening]);

  const sendDisabled = loading || (!input.trim() && !attached && !attachedFile);

  return (
    <div className="chat" data-testid={`${s}-chat`}>
      {messages.length > 0 ? (
        <div className="chat__head">
          <span className="chat__head-label">
            Conversation · {messages.length} {messages.length === 1 ? "message" : "messages"}
          </span>
          <Button variant="ghost" size="sm" onClick={clear} data-testid={`${s}-clear`}>
            Clear conversation
          </Button>
        </div>
      ) : null}

      <div className="chat__messages" data-testid={`${s}-messages`} ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="chat__empty" data-testid={`${s}-empty`}>
            <div className="chat__empty-icon" aria-hidden>
              <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden>
                <path d="M12 2.6l2.6 6 6.5.5-4.9 4.2 1.5 6.3L12 16.2 6.3 19.6l1.5-6.3L2.9 9.1l6.5-.5 2.6-6z" />
              </svg>
            </div>
            <h3 className="chat__empty-title">{emptyTitle}</h3>
            <p className="chat__empty-text">{emptyDescription}</p>
            {suggestions && suggestions.length > 0 ? (
              <div className="chat__suggestions" data-testid={`${s}-suggestions`}>
                {suggestions.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className="chat__suggestion"
                    onClick={() => void submit(q)}
                    disabled={loading}
                    data-testid={`${s}-suggestion`}
                  >
                    {q}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          messages.map((m) => <MessageBubble key={m.id} message={m} reduced={reduced} ids={ids} />)
        )}
        {loading ? <ThinkingIndicator testId={`${s}-thinking`} /> : null}
      </div>

      <div className="chat__composer-area">
        {attached ? (
          <div className="chat__file-chip" data-testid={`${s}-file-chip`}>
            <span className="chat__file-icon" aria-hidden>📄</span>
            <span className="chat__file-name" title={attached.name}>{attached.name}</span>
            <span className="chat__file-size">{formatBytes(attached.size)}</span>
            <button
              type="button"
              className="chat__file-remove"
              onClick={() => setAttached(null)}
              aria-label="Remove attachment"
              data-testid={`${s}-file-remove`}
            >
              ×
            </button>
          </div>
        ) : null}
        {composerNotice ? (
          <p className="chat__mic-notice" role="status" data-testid={`${s}-notice`}>
            {composerNotice}
          </p>
        ) : null}

        <form
          className="chat__composer"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          data-testid={`${s}-form`}
        >
          <input
            ref={fileInputRef}
            type="file"
            hidden
            accept={UPLOAD_ACCEPT + ",.txt,.md,.markdown,.csv,.tsv,.json,.xml,.yml,.yaml,.log"}
            onChange={(e) => {
              void onPickFile(e.target.files?.[0]);
              e.target.value = "";
            }}
            data-testid={`${s}-file-input`}
            aria-hidden="true"
            tabIndex={-1}
          />
          <button
            type="button"
            className="chat__composer-btn"
            onClick={() => fileInputRef.current?.click()}
            title="Attach a file (text, PDF, or image) — the AI reads it for you"
            aria-label="Attach a file"
            disabled={loading}
            data-testid={`${s}-attach`}
          >
            <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>

          <label htmlFor={`${s}-input`} className="chat__label">
            {inputLabel}
          </label>
          <textarea
            id={`${s}-input`}
            ref={textareaRef}
            className="chat__composer-input"
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              autoGrow();
            }}
            onKeyDown={onKey}
            placeholder={inputPlaceholder}
            rows={1}
            disabled={loading}
            data-testid={`${s}-input`}
          />

          <button
            type="button"
            className={clsx("chat__composer-btn", listening && "chat__composer-btn--listening")}
            onClick={toggleMic}
            title={listening ? "Stop listening" : "Ask by voice"}
            aria-label={listening ? "Stop listening" : "Ask by voice"}
            aria-pressed={listening}
            disabled={loading}
            data-testid={`${s}-mic`}
          >
            {listening ? (
              <span className="chat__mic-stop" aria-hidden />
            ) : (
              <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3" />
              </svg>
            )}
          </button>

          <button
            type="submit"
            className="chat__composer-send"
            disabled={sendDisabled}
            aria-label="Send message"
            data-testid={`${s}-submit`}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          </button>
        </form>

        <p className="chat__composer-hint">
          Press Enter to send · Shift+Enter for a new line · Attach any file (text, PDF, image) — the AI uses every backend tool to answer
        </p>
      </div>
    </div>
  );
}
