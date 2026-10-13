"use client";

import { HelixOSApiError } from "@helixos/api-client";
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { AuthGate } from "../components/auth-gate";
import { handleUnauthorized } from "./auth";

/** An expired or revoked token sends the browser back through sign-in. */
function onApiError(error: unknown): void {
  if (error instanceof HelixOSApiError && error.status === 401) {
    handleUnauthorized();
  }
}

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({ onError: onApiError }),
        mutationCache: new MutationCache({ onError: onApiError }),
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1
          }
        }
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthGate>{children}</AuthGate>
    </QueryClientProvider>
  );
}
