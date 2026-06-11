import type { HelixDesktopBridge } from "../shared/desktop-bridge";

declare global {
  interface Window {
    helixDesktop?: HelixDesktopBridge;
    helixDesktopActions?: {
      restartSidecar: () => Promise<HelixDesktopBridge>;
    };
  }
}

export {};
