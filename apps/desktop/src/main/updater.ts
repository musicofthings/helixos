import { app } from "electron";

export function setupAutoUpdater(): void {
  if (!app.isPackaged || process.env.HELIX_DISABLE_AUTOUPDATE === "1") {
    return;
  }

  // electron-updater is CommonJS-only; load it lazily after Electron bootstraps.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { autoUpdater } = require("electron-updater") as typeof import("electron-updater");

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on("error", (error: Error) => {
    console.error("[helix-updater]", error.message);
  });

  autoUpdater.on("update-downloaded", () => {
    console.log("[helix-updater] Update downloaded; will install on quit");
  });

  void autoUpdater.checkForUpdatesAndNotify();
}
