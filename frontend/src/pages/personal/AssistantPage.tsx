import { useCallback } from "react";
import { api, type AssistantAskResponse } from "@/lib/api";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { AssistantChat } from "@/components/assistant/AssistantChat";

export function AssistantPage() {
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
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · AI Assistant</div>
            <h2 className="page__title">AI Tax Assistant</h2>
            <p className="page__subtitle">
              Ask natural-language questions about FBR tax and compliance. The assistant uses
              every backend tool for you — calculators, verification, notice and document
              analysis — and grounds every answer in official FBR law (router + RAG + verification).
            </p>
          </div>
        </header>

        <AssistantChat
          variant="personal"
          ask={ask}
          askStream={askStream}
          loggedIn={true}
          inputLabel="Ask a question"
          inputPlaceholder="e.g. Calculate income tax on Rs 2,500,000 for tax year 2026"
          emptyTitle="Ask your first question"
          emptyDescription="No questions yet. Ask anything about FBR tax, filing obligations, notice types, or compliance timelines — or attach a document and let the AI analyze it."
        />
      </section>
    </ErrorBoundary>
  );
}
