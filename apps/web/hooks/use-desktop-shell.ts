"use client";

import { useEffect, useState } from "react";

import { getSidecarStatus, isDesktopShell } from "../lib/api-config";
import type { SidecarStatus, SidecarStatusEvent } from "../types/helix-desktop";

export type DesktopShellState = {
  isDesktop: boolean;
  sidecarStatus: SidecarStatus | undefined;
  canRestartSidecar: boolean;
};

const SIDECAR_STATUS_EVENT = "helix:sidecar-status-changed";

function readInitialDesktopState(initialDesktopShell: boolean): DesktopShellState {
  if (typeof window === "undefined") {
    return {
      isDesktop: initialDesktopShell,
      sidecarStatus: initialDesktopShell ? "starting" : undefined,
      canRestartSidecar: false
    };
  }

  const desktop = initialDesktopShell || isDesktopShell();
  return {
    isDesktop: desktop,
    // Prefer live preload status; otherwise start pessimistic and wait for IPC.
    sidecarStatus: desktop ? ((getSidecarStatus() as SidecarStatus | undefined) ?? "starting") : undefined,
    canRestartSidecar: Boolean(window.helixDesktopActions?.restartSidecar)
  };
}

export function useDesktopShell(initialDesktopShell = false): DesktopShellState {
  const [state, setState] = useState<DesktopShellState>(() =>
    readInitialDesktopState(initialDesktopShell)
  );

  useEffect(() => {
    const desktop = isDesktopShell();
    if (!desktop) {
      setState({
        isDesktop: false,
        sidecarStatus: undefined,
        canRestartSidecar: false
      });
      return;
    }

    const applyStatus = (status: SidecarStatus | undefined) => {
      setState({
        isDesktop: true,
        sidecarStatus: status ?? "starting",
        canRestartSidecar: Boolean(window.helixDesktopActions?.restartSidecar)
      });
    };

    applyStatus((getSidecarStatus() as SidecarStatus | undefined) ?? "starting");

    const unsubscribe = window.helixDesktopActions?.onSidecarStatus?.(
      (event: SidecarStatusEvent) => {
        applyStatus(event.status);
      }
    );

    const onDomEvent = (event: Event) => {
      const detail = (event as CustomEvent<SidecarStatusEvent>).detail;
      if (detail?.status) {
        applyStatus(detail.status);
      }
    };
    window.addEventListener(SIDECAR_STATUS_EVENT, onDomEvent);

    return () => {
      unsubscribe?.();
      window.removeEventListener(SIDECAR_STATUS_EVENT, onDomEvent);
    };
  }, []);

  return state;
}
