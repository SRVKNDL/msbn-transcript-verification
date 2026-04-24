const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const COGNITO_CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID ?? "";
const COGNITO_REGION = import.meta.env.VITE_COGNITO_REGION ?? "us-east-1";

const SESSION_KEY = "msbn.auth.session";

interface AuthSession {
  idToken: string;
  accessToken: string;
  refreshToken?: string;
  expiresAt: number;
}

export interface CurrentUser {
  displayName: string;
  email: string;
  initials: string;
  role: string;
}

interface TokenResponse {
  IdToken: string;
  AccessToken: string;
  RefreshToken?: string;
  ExpiresIn: number;
}

export const isApiMode = Boolean(API_BASE);
export const isAuthConfigured = Boolean(COGNITO_CLIENT_ID);
export const isAuthRequired = true;

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

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const payload = token.split(".")[1];
  if (!payload) return null;
  try {
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const json = decodeURIComponent(
      atob(normalized)
        .split("")
        .map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, "0")}`)
        .join("")
    );
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function getStringClaim(claims: Record<string, unknown>, key: string) {
  const value = claims[key];
  return typeof value === "string" ? value : "";
}

function initialsFor(displayName: string, email: string) {
  const source = displayName || email.split("@")[0] || "User";
  const parts = source
    .replace(/[._-]+/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  const initials = parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
  return initials || "U";
}

function storeSession(tokens: TokenResponse, existingRefreshToken?: string) {
  const session: AuthSession = {
    idToken: tokens.IdToken,
    accessToken: tokens.AccessToken,
    refreshToken: tokens.RefreshToken ?? existingRefreshToken,
    expiresAt: Date.now() + tokens.ExpiresIn * 1000,
  };
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

function cognitoEndpoint() {
  return `https://cognito-idp.${COGNITO_REGION}.amazonaws.com/`;
}

async function cognitoRequest<T>(target: string, body: object): Promise<T> {
  const response = await fetch(cognitoEndpoint(), {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": `AWSCognitoIdentityProviderService.${target}`,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const message =
      typeof detail.message === "string"
        ? detail.message
        : `Cognito request failed: ${response.status}`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

async function refreshSession(session: AuthSession) {
  if (!session.refreshToken) return null;
  const response = await cognitoRequest<{
    AuthenticationResult?: TokenResponse;
  }>("InitiateAuth", {
    AuthFlow: "REFRESH_TOKEN_AUTH",
    ClientId: COGNITO_CLIENT_ID,
    AuthParameters: {
      REFRESH_TOKEN: session.refreshToken,
    },
  });
  if (!response.AuthenticationResult) return null;
  return storeSession(response.AuthenticationResult, session.refreshToken);
}

export function hasAuthSession() {
  const session = getSession();
  if (!isAuthRequired) return true;
  if (!isAuthConfigured) return false;
  if (!session) return false;
  return session.expiresAt > Date.now() + 60_000 || Boolean(session.refreshToken);
}

export async function getIdToken() {
  if (!isAuthRequired) return null;
  if (!isAuthConfigured) {
    throw new Error("Cognito auth is not configured for this frontend build.");
  }
  const session = getSession();
  if (!session) return null;
  if (session.expiresAt > Date.now() + 60_000) return session.idToken;
  const refreshed = await refreshSession(session);
  return refreshed?.idToken ?? null;
}

export function getCurrentUser(): CurrentUser | null {
  const session = getSession();
  if (!session) return null;
  const claims = decodeJwtPayload(session.idToken);
  if (!claims) return null;

  const email = getStringClaim(claims, "email");
  const givenName = getStringClaim(claims, "given_name");
  const familyName = getStringClaim(claims, "family_name");
  const fullName = getStringClaim(claims, "name");
  const username = getStringClaim(claims, "cognito:username");
  const role = getStringClaim(claims, "custom:role") || "Reviewer";
  const displayName =
    fullName || [givenName, familyName].filter(Boolean).join(" ") || email || username || "User";

  return {
    displayName,
    email,
    initials: initialsFor(displayName, email),
    role,
  };
}

export async function signIn(email: string, password: string) {
  if (!isAuthConfigured) {
    throw new Error("Cognito auth is not configured for this frontend build.");
  }
  const response = await cognitoRequest<{
    AuthenticationResult?: TokenResponse;
    ChallengeName?: string;
  }>("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: COGNITO_CLIENT_ID,
    AuthParameters: {
      USERNAME: email,
      PASSWORD: password,
    },
  });

  if (response.ChallengeName === "NEW_PASSWORD_REQUIRED") {
    throw new Error("This account requires a permanent password in Cognito before dashboard sign-in.");
  }
  if (!response.AuthenticationResult) {
    throw new Error("Cognito sign-in did not return a session.");
  }
  storeSession(response.AuthenticationResult);
}

export function signOut() {
  sessionStorage.removeItem(SESSION_KEY);
  window.location.href = "/";
}
