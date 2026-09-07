import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Inter } from "next/font/google";
import "./globals.css";

const display = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
});

const body = Inter({ subsets: ["latin"], variable: "--font-body" });

export const metadata: Metadata = {
  title: "Satya Trauma & Maternity Center",
  description:
    "Satya Trauma & Maternity Center, Kanpur — voice pre-consultation intake and "
    + "clinical console. Trauma & Orthopedics (Dr. A K Agarwal) and Maternity & "
    + "Gynecology (Dr. Manisha Agarwal).",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body className="min-h-screen font-sans">{children}</body>
    </html>
  );
}
