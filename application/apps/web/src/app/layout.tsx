import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { ResearchBanner } from "@/components/ResearchBanner";

const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Cluster-first breast tumour explorer",
  description:
    "Research prototype: structure-first subgroups, measured cell-line response, not a clinical decision-support tool.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${plexSans.variable} ${plexMono.variable} antialiased`} style={{ fontFamily: "var(--font-plex-sans), system-ui, sans-serif" }}>
        <ResearchBanner />
        {children}
      </body>
    </html>
  );
}
