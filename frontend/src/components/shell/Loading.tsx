import clsx from "clsx";

interface LoadingProps {
  label?: string;
  fullscreen?: boolean;
  testId?: string;
}

export function Loading({ label = "Loading…", fullscreen = false, testId }: LoadingProps) {
  return (
    <div
      className={clsx("state state--loading", fullscreen && "state--full")}
      role="status"
      aria-live="polite"
      data-testid={testId ?? "loading"}
    >
      <div className="spinner" aria-hidden />
      <div className="state__label">{label}</div>
    </div>
  );
}