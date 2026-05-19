import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Forge3D — AI 3D Generation Platform",
  description: "Text-to-3D, Image-to-3D, palmilha corretiva. Open-source models.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-br">
      <body>{children}</body>
    </html>
  );
}
