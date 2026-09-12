import { type ButtonHTMLAttributes, forwardRef } from "react";
import clsx from "clsx";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "md",
      loading = false,
      disabled,
      children,
      className,
      ...rest
    },
    ref,
  ) => {
    return (
      <button
        ref={ref}
        type="button"
        disabled={disabled || loading}
        className={clsx(
          "btn",
          `btn--${variant}`,
          `btn--${size}`,
          (disabled || loading) && "btn--disabled",
          className,
        )}
        aria-disabled={disabled || loading}
        data-loading={loading ? "true" : undefined}
        {...rest}
      >
        {loading ? <span className="spinner spinner--inline" aria-hidden /> : null}
        {children}
      </button>
    );
  },
);

Button.displayName = "Button";