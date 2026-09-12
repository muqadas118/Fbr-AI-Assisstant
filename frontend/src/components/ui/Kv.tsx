import { type ReactNode } from "react";
import clsx from "clsx";

interface KvProps {
  rows: Array<{ key: ReactNode; value: ReactNode }>;
  className?: string;
  testId?: string;
}

export function Kv({ rows, className, testId }: KvProps) {
  return (
    <dl className={clsx("kv", className)} data-testid={testId}>
      {rows.map((row, idx) => (
        <div key={idx} className="kv__row">
          <dt className="kv__key">{row.key}</dt>
          <dd className="kv__value">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}