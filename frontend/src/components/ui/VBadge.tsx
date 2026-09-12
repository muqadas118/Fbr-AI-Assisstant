import clsx from "clsx";

interface VBadgeProps {
  verified: boolean;
  reason?: string | null;
  className?: string;
  testId?: string;
}

export function VBadge({ verified, reason, className, testId }: VBadgeProps) {
  return (
    <span
      className={clsx("vbadge", verified ? "vbadge--verified" : "vbadge--unverified", className)}
      title={verified ? "Verified" : reason ?? "Not verified"}
      data-testid={testId}
    >
      <span className="vbadge__dot" aria-hidden />
      {verified ? "Verified" : "Not verified"}
    </span>
  );
}