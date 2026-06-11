export type SidecarStatus = "starting" | "ready" | "error" | "stopped";

export type HelixDesktopBridge = {
  apiBaseUrl: string;
  apiToken: string;
  webBaseUrl: string;
  mcpBridgeUrl: string;
  platform: string;
  sidecarStatus: SidecarStatus;
  isDesktop: true;
};

export type HelixDesktopActions = {
  restartSidecar: () => Promise<HelixDesktopBridge>;
};

declare global {
  interface Window {
    helixDesktop?: HelixDesktopBridge;
    helixDesktopActions?: HelixDesktopActions;
  }
}

export {};
