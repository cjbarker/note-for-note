import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  // Optional label so the fallback can name what failed (e.g. "the score").
  label?: string;
}

interface State {
  error: Error | null;
}

// Catches render-time crashes in its subtree so one failing component (e.g. OSMD
// or the audio player) doesn't blank out the whole app.
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled error in", this.props.label ?? "component", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary" role="alert">
          Something went wrong{this.props.label ? ` rendering ${this.props.label}` : ""}.
          <button className="button small" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
