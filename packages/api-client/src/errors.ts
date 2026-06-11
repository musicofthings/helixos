export class HelixOSApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "HelixOSApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}
