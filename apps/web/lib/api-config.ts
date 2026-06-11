import { HelixOSClient } from "@helixos/api-client";

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_TOKEN = "org-demo-token";

function readQueryParam(name: string): string | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }

  return new URLSearchParams(window.location.search).get(name) ?? undefined;
}

export function isDesktopShell(): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  return Boolean(window.helixDesktop?.isDesktop || readQueryParam("helix_desktop") === "1");
}

export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    const bridgeUrl = window.helixDesktop?.apiBaseUrl;
    if (bridgeUrl) {
      return bridgeUrl;
    }

    const queryUrl = readQueryParam("helix_api");
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

    const queryToken = readQueryParam("helix_token");
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
