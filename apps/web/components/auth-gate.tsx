"use client";

import { useEffect, useState } from "react";

import { isDesktopShell } from "../lib/api-config";
import { getAuthConfig, initAuth, signIn } from "../lib/auth";

type GateState = "checking" | "ready" | "redirecting" | "error";

/**
 * Holds the app back until there is a signed-in session. Passes straight
 * through when OIDC is not configured or when running in the desktop shell.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GateState>("checking");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!getAuthConfig() || isDesktopShell()) {
      setState("ready");
      return;
    }
    let cancelled = false;
    initAuth()
      .then((result) => {
        if (!cancelled) setState(result === "signed-in" ? "ready" : "redirecting");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setMessage(error instanceof Error ? error.message : "Sign-in failed");
        setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "ready") {
    return <>{children}</>;
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[#f7f8f5] px-6">
      <div className="max-w-sm text-center">
        <div className="text-xl font-semibold text-ink">HelixOS</div>
        {state === "error" ? (
          <>
            <p role="alert" className="mt-3 text-sm text-graphite">
              We could not sign you in{message ? `: ${message}` : "."}
            </p>
            <button
              type="button"
              onClick={() => {
                window.history.replaceState({}, "", "/");
                void signIn();
              }}
              className="mt-4 rounded-md bg-fern px-4 py-2 text-sm font-medium text-white"
            >
              Try again
            </button>
          </>
        ) : (
          <p className="mt-3 text-sm text-graphite">
            {state === "redirecting" ? "Redirecting to sign in…" : "Checking your session…"}
          </p>
        )}
      </div>
    </main>
  );
}
