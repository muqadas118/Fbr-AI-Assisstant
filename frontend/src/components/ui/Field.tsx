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

/** Elements whose id is a valid htmlFor target. */
const LABELABLE = new Set(["input", "select", "textarea", "meter", "output", "progress"]);

/**
 * Walk into a wrapper (e.g. `<label><input/></label>`) and inject `controlId`
 * on the first labelable control that has no id yet. Returns the node
 * unchanged when there is nothing to inject into.
 */
function injectIntoFirstControl(node: ReactNode, controlId: string): ReactNode {
  if (Array.isArray(node)) {
    let changed = false;
    const mapped = node.map((child) => {
      const patched = injectIntoFirstControl(child, controlId);
      if (patched !== child) changed = true;
      return patched;
    });
    return changed ? mapped : node;
  }
  if (!isValidElement(node)) return node;
  const el = node as ReactElement<{ id?: string }>;
  const type = typeof el.type === "string" ? el.type : "";
  if (LABELABLE.has(type) && !el.props.id) {
    return cloneElement(el, { id: controlId });
  }
  const children = (el.props as { children?: ReactNode }).children;
  if (children === undefined || children === null) return node;
  const patched = injectIntoFirstControl(children, controlId);
  return patched !== children ? cloneElement(el, {}, patched) : node;
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
  // The visible <label> must point at the control (htmlFor/id). Controls that
  // already carry their own id keep it; the rest get the generated one:
  //   1. a direct <input>/<select>/<textarea> takes it (plus the prefix hint);
  //   2. a wrapper (e.g. `<label><input/></label>`) has it injected on the
  //      first labelable descendant — that is how checkbox rows stay wired;
  //   3. anything else (e.g. <Select>) receives it as an `id` prop to forward.
  let controlId = autoId;
  if (isValidElement(content)) {
    const control = content as ReactElement<{ id?: string; placeholder?: string }>;
    const type = typeof control.type === "string" ? control.type : "";
    if (LABELABLE.has(type)) {
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
    } else {
      const patched = injectIntoFirstControl(control, autoId);
      if (patched !== control) {
        controlId = autoId;
        content = patched as ReactNode;
      } else {
        content = cloneElement(control, {
          id: autoId,
          ...(prefix && !control.props.placeholder
            ? { placeholder: `e.g. ${prefix} 500,000` }
            : {}),
        });
      }
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
