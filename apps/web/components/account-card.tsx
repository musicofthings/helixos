"use client";

import { LogOut } from "lucide-react";
import { useSyncExternalStore } from "react";

import { getAuthConfig, getSessionProfile, signOut, subscribeToSession } from "../lib/auth";

/** Who is signed in, with a sign-out button. Renders nothing without OIDC sign-in. */
export function AccountCard() {
  const profile = useSyncExternalStore(subscribeToSession, getSessionProfile, () => null);
  if (!getAuthConfig() || !profile) {
    return null;
  }
  const label = profile.name ?? profile.email ?? "Signed in";
  return (
    <section className="mt-8 flex items-center justify-between gap-2 rounded-md border border-black/10 bg-white p-3">
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-ink">{label}</div>
        {profile.name && profile.email ? <div className="truncate text-xs text-graphite">{profile.email}</div> : null}
      </div>
      <button
        type="button"
        onClick={() => void signOut()}
        aria-label="Sign out"
        title="Sign out"
        className="rounded-md p-2 text-graphite hover:bg-black/5 hover:text-ink"
      >
        <LogOut size={16} />
      </button>
    </section>
  );
}
