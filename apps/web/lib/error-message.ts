import { HelixOSApiError } from "@helixos/api-client";

/**
 * User-facing text for a failed request. API errors carry a server request ID;
 * appending it lets support find the matching log lines.
 */
export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof HelixOSApiError && error.requestId) {
    return `${error.message} (ref ${error.requestId})`;
  }
  return error instanceof Error ? error.message : fallback;
}
