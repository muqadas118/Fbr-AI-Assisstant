import { useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { ApiError, NetworkError, api, isUnauthorized, type AnswerResponse } from "@/lib/api";
import { Loading } from "@/components/shell/Loading";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { VerificationPanel } from "@/components/ui/VerificationPanel";
import { SourceList } from "@/components/ui/SourceCitation";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/state/auth";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  payload?: AnswerResponse;
  error?: string;
  ts: number;
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const payload = message.payload;

  if (isUser) {
    return (
      <div className="chat__msg chat__msg--user" data-testid="biz-chat-user">
        <div className="chat__bubble">{message.text}</div>
      </div>
    );
  }

  if (message.error) {
    const login = /login/i.test(message.text);
    return (
      <div className="chat__msg chat__msg--assistant" data-testid="biz-chat-error">
        <div className="chat__bubble">
          <StatusBanner
            kind="err"
            title={login ? "Login required" : "Could not retrieve answer"}
            description={message.text}
            action={
              login ? (
                <Link to="/login">
                  <Button variant="primary" size="sm" data-testid="biz-message-login">
                    Go to Login
                  </Button>
                </Link>
              ) : undefined
            }
            testId="biz-message-error"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="chat__msg chat__msg--assistant" data-testid="biz-chat-assistant">
      <div className="chat__bubble">
        <p className="chat__answer" data-testid="biz-chat-answer">
          {message.text}
        </p>

        {payload ? (
          <>
            <VerificationPanel
              verification={payload.verification}
              grounded={payload.grounded}
              className="chat__verification"
              testId="biz-chat-verification"
            />
            <DomainBlock
              primary={payload.primary_domain}
              domains={payload.domains}
              multi={payload.multi_domain}
            />
            {payload.sources && payload.sources.length > 0 ? (
              <SourceList sources={payload.sources} testId="biz-chat-sources" />
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}

function DomainBlock({
  primary,
  domains,
  multi,
}: {
  primary: string;
  domains: string[];
  multi: boolean;
}) {
  if (!primary && (!domains || domains.length === 0)) return null;
  return (
    <div className="chat__domains" data-testid="biz-chat-domains">
      <span className="chat__domain-label">Routed to</span>
      <span className="chat__domain-primary">{primary || "general"}</span>
      {multi && domains && domains.length > 1 ? (
        <span className="chat__domain-multi">+ {domains.length - 1} more</span>
      ) : null}
    </div>
  );
}

const SUGGESTED_QUESTIONS = [
  "What is the corporate income tax rate for a private limited company in Pakistan?",
  "When is the annual sales tax return (STR) due for a registered supplier?",
  "What is the penalty for late withholding of WHT on a contractor payment?",
  "What are the compliance deadlines for an AOP's annual filing?",
  "Am I required to register for sales tax once my taxable turnover crosses the threshold?",
  "How do I reconcile output and input sales tax before filing my STR?",
];

export function BusinessAssistantPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const session = useAuth((s) => s.session);

  const submit = useCallback(
    async (q?: string) => {
      const question = (q ?? input).trim();
      if (!question || loading) return;

      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: "user",
        text: question,
        ts: Date.now(),
      };
      setMessages((m) => [...m, userMsg]);
      setInput("");
      setLoading(true);

      try {
        const resp = await api.answer(question);
        const assistantMsg: Message = {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: resp.answer,
          payload: resp,
          ts: Date.now(),
        };
        setMessages((m) => [...m, assistantMsg]);
      } catch (err) {
        const detail =
          err instanceof ApiError || err instanceof NetworkError
            ? err instanceof ApiError && isUnauthorized(err)
              ? "Login required — your session is missing or expired. Please login, then ask again."
              : err.message
            : "An unexpected error occurred.";
        const errMsg: Message = {
          id: `e-${Date.now()}`,
          role: "assistant",
          text: detail,
          error: detail,
          ts: Date.now(),
        };
        setMessages((m) => [...m, errMsg]);
      } finally {
        setLoading(false);
      }
    },
    [input, loading],
  );

  const clear = useCallback(() => {
    setMessages([]);
    setInput("");
  }, []);

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
  };

  return (
    <ErrorBoundary>
      <section className="page page--assistant">
        <header className="page__header">
          <div>
            <p className="page-eyebrow">Business · Tax Assistant</p>
            <h2 className="page__title">Business Tax Assistant</h2>
            <p className="page__subtitle">
              Ask natural-language questions about corporate income tax, sales tax returns,
              withholding statements, and business compliance. Answers are generated by the
              verified backend pipeline (router + RAG + verification).
            </p>
          </div>
          {messages.length > 0 ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={clear}
              data-testid="biz-assistant-clear"
            >
              Clear conversation
            </Button>
          ) : null}
        </header>

        <div className="chat" data-testid="biz-assistant-chat">
          {!session ? (
            <StatusBanner
              kind="warn"
              title="You are not logged in"
              description="Answers need authentication. Please login first, then ask."
              action={
                <Link to="/login">
                  <Button variant="primary" size="sm" data-testid="biz-assistant-login">
                    Go to Login
                  </Button>
                </Link>
              }
              testId="biz-assistant-login-banner"
            />
          ) : null}
          <div className="chat__messages" data-testid="biz-assistant-messages">
            {messages.length === 0 ? (
              <div className="chat__empty">
                <p>
                  No questions yet. Ask anything about company tax, sales tax registration,
                  withholding, corporate filing deadlines, or AOP compliance.
                </p>
                <div className="chat__suggestions" data-testid="biz-suggestions">
                  {SUGGESTED_QUESTIONS.map((q) => (
                    <button
                      key={q}
                      type="button"
                      className="chat__suggestion"
                      onClick={() => void submit(q)}
                      disabled={loading}
                      data-testid="biz-suggestion"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => <MessageBubble key={m.id} message={m} />)
            )}
            {loading ? (
              <div className="chat__msg chat__msg--assistant" data-testid="biz-assistant-typing">
                <div className="chat__bubble">
                  <Loading label="Thinking…" testId="biz-assistant-loading" />
                </div>
              </div>
            ) : null}
          </div>

          <form
            className="chat__form"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
            data-testid="biz-assistant-form"
          >
            <label htmlFor="biz-assistant-input" className="chat__label">
              Ask a business tax question
            </label>
            <textarea
              id="biz-assistant-input"
              className="chat__textarea"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder="e.g. What is the penalty for late filing of a sales tax return?"
              rows={2}
              disabled={loading}
              data-testid="biz-assistant-input"
            />
            <div className="chat__form-actions">
              <span className="chat__hint">
                Press Enter to send, Shift+Enter for new line.
              </span>
              <Button
                type="submit"
                variant="primary"
                disabled={!input.trim() || loading}
                loading={loading}
                data-testid="biz-assistant-submit"
              >
                {loading ? "Thinking…" : "Send"}
              </Button>
            </div>
          </form>
        </div>
      </section>
    </ErrorBoundary>
  );
}