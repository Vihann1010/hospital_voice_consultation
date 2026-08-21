import { AuthProvider } from "@/components/dashboard/auth-provider";
import { Sidebar } from "@/components/dashboard/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";

/**
 * The clinical dashboard. Front-desk staff are sent to the reception terminal
 * instead — every panel here is consultations, prescriptions and revenue,
 * none of which they can load.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider allow={["admin", "doctor"]} fallbackPath="/reception">
      <ToastProvider>
        <TooltipProvider delayDuration={200}>
        <div className="min-h-screen bg-mint">
          <Sidebar />
          <div className="lg:pl-60">
            <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
          </div>
        </div>
        </TooltipProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
