import { AuthProvider } from "@/components/dashboard/auth-provider";
import { LabShell } from "@/components/lab/lab-shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";

/**
 * The laboratory terminal, in its own route group.
 *
 * Open to the bench, to doctors (the pathologist verifies here), and to the
 * front desk and ward nurses, who send samples. A manager has no lab work and
 * is sent to the dashboard.
 */
export default function LabLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider allow={["admin", "doctor", "supervisor", "reception", "nurse", "lab"]} fallbackPath="/dashboard">
      <ToastProvider>
        <TooltipProvider delayDuration={200}>
          <LabShell>{children}</LabShell>
        </TooltipProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
