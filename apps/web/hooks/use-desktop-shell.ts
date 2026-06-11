"use client";

import { useEffect, useState } from "react";

import { getSidecarStatus, isDesktopShell } from "../lib/api-config";

export type DesktopShellState = {
  isDesktop: boolean;
  sidecarStatus: string | undefined;
  canRestartSidecar: boolean;
};

export function useDesktopShell(initialDesktopShell = false): DesktopShellState {
  const [state, setState] = useState<DesktopShellState>(() => ({
    isDesktop: initialDesktopShell,
    sidecarStatus: initialDesktopShell ? "ready" : undefined,
    canRestartSidecar: false
  }));

  useEffect(() => {
    const desktop = isDesktopShell();
    setState({
      isDesktop: desktop,
      sidecarStatus: getSidecarStatus() ?? (desktop ? "ready" : undefined),
      canRestartSidecar: Boolean(window.helixDesktopActions?.restartSidecar)
    });
  }, []);

  return state;
}
