import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HelixOS",
  description: "AI-native laboratory management and molecular biology platform"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
