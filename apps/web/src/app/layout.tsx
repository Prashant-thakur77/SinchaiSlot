import type { Metadata, Viewport } from "next";
import { Eczar, Mukta } from "next/font/google";
import "./globals.css";

// Both faces carry Latin and Devanagari, so Hindi and English are set in the same voice.
const eczar = Eczar({ variable: "--font-eczar", subsets: ["latin"], weight: ["400", "500", "600"], display: "swap" });
const mukta = Mukta({ variable: "--font-mukta", subsets: ["latin", "devanagari"], weight: ["400", "500", "600"], display: "swap", preload: false });

export const metadata: Metadata = {
  title: "SinchaiSlot: water first, then everything else",
  description:
    "A shared solar pump in Samastipur, Bihar, run as a village micro-utility: water for farmers, leftover sun for the mill and batteries, inside a groundwater budget.",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = { themeColor: "#FBF5E7", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${eczar.variable} ${mukta.variable}`}
    >
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}
