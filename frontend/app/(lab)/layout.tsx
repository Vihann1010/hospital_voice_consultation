import { AuthProvider } from "@/components/dashboard/auth-provider";
import { ModuleGate } from "@/components/dashboard/module-gate";
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
          {/* This whole terminal belongs to a module. At a site that does
              not run it, every request behind these screens 404s, so say
              which it is rather than rendering a shell that cannot work. */}
          <ModuleGate module="laboratory">
            <LabShell>{children}</LabShell>
          </ModuleGate>
        </TooltipProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
