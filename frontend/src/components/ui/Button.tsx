import { type ButtonHTMLAttributes, forwardRef } from "react";
import clsx from "clsx";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  /**
   * Defaults to "button". Pass `type="submit"` for form submits — the rest
   * spread allows it, but declaring it keeps contract mistakes visible.
   */
  type?: "button" | "submit" | "reset";
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
      type = "button",
      ...rest
    },
    ref,
  ) => {
    return (
      <button
        ref={ref}
        type={type}
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