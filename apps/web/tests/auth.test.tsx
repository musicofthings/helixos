import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const OIDC_ENV = {
  NEXT_PUBLIC_OIDC_AUTHORITY: "https://idp.example.test/",
  NEXT_PUBLIC_OIDC_CLIENT_ID: "helixos-web"
};

beforeEach(() => {
  vi.resetModules();
  for (const key of Object.keys(OIDC_ENV)) vi.stubEnv(key, "");
  vi.stubEnv("NEXT_PUBLIC_API_TOKEN", "");
  window.sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

describe("getAuthConfig", () => {
  it("is off unless both authority and client id are set", async () => {
    const { getAuthConfig } = await import("../lib/auth");
    expect(getAuthConfig()).toBeNull();
    vi.stubEnv("NEXT_PUBLIC_OIDC_AUTHORITY", OIDC_ENV.NEXT_PUBLIC_OIDC_AUTHORITY);
    expect(getAuthConfig()).toBeNull();
  });

  it("reads provider settings with safe defaults", async () => {
    for (const [key, value] of Object.entries(OIDC_ENV)) vi.stubEnv(key, value);
    const { getAuthConfig } = await import("../lib/auth");
    expect(getAuthConfig()).toEqual({
      authority: "https://idp.example.test/",
      clientId: "helixos-web",
      scope: "openid profile email",
      audience: undefined,
      tokenType: "access_token"
    });
    vi.stubEnv("NEXT_PUBLIC_OIDC_TOKEN_TYPE", "id_token");
    vi.stubEnv("NEXT_PUBLIC_OIDC_AUDIENCE", "helixos-api");
    expect(getAuthConfig()).toMatchObject({ tokenType: "id_token", audience: "helixos-api" });
  });
});

describe("AuthGate", () => {
  it("renders the app straight away when sign-in is not configured", async () => {
    const { AuthGate } = await import("../components/auth-gate");
    render(
      <AuthGate>
        <p>the app</p>
      </AuthGate>
    );
    expect(await screen.findByText("the app")).toBeTruthy();
  });

  it("holds the app back while a session is being established", async () => {
    for (const [key, value] of Object.entries(OIDC_ENV)) vi.stubEnv(key, value);
    vi.doMock("../lib/auth", async (original) => ({
      ...(await original<typeof import("../lib/auth")>()),
      initAuth: () => new Promise(() => undefined)
    }));
    const { AuthGate } = await import("../components/auth-gate");
    render(
      <AuthGate>
        <p>the app</p>
      </AuthGate>
    );
    expect(await screen.findByText("Checking your session…")).toBeTruthy();
    expect(screen.queryByText("the app")).toBeNull();
    vi.doUnmock("../lib/auth");
  });

  it("offers a retry when sign-in fails", async () => {
    for (const [key, value] of Object.entries(OIDC_ENV)) vi.stubEnv(key, value);
    vi.doMock("../lib/auth", async (original) => ({
      ...(await original<typeof import("../lib/auth")>()),
      initAuth: () => Promise.reject(new Error("state mismatch"))
    }));
    const { AuthGate } = await import("../components/auth-gate");
    render(
      <AuthGate>
        <p>the app</p>
      </AuthGate>
    );
    expect((await screen.findByRole("alert")).textContent).toContain("state mismatch");
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(screen.queryByText("the app")).toBeNull();
    vi.doUnmock("../lib/auth");
  });
});

describe("api token precedence", () => {
  it("falls back to the build-time token when there is no session", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_TOKEN", "from-env");
    const { getApiToken } = await import("../lib/api-config");
    expect(getApiToken()).toBe("from-env");
  });

  it("prefers a desktop bridge token over everything", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_TOKEN", "from-env");
    (window as unknown as { helixDesktop: unknown }).helixDesktop = { getApiToken: () => "from-bridge" };
    const { getApiToken } = await import("../lib/api-config");
    expect(getApiToken()).toBe("from-bridge");
    delete (window as unknown as { helixDesktop?: unknown }).helixDesktop;
  });
});
