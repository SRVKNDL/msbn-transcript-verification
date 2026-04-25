import { Component, type ErrorInfo, type ReactNode } from "react";
import { TOKENS, LAYOUT } from "../tokens";

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

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Review page render failed", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div
        style={{
          width: "100vw",
          height: "100vh",
          background: LAYOUT.bg,
          color: TOKENS.ink,
          fontFamily: "'Open Sans', system-ui, sans-serif",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          boxSizing: "border-box",
        }}
      >
        <div
          style={{
            width: "min(560px, 100%)",
            background: TOKENS.paper,
            border: `1px solid ${TOKENS.line}`,
            borderTop: `3px solid ${TOKENS.high}`,
            borderRadius: 3,
            padding: "24px 28px",
            boxShadow: "0 18px 45px rgba(0,0,0,0.16)",
          }}
        >
          <div
            style={{
              fontSize: 11,
              color: TOKENS.ink4,
              fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
              letterSpacing: 0.6,
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            Frontend error
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 10, fontFamily: "'Montserrat', system-ui, sans-serif" }}>
            This review page could not render
          </div>
          <div style={{ fontSize: 13, color: TOKENS.ink2, lineHeight: 1.6, marginBottom: 18 }}>
            {this.state.error.message || "An unknown rendering error occurred."}
          </div>
          <button
            onClick={() => {
              window.location.href = "/queue";
            }}
            style={{
              border: "none",
              background: TOKENS.ink,
              color: "#fff",
              padding: "9px 14px",
              fontSize: 12,
              fontWeight: 600,
              borderRadius: 2,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            Back to review queue
          </button>
        </div>
      </div>
    );
  }
}
