import type { Metadata, Viewport } from "next";
// The fonts ship inside the app rather than being fetched from Google Fonts
// while building: the Docker build runs where fonts.gstatic.com is not
// reachable, and a build that fails for want of a typeface is not worth it.
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/inter";
import "./globals.css";
import { ModulesProvider } from "@/components/dashboard/modules-provider";

// Deliberately generic. This is built once and served by every site that runs
// it; one hospital's name and two of its doctors used to be written here, and
// every other site's browser tab said so. The site's own name replaces the
// title as soon as the configuration arrives (see ModulesProvider).
export const metadata: Metadata = {
  title: "Clinical console",
  description: "Voice pre-consultation intake and clinical console.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans">
        {/* One provider for every screen, the sign-in page included: the
            logo, the tab title and the module switches all read it. */}
        <ModulesProvider>{children}</ModulesProvider>
      </body>
    </html>
  );
}
