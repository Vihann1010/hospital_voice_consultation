import { AuthProvider } from "@/components/dashboard/auth-provider";
import { IntakeShell } from "@/components/intake/intake-shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";

/**
 * The voice intake terminal — its own screen, usually a tablet on a stand
 * near the waiting area. All staff roles may operate it: starting an intake
 * is not clinical authority, it is handing someone a tablet.
 */
export default function IntakeLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider allow={["admin", "doctor", "staff"]} fallbackPath="/dashboard">
      <ToastProvider>
        <TooltipProvider delayDuration={200}>
          <IntakeShell>{children}</IntakeShell>
        </TooltipProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
