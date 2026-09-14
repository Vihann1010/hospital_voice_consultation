import type { Metadata, Viewport } from "next";
// The fonts ship inside the app rather than being fetched from Google Fonts
// while building: the Docker build runs where fonts.gstatic.com is not
// reachable, and a build that fails for want of a typeface is not worth it.
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/inter";
import "./globals.css";

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
    <html lang="en">
      <body className="min-h-screen font-sans">{children}</body>
    </html>
  );
}
