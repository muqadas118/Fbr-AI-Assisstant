import type { VerificationResult } from "@/lib/api";
import { VBadge } from "./VBadge";
import { Tag } from "./Tag";

interface VerificationPanelProps {
  verification: VerificationResult;
  grounded: boolean;
  className?: string;
  testId?: string;
}

export function VerificationPanel({
  verification,
  grounded,
  className,
  testId,
}: VerificationPanelProps) {
  const checks = verification.checks ?? {};
  const rows = [
    { name: "Answer size", check: checks.answer_size },
    { name: "Section consistency", check: checks.section_consistency },
    { name: "Grounding", check: checks.grounding },
    { name: "Speculation", check: checks.speculation },
  ];

  return (
    <div className={className} data-testid={testId}>
      <div className="verification__head">
        <VBadge verified={verification.passed} reason={verification.reason} />
        <span className="verification__grounded">
          Grounded: {grounded ? "Yes" : "No"}
        </span>
      </div>
      <p className="verification__reason">{verification.reason}</p>
      {(verification.failed_checks ?? []).length > 0 ? (
        <p className="verification__failed">
          Failed: {(verification.failed_checks ?? []).join(", ")}
        </p>
      ) : null}
      <dl className="verification__checks">
        {rows.map((r) => (
          <div key={r.name} className="verification__check-row">
            <dt>{r.name}</dt>
            <dd>
              {r.check == null ? (
                <span className="verification__check-na">—</span>
              ) : r.check.passed ? (
                <Tag variant="ok">Pass</Tag>
              ) : (
                <Tag variant="err">Fail</Tag>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}