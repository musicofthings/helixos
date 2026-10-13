import { HelixOSApiError } from "@helixos/api-client";
import { describe, expect, it } from "vitest";

import { shouldRetry } from "../lib/providers";

describe("shouldRetry", () => {
  it("retries a network or server failure once", () => {
    expect(shouldRetry(0, new TypeError("fetch failed"))).toBe(true);
    expect(shouldRetry(0, new HelixOSApiError(503, "auth_unavailable", "later"))).toBe(true);
    expect(shouldRetry(1, new TypeError("fetch failed"))).toBe(false);
  });

  it("never retries a client error, above all a rate limit", () => {
    for (const status of [400, 401, 403, 404, 409, 413, 422, 429]) {
      expect(shouldRetry(0, new HelixOSApiError(status, "x", "no"))).toBe(false);
    }
  });
});
