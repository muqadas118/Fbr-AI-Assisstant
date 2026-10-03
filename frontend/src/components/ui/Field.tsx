import { cloneElement, isValidElement, type ReactNode } from "react";
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
  // Rs (or any prefix) is now a placeholder that erases on typing —
  // no permanent pill/badge inside the box.
  let content = children;
  if (prefix && isValidElement(content)) {
    const props = (content as React.ReactElement<{ placeholder?: string }>).props;
    if (!props.placeholder) {
      content = cloneElement(content as React.ReactElement<{ placeholder?: string }>, {
        placeholder: `e.g. ${prefix} 500,000`,
      });
    }
  }
  return (
    <div className={clsx("field", error && "field--error", className)} data-testid={testId}>
      <label className="field__label">
        {label}
        {helperText ? <span className="field__helper">{helperText}</span> : null}
      </label>
      <div className="field__control">
        {content}
        {suffix ? <span className="field__suffix">{suffix}</span> : null}
      </div>
      {error ? <p className="field__error">{error}</p> : null}
    </div>
  );
}