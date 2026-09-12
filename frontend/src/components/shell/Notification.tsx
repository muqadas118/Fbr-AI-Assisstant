import { useNotification } from "@/state/notifications";

export function Notification() {
  const current = useNotification((s) => s.current);
  const dismiss = useNotification((s) => s.dismiss);

  if (!current) return null;

  return (
    <div
      className={`toast toast--${current.kind}`}
      role="status"
      aria-live="polite"
      data-testid="toast"
    >
      <span className="toast__msg">{current.message}</span>
      <button
        type="button"
        className="toast__close"
        aria-label="Dismiss notification"
        onClick={dismiss}
      >
        ×
      </button>
    </div>
  );
}