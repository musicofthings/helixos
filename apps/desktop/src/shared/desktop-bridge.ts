export type SidecarStatus = "starting" | "ready" | "error" | "stopped";

export type HelixDesktopBridge = {
  apiBaseUrl: string;
  apiToken: string;
  webBaseUrl: string;
  mcpBridgeUrl: string;
  platform: NodeJS.Platform;
  sidecarStatus: SidecarStatus;
  isDesktop: true;
};

export type HelixDesktopConfig = HelixDesktopBridge;

export const HELIX_IPC_CHANNELS = {
  getConfig: "helix:get-config",
  restartSidecar: "helix:restart-sidecar",
  sidecarStatus: "helix:sidecar-status"
} as const;

export type SidecarStatusEvent = {
  status: SidecarStatus;
  apiBaseUrl?: string;
  message?: string;
};

/** DOM event name dispatched on the page window when sidecar status changes. */
export const HELIX_SIDECAR_STATUS_EVENT = "helix:sidecar-status-changed";
