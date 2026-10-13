/**
 * Browser sign-in against any OpenID Connect provider (authorization code + PKCE).
 *
 * Sign-in is active only when NEXT_PUBLIC_OIDC_AUTHORITY and
 * NEXT_PUBLIC_OIDC_CLIENT_ID are set at build time and the app is not running
 * inside the desktop shell (which authenticates to its own sidecar). With no
 * OIDC configuration the app behaves exactly as before (dev token).
 *
 * Everything NEXT_PUBLIC_* is public by design; nothing here is a secret.
 */

import type { User, UserManager } from "oidc-client-ts";

export interface AuthConfig {
  authority: string;
  clientId: string;
  scope: string;
  audience?: string;
  /** Which token the API receives. Most providers: access_token. Google: id_token. */
  tokenType: "access_token" | "id_token";
}

export interface SessionProfile {
  email?: string;
  name?: string;
}

export function getAuthConfig(): AuthConfig | null {
  const authority = process.env.NEXT_PUBLIC_OIDC_AUTHORITY?.trim();
  const clientId = process.env.NEXT_PUBLIC_OIDC_CLIENT_ID?.trim();
  if (!authority || !clientId) {
    return null;
  }
  return {
    authority,
    clientId,
    scope: process.env.NEXT_PUBLIC_OIDC_SCOPE?.trim() || "openid profile email",
    audience: process.env.NEXT_PUBLIC_OIDC_AUDIENCE?.trim() || undefined,
    tokenType: process.env.NEXT_PUBLIC_OIDC_TOKEN_TYPE === "id_token" ? "id_token" : "access_token"
  };
}

let manager: UserManager | null = null;
let token: string | null = null;
let profile: SessionProfile | null = null;
let redirecting = false;
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

/** The bearer token for API calls, or null when not signed in. */
export function getSessionToken(): string | null {
  return token;
}

export function getSessionProfile(): SessionProfile | null {
  return profile;
}

export function subscribeToSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function adopt(user: User, config: AuthConfig): void {
  const value = config.tokenType === "id_token" ? user.id_token : user.access_token;
  token = value ?? null;
  profile = {
    email: typeof user.profile.email === "string" ? user.profile.email : undefined,
    name: typeof user.profile.name === "string" ? user.profile.name : undefined
  };
  notify();
}

function clearSession(): void {
  token = null;
  profile = null;
  notify();
}

async function createManager(config: AuthConfig): Promise<UserManager> {
  // Loaded on demand so builds/shells without OIDC never ship the library.
  const { UserManager, WebStorageStateStore } = await import("oidc-client-ts");
  const origin = window.location.origin;
  return new UserManager({
    authority: config.authority,
    client_id: config.clientId,
    redirect_uri: `${origin}/`,
    post_logout_redirect_uri: `${origin}/`,
    response_type: "code",
    scope: config.scope,
    extraQueryParams: config.audience ? { audience: config.audience } : undefined,
    automaticSilentRenew: false,
    userStore: new WebStorageStateStore({ store: window.sessionStorage })
  });
}

export async function signIn(): Promise<void> {
  const config = getAuthConfig();
  if (!config || redirecting) {
    return;
  }
  redirecting = true;
  manager ??= await createManager(config);
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  await manager.signinRedirect({ state: { returnTo } });
}

export async function signOut(): Promise<void> {
  const config = getAuthConfig();
  if (!config) {
    return;
  }
  manager ??= await createManager(config);
  const idToken = (await manager.getUser())?.id_token;
  clearSession();
  await manager.removeUser();
  try {
    await manager.signoutRedirect({ id_token_hint: idToken });
  } catch {
    // Provider without an end-session endpoint: local sign-out only.
    window.location.assign("/");
  }
}

/** Called when the API says the token is no longer valid. */
export function handleUnauthorized(): void {
  if (getAuthConfig() && !redirecting) {
    clearSession();
    void signIn();
  }
}

function isRedirectCallback(): boolean {
  const params = new URLSearchParams(window.location.search);
  return (params.has("code") && params.has("state")) || (params.has("error") && params.has("state"));
}

/**
 * Establish a session: finish a pending redirect, reuse a stored one, or send
 * the browser to the provider. Resolves "signed-in" or "redirecting".
 */
export function initAuth(): Promise<"signed-in" | "redirecting"> {
  // One run per page load: the redirect callback's one-time state can only be
  // consumed once, and React StrictMode mounts effects twice in development.
  initialization ??= establishSession();
  return initialization;
}

let initialization: Promise<"signed-in" | "redirecting"> | null = null;

async function establishSession(): Promise<"signed-in" | "redirecting"> {
  const config = getAuthConfig();
  if (!config) {
    return "signed-in";
  }
  manager ??= await createManager(config);
  const active = manager;

  active.events.addAccessTokenExpiring(() => {
    // Silent renewal only works with a refresh token (request offline_access).
    void active
      .getUser()
      .then((user) => (user?.refresh_token ? active.signinSilent() : null))
      .then((user) => user && adopt(user, config))
      .catch(() => undefined);
  });
  active.events.addAccessTokenExpired(() => handleUnauthorized());
  active.events.addUserSignedOut(() => handleUnauthorized());

  if (isRedirectCallback()) {
    const user = await active.signinRedirectCallback();
    adopt(user, config);
    const state = user.state as { returnTo?: string } | undefined;
    window.history.replaceState({}, "", state?.returnTo || "/");
    return "signed-in";
  }

  const existing = await active.getUser();
  if (existing && !existing.expired) {
    adopt(existing, config);
    return "signed-in";
  }

  await signIn();
  return "redirecting";
}
