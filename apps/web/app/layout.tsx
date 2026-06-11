import type { Metadata } from "next";
import "./globals.css";

import { AppProviders } from "../lib/providers";

export const metadata: Metadata = {
  title: "HelixOS",
  description: "AI-native laboratory management and molecular biology platform"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
