import type { Metadata, Viewport } from "next";
import {
  Bricolage_Grotesque,
  Geist,
  Geist_Mono,
  Newsreader,
  Noto_Sans_Devanagari,
} from "next/font/google";
import "./globals.css";

const bricolage = Bricolage_Grotesque({ variable: "--font-bricolage", subsets: ["latin"], display: "swap" });
const newsreader = Newsreader({ variable: "--font-newsreader", subsets: ["latin"], style: ["normal", "italic"], display: "swap", preload: false });
const geist = Geist({ variable: "--font-geist", subsets: ["latin"], display: "swap" });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"], display: "swap", preload: false });
const deva = Noto_Sans_Devanagari({ variable: "--font-devanagari", subsets: ["devanagari"], weight: ["400", "600"], display: "swap", preload: false });

export const metadata: Metadata = {
  title: "SinchaiSlot: water first, then everything else",
  description:
    "A shared solar pump in Samastipur, Bihar, run as a village micro-utility: water for farmers, leftover sun for the mill and batteries, inside a groundwater budget.",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = { themeColor: "#0E1512", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${bricolage.variable} ${newsreader.variable} ${geist.variable} ${geistMono.variable} ${deva.variable}`}
    >
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}
