import clsx from "clsx";

interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function Spinner({ size = "md", className }: SpinnerProps) {
  return (
    <span
      className={clsx("spinner", `spinner--${size}`, className)}
      role="status"
      aria-label="Loading"
    >
      <span className="spinner__ring" aria-hidden />
    </span>
  );
}