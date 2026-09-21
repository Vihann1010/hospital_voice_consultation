import { AuthProvider } from "@/components/dashboard/auth-provider";
import { Sidebar } from "@/components/dashboard/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import { KeyboardProvider } from "@/components/keyboard/keyboard-provider";
import { GlobalShortcuts } from "@/components/keyboard/global-shortcuts";
import { ShortcutHints } from "@/components/keyboard/shortcut-hints";

/**
 * The clinical dashboard. Front-desk staff are sent to the reception terminal
 * instead — every panel here is consultations, prescriptions and revenue,
 * none of which they can load.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider allow={["admin", "manager", "doctor"]} fallbackPath="/reception">
      <ToastProvider>
        <TooltipProvider delayDuration={200}>
          <KeyboardProvider>
            <GlobalShortcuts variant="clinical" />
            <div className="h-dvh overflow-hidden bg-mint">
              <Sidebar />
              <div className="h-full overflow-hidden lg:pl-60">
                <main className="h-full overflow-y-auto px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
                  <div className="mx-auto max-w-[1400px]">{children}</div>
                </main>
              </div>
            </div>
            <ShortcutHints />
          </KeyboardProvider>
        </TooltipProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
