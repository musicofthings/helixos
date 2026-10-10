import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { vi } from "vitest";

/** One fake client object the mocked createHelixClient() always returns. */
export const api: Record<string, ReturnType<typeof vi.fn>> = new Proxy(
  {} as Record<string, ReturnType<typeof vi.fn>>,
  {
    get(target, name: string) {
      return (target[name] ??= vi.fn());
    }
  }
);

export function resetApi(): void {
  for (const key of Object.keys(api)) delete api[key];
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } }
  });
}

export function wrapperFor(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}
