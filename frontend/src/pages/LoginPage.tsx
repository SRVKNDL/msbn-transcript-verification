import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useT } from "../theme";

function LoginField({
  label,
  value: initial,
  type = "text",
}: {
  label: string;
  value: string;
  type?: string;
}) {
  const t = useT();
  const [value, setValue] = useState(initial);
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
        onChange={(e) => setValue(e.target.value)}
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
          Use your MSBN credentials to continue.
        </div>

        <LoginField label="Email" value="saurav.pant@msbn.ms.gov" />
        <div style={{ height: 12 }} />
        <LoginField
          label="Password"
          value="\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
          type="password"
        />
        <div style={{ height: 18 }} />

        <button
          onClick={() => navigate("/dashboard")}
          style={{
            width: "100%",
            padding: "11px",
            background: t.primary,
            color: t.primaryInk,
            border: "none",
            borderRadius: 3,
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: "inherit",
          }}
        >
          Sign in
        </button>

        <div style={{ marginTop: 16, textAlign: "center", fontSize: 12 }}>
          <a
            href="#"
            onClick={(e) => e.preventDefault()}
            style={{
              color: t.primary,
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            Forgot password?
          </a>
          <span style={{ color: t.ink4, margin: "0 8px" }}>&middot;</span>
          <a
            href="#"
            onClick={(e) => e.preventDefault()}
            style={{ color: t.ink3, textDecoration: "none" }}
          >
            Request access
          </a>
        </div>

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
