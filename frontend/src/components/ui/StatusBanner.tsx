import { type ReactNode } from "react";
import clsx from "clsx";

type BannerKind = "info" | "ok" | "warn" | "err" | "not-connected";

interface StatusBannerProps {
  kind: BannerKind;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  testId?: string;
}

export function StatusBanner({
  kind,
  title,
  description,
  action,
  className,
  testId,
}: StatusBannerProps) {
  return (
    <div
      className={clsx("state", `state--${kind}`, className)}
      role={kind === "err" ? "alert" : "status"}
      data-testid={testId}
    >
      <div className="state__icon" aria-hidden>
        {kind === "err" ? (
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
          </svg>
        ) : kind === "warn" ? (
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0ZM12 9v4M12 17h.01" />
          </svg>
        ) : kind === "ok" ? (
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        ) : kind === "not-connected" ? (
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M13 16h-1v-4h-1M13 8h-1M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
          </svg>
        )}
      </div>
      <div className="state__body">
        <h3 className="state__title">{title}</h3>
        {description ? <p className="state__body-text">{description}</p> : null}
        {action ? <div className="state__action">{action}</div> : null}
      </div>
    </div>
  );
}