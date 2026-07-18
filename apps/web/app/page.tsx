import { WorkspaceApp } from "../components/workspace-app";

/**
 * Static-export friendly entry. Desktop detection happens client-side via
 * `window.helixDesktop` / `?helix_desktop=1` (see useDesktopShell / api-config).
 * Avoid awaiting searchParams here — that breaks `HELIX_STATIC_EXPORT=1` builds.
 */
export default function Home() {
  return <WorkspaceApp initialDesktopShell={false} />;
}
