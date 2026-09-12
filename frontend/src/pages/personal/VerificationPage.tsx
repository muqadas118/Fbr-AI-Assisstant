import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { StatusBanner } from "@/components/ui/StatusBanner";
import { Tag } from "@/components/ui/Tag";

interface VerificationResult {
  id: string;
  label: string;
  status: "verified" | "insufficient" | "not_verified";
  confidence: number | null;
  sourceAuthority: string | null;
  dateCheck: string | null;
  factualCheck: string | null;
  legalCheck: string | null;
}

export function VerificationPage() {
  const [results, _setResults] = useState<VerificationResult[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // For Part 1: no dedicated verification endpoint exists yet.
  // Show a clear not-connected state.
  if (results === null) {
    return (
      <div className="page page--verification">
        <header className="page__header">
          <h2 className="page__title">Verification</h2>
          <p className="page__subtitle">
            How backend answers are verified. Only actual backend data is displayed.
          </p>
        </header>

        <div className="page__content">
          <StatusBanner
            kind="not-connected"
            title="Verification not connected"
            description="The Verification page is not yet connected to backend verification results. No verification data will be displayed until the backend endpoints are available."
            testId="verification-not-connected"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="page page--verification">
      <header className="page__header">
        <h2 className="page__title">Verification</h2>
        <p className="page__subtitle">How backend answers are verified.</p>
      </header>

      <div className="page__content">
        <Card title="Verification Results" testId="verification-results">
          {results.length === 0 ? (
            <StatusBanner
              kind="info"
              title="No verification results"
              description="No verification data is available yet."
              testId="verification-empty"
            />
          ) : (
            <table className="verification-table" data-testid="verification-table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Source Authority</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr
                    key={r.id}
                    className={selectedId === r.id ? "verification-table__row--selected" : ""}
                    onClick={() => setSelectedId(r.id)}
                    data-testid="verification-row"
                  >
                    <td>{r.label}</td>
                    <td>
                      <Tag
                        variant={
                          r.status === "verified" ? "ok" : r.status === "insufficient" ? "warn" : "err"
                        }
                      >
                        {r.status}
                      </Tag>
                    </td>
                    <td>{r.confidence !== null ? `${r.confidence}%` : "—"}</td>
                    <td>{r.sourceAuthority || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        {selectedId ? (
          <Card title="Verification Details" testId="verification-details">
            <p className="card__body-text">Verification detail view will be available once the backend endpoint is connected.</p>
            <button className="btn btn--ghost" onClick={() => setSelectedId(null)}>Close</button>
          </Card>
        ) : null}
      </div>
    </div>
  );
}