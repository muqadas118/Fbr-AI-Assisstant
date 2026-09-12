import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (typeof console !== "undefined" && console.error) {
      console.error("Shell error:", error, info);
    }
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="state state--error" role="alert" data-testid="shell-error">
          <h2 className="state__title">Something went wrong.</h2>
          <p className="state__body">
            The interface could not render this view. Please reload the page. If the issue continues,
            contact support with the time this occurred.
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}