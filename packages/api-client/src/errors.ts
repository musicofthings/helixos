export class HelixOSApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  /** Server-assigned correlation ID (X-Request-ID); quote it when reporting a problem. */
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
    requestId: string | null = null
  ) {
    super(message);
    this.name = "HelixOSApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}
