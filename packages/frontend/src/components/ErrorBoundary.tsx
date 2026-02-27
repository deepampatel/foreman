/**
 * Error boundary — catches React rendering errors gracefully.
 *
 * Learn: Class component required for getDerivedStateFromError.
 * Wraps the app routes to prevent white-screen-of-death on errors.
 * Shows a friendly error message with a retry button.
 */

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <h2>Something went wrong</h2>
          <p className="error-boundary-message">
            {this.state.error?.message || "An unexpected error occurred."}
          </p>
          <button
            className="error-boundary-btn"
            onClick={() => this.setState({ hasError: false })}
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
