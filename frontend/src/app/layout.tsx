import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Content Factory — AI-Powered Content Generation",
  description: "Transform ideas into high-quality video content with multi-agent AI.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
