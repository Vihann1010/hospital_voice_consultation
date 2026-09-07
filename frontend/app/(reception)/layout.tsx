import { AuthProvider } from "@/components/dashboard/auth-provider";
import { ReceptionShell } from "@/components/reception/reception-shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";

/**
 * The reception terminal runs outside the clinical dashboard entirely: its own
 * route group, its own shell, no clinical navigation.
 *
 * All three staff roles are allowed. Front-desk work is not clinical
 * authority, and a doctor or admin covering the counter should not have to
 * sign in as somebody else.
 */
export default function ReceptionLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider allow={["admin", "doctor", "staff"]} fallbackPath="/dashboard">
      <ToastProvider>
        <TooltipProvider delayDuration={200}>
          <ReceptionShell>{children}</ReceptionShell>
        </TooltipProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
