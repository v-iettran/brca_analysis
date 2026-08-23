import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ResearchBanner } from "@/components/ResearchBanner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MOFA-Guided Oncology Research Copilot",
  description:
    "Research prototype mapping a breast cancer RNA profile to MOFA cluster evidence, drug discovery signals, and literature/trial context.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased bg-slate-50 text-slate-900`}>
        <ResearchBanner />
        {children}
      </body>
    </html>
  );
}
