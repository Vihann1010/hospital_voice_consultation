"use client";

/**
 * Shell for the voice intake terminal.
 *
 * Kept deliberately bare: this screen is operated standing up, often by
 * whoever is nearest, and everything on it should be reachable without
 * reading. No navigation, one job.
 */
import { LogOut, Mic } from "lucide-react";
import { useAuth } from "@/components/dashboard/auth-provider";
import { Logo } from "@/components/brand/logo";
import { PlatformMark } from "@/components/brand/platform-mark";

export function IntakeShell({ children }: { children: React.ReactNode }) {
  const { logout } = useAuth();

  return (
    <div className="h-dvh overflow-hidden bg-mint">
      <header className="sticky top-0 z-30 border-b border-pine/10 bg-white">
        <div className="mx-auto flex max-w-[1680px] items-center gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3 rounded bg-white">
            <Logo className="h-8 w-auto" />
            <PlatformMark variant="inline" width={92} />
          </div>
          <div className="hidden border-l border-pine/10 pl-3 sm:block">
            <p className="flex items-center gap-1.5 font-display text-sm font-semibold text-pine">
              <Mic className="h-3.5 w-3.5" /> Voice intake
            </p>
            <p className="text-[11px] text-ink-muted">Patients waiting to be seen</p>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={logout}
              className="rounded-lg p-2 text-ink-faint transition hover:bg-mint hover:text-clay"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="h-[calc(100dvh-65px)] overflow-y-auto px-4 py-6">
        <div className="mx-auto max-w-[1680px]">{children}</div>
      </main>
    </div>
  );
}
