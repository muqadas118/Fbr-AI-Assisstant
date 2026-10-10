import { useCallback } from "react";
import { api, type AssistantAskResponse } from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { AssistantChat } from "@/components/assistant/AssistantChat";
import { useChatActive } from "@/state/chatActive";

const SUGGESTED_QUESTIONS = [
  "What is the corporate income tax rate for a private limited company in Pakistan?",
  "When is the annual sales tax return (STR) due for a registered supplier?",
  "What is the penalty for late withholding of WHT on a contractor payment?",
  "What are the compliance deadlines for an AOP's annual filing?",
  "Am I required to register for sales tax once my taxable turnover crosses the threshold?",
  "How do I reconcile output and input sales tax before filing my STR?",
];

export function BusinessAssistantPage() {
  // While a conversation exists the big header collapses and the chat grows
  // into the freed space — exactly like ChatGPT's sending view.
  const chatActive = useChatActive((st) => st.active);
  // Smart mode: the AI plans and runs every backend tool (calculators,
  // verification, notices, documents, invoices, calendar, health) and
  // grounds the answer in the official FBR corpus. Attachments (text,
  // PDF, image) are read by the backend before answering.
  const ask = useCallback(
    (question: string, file?: File | null) => api.assistantAsk(question, file),
    [],
  );
  const askStream = useCallback(
    (
      question: string,
      handlers: {
        onMeta?: (meta: Partial<AssistantAskResponse>) => void;
        onDelta?: (chunk: string) => void;
      },
    ) => api.assistantAskStream(question, handlers),
    [],
  );

  return (
    <ErrorBoundary>
      <section className="page page--assistant">
        {chatActive ? null : (
          <header className="page__header">
            <div>
              <div className="page__eyebrow page-eyebrow eyebrow">
                FBR · Business AI Assistant
              </div>
              <h2 className="page__title">Business Tax Assistant</h2>
              <p className="page__subtitle">
                Ask natural-language questions about corporate income tax, sales tax returns,
                withholding statements, and business compliance. The assistant uses every backend
                tool for you — calculators, verification, notice and document analysis — and
                grounds every answer in official FBR law (router + RAG + verification).
              </p>
            </div>
          </header>
        )}

        <AssistantChat
          variant="business"
          ask={ask}
          askStream={askStream}
          loggedIn={true}
          inputLabel="Ask a business tax question"
          inputPlaceholder="e.g. Calculate sales tax on Rs 1,000,000 monthly sales"
          emptyDescription="Ask anything about company tax, sales tax registration, withholding, corporate filing deadlines, or AOP compliance — or attach an invoice and let the AI process it."
          suggestions={SUGGESTED_QUESTIONS}
        />
      </section>
    </ErrorBoundary>
  );
}
