import { AuthProvider } from "@/components/dashboard/auth-provider";
import { WardShell } from "@/components/ward/ward-shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";

/**
 * The ward terminal, in its own route group.
 *
 * Staff are admitted here and are NOT admitted to /dashboard — that gate is
 * already in the dashboard layout, so an IPD incharge signing in has no route
 * into consultations, prescriptions or hospital revenue.
 */
export default function WardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider allow={["admin", "doctor", "supervisor", "reception", "nurse"]} fallbackPath="/dashboard">
      <ToastProvider>
        <TooltipProvider delayDuration={200}>
          <WardShell>{children}</WardShell>
        </TooltipProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
