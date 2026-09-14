import { useState, useCallback } from "react";
import clsx from "clsx";
import { api, ApiError, NetworkError, type AnswerResponse } from "@/lib/api";
import { Loading } from "@/components/shell/Loading";
import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { Card } from "@/components/ui/Card";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { VerificationPanel } from "@/components/ui/VerificationPanel";
import { SourceList } from "@/components/ui/SourceCitation";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { Field } from "@/components/ui/Field";

const SUGGESTED_QUESTIONS = [
  "What is the current income tax rate for salaried individuals?",
  "What are the WHT rates for professional services?",
  "How to file a sales tax return in Pakistan?",
  "What are the penalties for late filing of income tax return?",
  "What deductions are allowed under Section 60 of the Income Tax Ordinance?",
];

const QUICK_LINKS = [
  {
    label: "Recent SROs",
    query: "Recent SROs (Statutory Regulatory Orders) issued by FBR 2025",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14,2 14,8 20,8"/>
        <line x1="16" x2="8" y1="13" y2="13"/>
        <line x1="16" x2="8" y1="17" y2="17"/>
      </svg>
    ),
  },
  {
    label: "Finance Act 2025",
    query: "Key changes in Finance Act 2025 income tax provisions",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
        <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
      </svg>
    ),
  },
  {
    label: "Property Valuations",
    query: "FBR property valuation tables rates 2025",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect width="7" height="7" x="3" y="3" rx="1"/>
        <rect width="7" height="7" x="14" y="3" rx="1"/>
        <rect width="7" height="7" x="14" y="14" rx="1"/>
        <rect width="7" height="7" x="3" y="14" rx="1"/>
      </svg>
    ),
  },
  {
    label: "Income Tax Slabs",
    query: "Income tax slabs for individuals tax year 2025",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" x2="18" y1="20" y2="10"/>
        <line x1="12" x2="12" y1="20" y2="4"/>
        <line x1="6" x2="6" y1="20" y2="14"/>
      </svg>
    ),
  },
  {
    label: "Sales Tax on Services",
    query: "Sales tax on services in Punjab Sindh KPK Balochistan 2025",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="9" cy="21" r="1"/>
        <circle cx="20" cy="21" r="1"/>
        <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
      </svg>
    ),
  },
  {
    label: "WHT Certificates",
    query: "Withholding tax certificates form 16A requirements",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="9,11 12,14 22,4"/>
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
      </svg>
    ),
  },
];

const QUERY_MAX = 1000;

interface ResearchResult {
  query: string;
  response: AnswerResponse;
  answeredAt: string;
}

function AnswerBlock({ answer }: { answer: string }) {
  const paragraphs = answer.split(/\n+/).filter((p) => p.trim().length > 0);
  return (
    <div className="research__answer" data-testid="research-answer">
      {paragraphs.map((para, i) => {
        const trimmed = para.trim();
        if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
          const items = trimmed.split(/\n/).filter(Boolean);
          return (
            <ul key={i} className="research__list">
              {items.map((item, j) => (
                <li key={j} className="research__list-item">{item.replace(/^[-*]\s*/, "")}</li>
              ))}
            </ul>
          );
        }
        if (/^\d+\.\s/.test(trimmed)) {
          const items = trimmed.split(/\n/).filter(Boolean);
          return (
            <ol key={i} className="research__list">
              {items.map((item, j) => (
                <li key={j} className="research__list-item">{item.replace(/^\d+\.\s*/, "")}</li>
              ))}
            </ol>
          );
        }
        return <p key={i} className="research__para">{trimmed}</p>;
      })}
    </div>
  );
}

function DomainRow({
  primary,
  domains,
  multi,
}: {
  primary: string;
  domains: string[];
  multi: boolean;
}) {
  return (
    <div className="research__domains" data-testid="research-domains">
      <span className="research__domain-label eyebrow">Routed to</span>
      <Tag variant="accent">{primary || "general"}</Tag>
      {multi && domains.length > 1 && (
        <span className="research__domain-multi muted">
          + {domains.length - 1} more
        </span>
      )}
    </div>
  );
}

export function ResearchPage() {
  const [query, setQuery] = useState("");
  const [queryError, setQueryError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) {
      setQueryError("Please enter a research query.");
      return;
    }
    if (trimmed.length > QUERY_MAX) {
      setQueryError(`Query must be ${QUERY_MAX} characters or fewer.`);
      return;
    }
    setQueryError(null);
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await api.answer(trimmed);
      setResult({ query: trimmed, response, answeredAt: new Date().toISOString() });
      setQuery(trimmed);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`FBR Research error (${err.status}): ${err.detail}`);
      } else if (err instanceof NetworkError) {
        setError(`Network error: ${err.message}. Please check your connection and try again.`);
      } else {
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void submit(query);
  };

  const handleQuickLink = (q: string) => {
    void submit(q);
  };

  const handleSuggested = (q: string) => {
    setQuery(q);
    void submit(q);
  };

  const clearResults = () => {
    setResult(null);
    setError(null);
    setQuery("");
    setQueryError(null);
  };

  return (
    <ErrorBoundary>
      <div className="page page--research">
        <header className="page__header">
          <div>
            <div className="page__eyebrow page-eyebrow eyebrow">FBR · Research</div>
            <h2 className="page__title">FBR Research &amp; Updates</h2>
            <p className="page__subtitle">
              Ask about FBR circulars, SROs, tax rates, filing procedures, and compliance requirements. Answers are grounded in authoritative FBR sources.
            </p>
          </div>
          {result && (
            <Button variant="ghost" size="sm" onClick={clearResults} data-testid="research-clear">
              Clear results
            </Button>
          )}
        </header>

        <div className="research-layout">
          {/* ── Main column ── */}
          <div className="research-main">
            {/* Search Form */}
            <Card title="Research Query" testId="research-query-card">
              <form
                onSubmit={handleSubmit}
                className="research-form"
                data-testid="research-form"
              >
                <Field
                  label="Your question"
                  helperText={`Ask about FBR rules, circulars, SROs, rates, or procedures (max ${QUERY_MAX} chars)`}
                  error={queryError ?? undefined}
                  data-testid="research-query-field"
                >
                  <textarea
                    id="research-input"
                    className="research-form__textarea"
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      if (queryError) setQueryError(null);
                    }}
                    placeholder="e.g. What are the income tax slabs for tax year 2025 for salaried individuals?"
                    rows={4}
                    maxLength={QUERY_MAX + 100}
                    disabled={loading}
                    data-testid="research-input"
                  />
                </Field>
                <div className="research-form__footer">
                  <span className="research-form__char-count muted small">
                    {query.length}/{QUERY_MAX}
                  </span>
                  <div className="research-form__actions">
                    <Button
                      type="submit"
                      variant="primary"
                      loading={loading}
                      disabled={loading || !query.trim()}
                      data-testid="research-submit"
                    >
                      {loading ? "Researching…" : "Research"}
                    </Button>
                  </div>
                </div>
              </form>
            </Card>

            {/* Loading state */}
            {loading && (
              <Card testId="research-loading-card">
                <Loading label="Searching FBR sources and generating answer…" testId="research-loading" />
              </Card>
            )}

            {/* Error state */}
            {error && (
              <StatusBanner
                kind="err"
                title="Research failed"
                description={error}
                testId="research-error"
              />
            )}

            {/* Results */}
            {result && !loading && (
              <div className="research-results" data-testid="research-results">
                <Card
                  title="Answer"
                  subtitle={`Asked: ${result.query}`}
                  testId="research-answer-card"
                >
                  <AnswerBlock answer={result.response.answer} />

                  <DomainRow
                    primary={result.response.primary_domain}
                    domains={result.response.domains}
                    multi={result.response.multi_domain}
                  />

                  <div className="research__verification">
                    <VerificationPanel
                      verification={result.response.verification}
                      grounded={result.response.grounded}
                      testId="research-verification"
                    />
                  </div>
                </Card>

                {/* Sources */}
                <Card title="Sources" testId="research-sources-card">
                  <SourceList
                    sources={result.response.sources}
                    testId="research-sources"
                  />
                </Card>

                {/* Answer metadata */}
                <Card title="Answer Metadata" testId="research-meta-card">
                  <div className="research__meta">
                    <Tag variant="accent">{result.response.primary_domain || "general"}</Tag>
                    <span className="muted small">
                      Answered at {new Date(result.answeredAt).toLocaleTimeString("en-PK")}
                    </span>
                    {result.response.grounded ? (
                      <Tag variant="ok">Grounded in sources</Tag>
                    ) : (
                      <Tag variant="warn">Not fully grounded</Tag>
                    )}
                  </div>
                </Card>
              </div>
            )}

            {/* Suggested questions (when no results) */}
            {!result && !loading && (
              <Card title="Suggested Questions" testId="research-suggestions-card">
                <div className="suggested-questions">
                  {SUGGESTED_QUESTIONS.map((q) => (
                    <button
                      key={q}
                      type="button"
                      className="suggested-q"
                      onClick={() => handleSuggested(q)}
                      data-testid={`suggested-${q.slice(0, 20).replace(/\s+/g, "-").toLowerCase()}`}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </Card>
            )}
          </div>

          {/* ── Sidebar ── */}
          <aside className="research-sidebar" aria-label="Quick research links" data-testid="research-sidebar">
            <Card title="Quick Research" testId="research-quick-links-card">
              <div className="quick-links">
                {QUICK_LINKS.map((link) => (
                  <button
                    key={link.label}
                    type="button"
                    className={clsx("quick-link", loading && "quick-link--disabled")}
                    onClick={() => handleQuickLink(link.query)}
                    disabled={loading}
                    data-testid={`quick-link-${link.label.replace(/\s+/g, "-").toLowerCase()}`}
                  >
                    <span className="quick-link__icon" aria-hidden>{link.icon}</span>
                    <span className="quick-link__label">{link.label}</span>
                  </button>
                ))}
              </div>
            </Card>

            <Card title="Research Tips" testId="research-tips-card">
              <ul className="research-tips">
                <li>Be specific about tax year (e.g. "2025") for the most current rules.</li>
                <li>Include the document type if known: "circular", "SRO", "notification".</li>
                <li>Specify "salaried" or "business" for individual tax queries.</li>
                <li>Ask about exemptions or deductions by section number when possible.</li>
              </ul>
            </Card>
          </aside>
        </div>
      </div>
    </ErrorBoundary>
  );
}
