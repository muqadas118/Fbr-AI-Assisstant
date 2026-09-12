import { type ReactNode } from "react";
import clsx from "clsx";

interface CardProps {
  children: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  className?: string;
  testId?: string;
}

export function Card({ children, title, subtitle, action, className, testId }: CardProps) {
  return (
    <section className={clsx("card", className)} data-testid={testId}>
      {(title || subtitle || action) ? (
        <div className="card__head">
          <div className="card__title-block">
            {title ? <h3 className="card__title">{title}</h3> : null}
            {subtitle ? <p className="card__subtitle">{subtitle}</p> : null}
          </div>
          {action ? <div className="card__action">{action}</div> : null}
        </div>
      ) : null}
      <div className="card__body">{children}</div>
    </section>
  );
}