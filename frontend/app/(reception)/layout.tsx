import { AuthProvider } from "@/components/dashboard/auth-provider";
import { ReceptionShell } from "@/components/reception/reception-shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import { KeyboardProvider } from "@/components/keyboard/keyboard-provider";
import { GlobalShortcuts } from "@/components/keyboard/global-shortcuts";
import { ShortcutHints } from "@/components/keyboard/shortcut-hints";

/**
 * The reception terminal runs outside the clinical dashboard entirely: its own
 * route group, its own shell, no clinical navigation.
 *
 * Reception, supervisor, doctor and admin are all allowed. Front-desk work is
 * not clinical authority, and a doctor or admin covering the counter should
 * not have to sign in as somebody else. A manager has no counter role and is
 * sent to the dashboard, where their work lives.
 */
export default function ReceptionLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider allow={["admin", "doctor", "supervisor", "reception"]} fallbackPath="/dashboard">
      <ToastProvider>
        <TooltipProvider delayDuration={200}>
          <KeyboardProvider>
            <GlobalShortcuts variant="reception" />
            <ReceptionShell>{children}</ReceptionShell>
            <ShortcutHints />
          </KeyboardProvider>
        </TooltipProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
