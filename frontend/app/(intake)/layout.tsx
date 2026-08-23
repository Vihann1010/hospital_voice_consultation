import { AuthProvider } from "@/components/dashboard/auth-provider";
import { IntakeShell } from "@/components/intake/intake-shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";

/**
 * The voice intake terminal — its own screen, usually a tablet on a stand
 * near the waiting area. Reception staff use the reception terminal instead;
 * this panel is reserved for clinical users.
 */
export default function IntakeLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider allow={["admin", "doctor"]} fallbackPath="/reception">
      <ToastProvider>
        <TooltipProvider delayDuration={200}>
          <IntakeShell>{children}</IntakeShell>
        </TooltipProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
