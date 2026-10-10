import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from "react";
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
  const autoId = useId();
  let content = children;
  // The visible <label> must point at the control (htmlFor/id). Controls
  // that already carry their own id keep it; the rest get the generated
  // one injected. Controls with no visible label at all (none here — the
  // label is always rendered) would need an explicit aria-label instead.
  let controlId = autoId;
  if (isValidElement(content)) {
    const control = content as ReactElement<{ id?: string; placeholder?: string }>;
    if (control.props.id) {
      controlId = control.props.id;
      if (prefix && !control.props.placeholder) {
        content = cloneElement(control, { placeholder: `e.g. ${prefix} 500,000` });
      }
    } else {
      content = cloneElement(control, {
        id: controlId,
        ...(prefix && !control.props.placeholder
          ? { placeholder: `e.g. ${prefix} 500,000` }
          : {}),
      });
    }
  }
  return (
    <div className={clsx("field", error && "field--error", className)} data-testid={testId}>
      <label className="field__label" htmlFor={controlId}>
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