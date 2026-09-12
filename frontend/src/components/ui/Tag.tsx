import clsx from "clsx";

interface TagProps {
  children: React.ReactNode;
  variant?: "default" | "accent" | "warn" | "ok" | "err";
  className?: string;
}

export function Tag({ children, variant = "default", className }: TagProps) {
  return <span className={clsx("tag", `tag--${variant}`, className)}>{children}</span>;
}