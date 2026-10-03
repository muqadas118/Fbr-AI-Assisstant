import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import clsx from "clsx";

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: Array<SelectOption | string>;
  /** Same hook as the old native select testid — kept on the trigger button. */
  testId?: string;
  /** Shown when the current value matches no option. */
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
}

function normalize(options: Array<SelectOption | string>): SelectOption[] {
  return options.map((o) => (typeof o === "string" ? { value: o, label: o } : o));
}

/**
 * Custom dropdown replacing every native `<select>` in the app.
 * The open list is fully styled (rounded boundary, padded options) —
 * something the OS-rendered native popup cannot do.
 */
export function Select({ value, onChange, options, testId, placeholder, ariaLabel, className }: SelectProps) {
  const items = useMemo(() => normalize(options), [options]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(() =>
    Math.max(0, items.findIndex((o) => o.value === value)),
  );
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  const selected = items.find((o) => o.value === value) ?? null;

  const close = useCallback(() => {
    setOpen(false);
  }, []);

  const pick = useCallback(
    (next: string) => {
      if (next !== value) onChange(next);
      setOpen(false);
    },
    [onChange, value],
  );

  // Close on outside pointer down / Escape.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  // Keep the highlighted option in view while navigating.
  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.querySelector<HTMLElement>(
      `[data-index="${highlight}"]`,
    );
    if (el?.scrollIntoView) {
      el.scrollIntoView({ block: "nearest" });
    } else if (el && listRef.current) {
      // jsdom and other test environments do not implement
      // scrollIntoView — degrade to manual offset math.
      const list = listRef.current;
      list.scrollTop = el.offsetTop;
    }
  }, [open, highlight]);

  const onTriggerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setHighlight(Math.max(0, items.findIndex((o) => o.value === value)));
      setOpen(true);
    }
  };

  const onListKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(items.length - 1, h + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(0, h - 1));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const item = items[highlight];
      if (item) pick(item.value);
    }
  };

  return (
    <div ref={rootRef} className={clsx("cselect", open && "cselect--open", className)}>
      <button
        type="button"
        className="cselect__trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        data-testid={testId}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onTriggerKeyDown}
      >
        <span className={clsx("cselect__value", !selected && "cselect__value--placeholder")}>
          {selected ? selected.label : (placeholder ?? "Select…")}
        </span>
        <svg
          className="cselect__chevron"
          viewBox="0 0 24 24"
          width="15"
          height="15"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open ? (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          aria-label={ariaLabel ?? "Options"}
          className="cselect__list"
          data-testid={testId ? `${testId}-list` : undefined}
          onKeyDown={onListKeyDown}
        >
          {items.map((item, index) => {
            const isSelected = item.value === value;
            return (
              <li
                key={item.value || `__empty-${index}`}
                role="option"
                aria-selected={isSelected}
                data-index={index}
                data-highlighted={index === highlight || undefined}
                data-testid={testId ? `${testId}-option-${item.value}` : undefined}
                className={clsx("cselect__option", isSelected && "cselect__option--selected")}
                onMouseEnter={() => setHighlight(index)}
                onClick={() => pick(item.value)}
              >
                <span className="cselect__option-label">{item.label}</span>
                {isSelected ? (
                  <svg
                    className="cselect__check"
                    viewBox="0 0 24 24"
                    width="15"
                    height="15"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden
                  >
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
