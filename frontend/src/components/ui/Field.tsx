import { type ReactNode } from "react";
import clsx from "clsx";

interface FieldProps {
  label: string;
  helperText?: string;
  prefix?: string;
  suffix?: string;
  error?: string;
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
}

export function Field({
  label,
  helperText,
  prefix,
  suffix,
  error,
  children,
  className,
  "data-testid": testId,
}: FieldProps) {
  return (
    <div className={clsx("field", error && "field--error", className)} data-testid={testId}>
      <label className="field__label">
        {label}
        {helperText ? <span className="field__helper">{helperText}</span> : null}
      </label>
      <div className="field__control">
        {prefix ? <span className="field__prefix">{prefix}</span> : null}
        {children}
        {suffix ? <span className="field__suffix">{suffix}</span> : null}
      </div>
      {error ? <p className="field__error">{error}</p> : null}
    </div>
  );
}