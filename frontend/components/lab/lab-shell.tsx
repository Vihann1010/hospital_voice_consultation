"use client";

/**
 * The laboratory terminal.
 *
 * Its own shell, like the ward and reception: the bench runs one screen all
 * day — what is waiting, what needs a result, what needs the pathologist — and
 * has no business browsing consultations or revenue. Doctors and the front
 * desk reach it too, and get a link back to where they came from.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft, BarChart3, ClipboardList, FlaskConical, LogOut } from "lucide-react";
import { homeFor, useAuth } from "@/components/dashboard/auth-provider";
import { Logo } from "@/components/brand/logo";
import { cn } from "@/lib/utils";

export function LabShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const links = [
    { href: "/lab", label: "Worklist", icon: ClipboardList,
      active: pathname === "/lab" || pathname.startsWith("/lab/requests") },
    { href: "/lab/tests", label: "Test list", icon: FlaskConical, active: pathname.startsWith("/lab/tests") },
    { href: "/lab/reports", label: "Reports", icon: BarChart3, active: pathname.startsWith("/lab/reports") },
  ];
  const home = user && user.role !== "lab" ? homeFor(user.role) : null;

  return (
    <div className="h-dvh overflow-hidden bg-mint">
      <header className="sticky top-0 z-30 border-b border-pine/10 bg-white print-hidden">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-4 px-4 py-3 sm:px-6">
          <div className="rounded bg-white">
            <Logo className="h-8 w-auto" />
          </div>
          <div className="hidden border-l border-pine/10 pl-4 sm:block">
            <p className="flex items-center gap-1.5 font-display text-sm font-semibold text-pine">
              <FlaskConical className="h-3.5 w-3.5" /> Laboratory
            </p>
            <p className="text-[11px] text-ink-muted">Samples, results &amp; reports</p>
          </div>

          <nav aria-label="Laboratory terminal" className="flex items-center gap-1">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition",
                  link.active ? "bg-pine text-mint" : "text-ink-muted hover:bg-mint hover:text-pine"
                )}
              >
                <link.icon className="h-3.5 w-3.5" /> {link.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {home && (
              <Link
                href={home}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-ink-muted transition hover:bg-mint hover:text-pine"
              >
                <ArrowLeft className="h-3.5 w-3.5" /> Back
              </Link>
            )}
            <div className="hidden text-right sm:block">
              <p className="text-xs font-medium text-ink">{user?.full_name}</p>
              <p className="text-[11px] capitalize text-ink-faint">{user?.role === "lab" ? "Lab technician" : user?.role}</p>
            </div>
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

      <main className="h-[calc(100dvh-65px)] overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-[1400px]">{children}</div>
      </main>
    </div>
  );
}
