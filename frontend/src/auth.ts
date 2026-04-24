const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const COGNITO_DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN ?? "";
const COGNITO_CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID ?? "";
const REDIRECT_URI =
  import.meta.env.VITE_COGNITO_REDIRECT_URI ?? window.location.origin + "/";
const LOGOUT_URI =
  import.meta.env.VITE_COGNITO_LOGOUT_URI ?? window.location.origin + "/";

const STATE_KEY = "msbn.oauth.state";
const VERIFIER_KEY = "msbn.oauth.verifier";
const SESSION_KEY = "msbn.auth.session";

interface AuthSession {
  idToken: string;
  accessToken: string;
  refreshToken?: string;
  expiresAt: number;
}

interface TokenResponse {
  id_token: string;
  access_token: string;
  refresh_token?: string;
  expires_in: number;
}

export const isApiMode = Boolean(API_BASE);
export const isAuthConfigured = Boolean(COGNITO_DOMAIN && COGNITO_CLIENT_ID);
export const isAuthRequired = isApiMode && isAuthConfigured;

function base64UrlEncode(bytes: ArrayBuffer | Uint8Array) {
  const data = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const raw = Array.from(data, (byte) => String.fromCharCode(byte)).join("");
  return btoa(raw).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function sha256(value: string) {
  const data = new TextEncoder().encode(value);
  return crypto.subtle.digest("SHA-256", data);
}

function randomString() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

function getSession(): AuthSession | null {
  const stored = sessionStorage.getItem(SESSION_KEY);
  if (!stored) return null;
  try {
    return JSON.parse(stored) as AuthSession;
  } catch {
    sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
}

function storeSession(tokens: TokenResponse, existingRefreshToken?: string) {
  const session: AuthSession = {
    idToken: tokens.id_token,
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token ?? existingRefreshToken,
    expiresAt: Date.now() + tokens.expires_in * 1000,
  };
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

function tokenEndpoint() {
  return `${COGNITO_DOMAIN.replace(/\/$/, "")}/oauth2/token`;
}

async function requestTokens(body: URLSearchParams) {
  const response = await fetch(tokenEndpoint(), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    throw new Error(`Cognito token exchange failed: ${response.status}`);
  }
  return response.json() as Promise<TokenResponse>;
}

async function refreshSession(session: AuthSession) {
  if (!session.refreshToken) return null;
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: COGNITO_CLIENT_ID,
    refresh_token: session.refreshToken,
  });
  const tokens = await requestTokens(body);
  return storeSession(tokens, session.refreshToken);
}

export function hasAuthSession() {
  const session = getSession();
  if (!isAuthRequired) return true;
  if (!session) return false;
  return session.expiresAt > Date.now() + 60_000 || Boolean(session.refreshToken);
}

export async function getIdToken() {
  if (!isAuthRequired) return null;
  const session = getSession();
  if (!session) return null;
  if (session.expiresAt > Date.now() + 60_000) return session.idToken;
  const refreshed = await refreshSession(session);
  return refreshed?.idToken ?? null;
}

export async function signIn() {
  if (!isAuthConfigured) {
    throw new Error("Cognito auth is not configured for this frontend build.");
  }

  const state = randomString();
  const verifier = randomString();
  const challenge = base64UrlEncode(await sha256(verifier));
  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(VERIFIER_KEY, verifier);

  const params = new URLSearchParams({
    response_type: "code",
    client_id: COGNITO_CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    scope: "openid email profile",
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  window.location.href = `${COGNITO_DOMAIN.replace(/\/$/, "")}/oauth2/authorize?${params}`;
}

export async function handleAuthRedirect() {
  const url = new URL(window.location.href);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code) return false;

  const expectedState = sessionStorage.getItem(STATE_KEY);
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);

  if (!state || state !== expectedState || !verifier) {
    throw new Error("Invalid Cognito redirect state.");
  }

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: COGNITO_CLIENT_ID,
    code,
    redirect_uri: REDIRECT_URI,
    code_verifier: verifier,
  });
  const tokens = await requestTokens(body);
  storeSession(tokens);

  url.searchParams.delete("code");
  url.searchParams.delete("state");
  window.history.replaceState({}, document.title, url.pathname + url.search);
  return true;
}

export function signOut() {
  sessionStorage.removeItem(SESSION_KEY);
  if (!isAuthConfigured) {
    window.location.href = "/";
    return;
  }

  const params = new URLSearchParams({
    client_id: COGNITO_CLIENT_ID,
    logout_uri: LOGOUT_URI,
  });
  window.location.href = `${COGNITO_DOMAIN.replace(/\/$/, "")}/logout?${params}`;
}
