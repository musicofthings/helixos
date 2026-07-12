import { HelixOSClient } from "@helixos/api-client";

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_TOKEN = "org-demo-token";

type QuerySnapshot = {
  helix_api?: string;
  helix_token?: string;
  helix_desktop?: string;
};

let querySnapshot: QuerySnapshot | null = null;

/**
 * Read the desktop handoff params once, cache them, then strip the sensitive
 * ones (token, api url) from the visible URL so a bearer token does not linger
 * in browser history or anything that logs the location. Cached values keep
 * query-param-only mode working after the URL is cleaned.
 */
function ensureQuerySnapshot(): QuerySnapshot {
  if (querySnapshot) {
    return querySnapshot;
  }
  if (typeof window === "undefined") {
    return {};
  }

  const params = new URLSearchParams(window.location.search);
  querySnapshot = {
    helix_api: params.get("helix_api") ?? undefined,
    helix_token: params.get("helix_token") ?? undefined,
    helix_desktop: params.get("helix_desktop") ?? undefined
  };

  if (window.history?.replaceState && (querySnapshot.helix_token || querySnapshot.helix_api)) {
    const url = new URL(window.location.href);
    url.searchParams.delete("helix_token");
    url.searchParams.delete("helix_api");
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }

  return querySnapshot;
}

export function isDesktopShell(): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  return Boolean(window.helixDesktop?.isDesktop || ensureQuerySnapshot().helix_desktop === "1");
}

export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    const bridgeUrl = window.helixDesktop?.apiBaseUrl;
    if (bridgeUrl) {
      return bridgeUrl;
    }

    const queryUrl = ensureQuerySnapshot().helix_api;
    if (queryUrl) {
      return queryUrl;
    }
  }

  return process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_BASE_URL;
}

export function getApiToken(): string {
  if (typeof window !== "undefined") {
    const bridgeToken = window.helixDesktop?.apiToken;
    if (bridgeToken) {
      return bridgeToken;
    }

    const queryToken = ensureQuerySnapshot().helix_token;
    if (queryToken) {
      return queryToken;
    }
  }

  return process.env.NEXT_PUBLIC_API_TOKEN ?? DEFAULT_TOKEN;
}

export function getSidecarStatus(): string | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }

  return window.helixDesktop?.sidecarStatus;
}

export function createHelixClient(): HelixOSClient {
  return new HelixOSClient({
    baseUrl: getApiBaseUrl(),
    token: getApiToken()
  });
}
