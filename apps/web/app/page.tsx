import { WorkspaceApp } from "../components/workspace-app";

type HomeProps = {
  searchParams: Promise<{ helix_desktop?: string | string[] }>;
};

export default async function Home({ searchParams }: HomeProps) {
  const params = await searchParams;
  const helixDesktop = params.helix_desktop;
  const initialDesktopShell = helixDesktop === "1" || helixDesktop?.[0] === "1";

  return <WorkspaceApp initialDesktopShell={initialDesktopShell} />;
}
