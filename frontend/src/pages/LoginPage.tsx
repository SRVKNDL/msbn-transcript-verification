import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  hasAuthSession,
  isAuthConfigured,
  signIn,
} from "../auth";
import { useT } from "../theme";

function LoginField({
  label,
  value,
  onChange,
  type = "text",
  autoComplete,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  autoComplete?: string;
}) {
  const t = useT();
  const [focus, setFocus] = useState(false);

  return (
    <div>
      <div
        style={{
          fontSize: 11,
          color: t.ink3,
          letterSpacing: 0.5,
          textTransform: "uppercase",
          fontFamily: t.mono,
          marginBottom: 5,
        }}
      >
        {label}
      </div>
      <input
        type={type}
        value={value}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={{
          width: "100%",
          padding: "10px 12px",
          background: t.surface,
          color: t.ink,
          border: `1px solid ${focus ? t.primary : t.line}`,
          borderRadius: 3,
          fontSize: 13,
          fontFamily: "inherit",
          outline: "none",
          boxSizing: "border-box",
          boxShadow: focus ? `0 0 0 2px ${t.primary}22` : "none",
          transition: "all 0.12s",
        }}
      />
    </div>
  );
}

export function LoginPage() {
  const t = useT();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (hasAuthSession()) navigate("/dashboard", { replace: true });
  }, [navigate]);

  const handleSignIn = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    if (!isAuthConfigured) {
      setError("Cognito settings are missing from this frontend build.");
      return;
    }
    if (!email.trim() || !password) {
      setError("Email and password are required.");
      return;
    }

    setLoading(true);
    try {
      await signIn(email.trim(), password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: t.bg,
        color: t.ink,
        fontFamily: t.sans,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          width: 420,
          background: t.surface,
          border: `1px solid ${t.line}`,
          borderTop: `3px solid ${t.accent}`,
          padding: "40px 44px",
          borderRadius: 3,
        }}
      >
        {/* Header with seal */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginBottom: 30,
          }}
        >
          <div
            style={{
              width: 42,
              height: 42,
              borderRadius: "50%",
              background: t.primary,
              color: t.primaryInk,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 12,
              fontWeight: 700,
              fontFamily: t.mono,
              letterSpacing: 0.5,
            }}
          >
            MS
          </div>
          <div>
            <div
              style={{
                fontSize: 10,
                color: t.ink4,
                letterSpacing: 1,
                textTransform: "uppercase",
                fontFamily: t.mono,
              }}
            >
              Mississippi Board of Nursing
            </div>
            <div
              style={{
                fontSize: 16,
                fontFamily: t.serif,
                fontWeight: 600,
                color: t.ink,
              }}
            >
              Transcript Verification
            </div>
          </div>
        </div>

        <div
          style={{
            fontSize: 24,
            fontFamily: t.serif,
            fontWeight: 600,
            color: t.ink,
            letterSpacing: -0.3,
          }}
        >
          Staff sign-in
        </div>
        <div
          style={{
            fontSize: 13,
            color: t.ink3,
            marginTop: 4,
            marginBottom: 24,
          }}
        >
          Use your Cognito reviewer account to continue.
        </div>

        <form onSubmit={handleSignIn}>
          <LoginField
            label="Email"
            value={email}
            onChange={setEmail}
            autoComplete="username"
          />
          <div style={{ height: 12 }} />
          <LoginField
            label="Password"
            value={password}
            onChange={setPassword}
            type="password"
            autoComplete="current-password"
          />
          <div style={{ height: 18 }} />

          {error && (
            <div
              style={{
                background: t.highBg,
                border: `1px solid ${t.high}`,
                color: t.high,
                fontSize: 12,
                padding: "8px 10px",
                borderRadius: 3,
                marginBottom: 12,
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "11px",
              background: t.primary,
              color: t.primaryInk,
              border: "none",
              borderRadius: 3,
              fontSize: 14,
              fontWeight: 600,
              cursor: loading ? "wait" : "pointer",
              opacity: loading ? 0.7 : 1,
              fontFamily: "inherit",
            }}
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div
          style={{
            marginTop: 24,
            paddingTop: 18,
            borderTop: `1px solid ${t.line2}`,
            fontSize: 10,
            color: t.ink4,
            fontFamily: t.mono,
            textAlign: "center",
            letterSpacing: 0.3,
            lineHeight: 1.7,
          }}
        >
          Authorized users only. Access is logged under Miss. Code &sect;
          97-45-3.
        </div>
      </div>
    </div>
  );
}
