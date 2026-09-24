"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Activity,
  BedDouble,
  CheckCircle2,
  FileImage,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  Menu,
  Scissors,
  Settings,
  ShieldCheck,
  Stethoscope,
  Landmark,
  UtensilsCrossed,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { initials } from "@/lib/format";
import { useAuth } from "@/components/dashboard/auth-provider";
import { useModules, type ModuleName } from "@/components/dashboard/modules-provider";
import { Logo } from "@/components/brand/logo";
import { PlatformMark } from "@/components/brand/platform-mark";
import { Button } from "@/components/ui/button";

/** Grouped so the front desk's work and the clinician's work are visually
 *  separate — the same sidebar serves both, and mixing them makes each
 *  harder to scan. */
const NAV: {
  href: string;
  label: string;
  icon: LucideIcon;
  group?: string;
  adminOnly?: boolean;
  /** Shown only to these roles. */
  roles?: string[];
  /** Shown only where this module is switched on. Its endpoints do not exist
   *  otherwise, so the link would lead to a 404. */
  module?: ModuleName;
}[] = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/waiting", label: "Waiting patients", icon: Users },
  { href: "/active", label: "Current consultations", icon: Activity },
  { href: "/completed", label: "Completed", icon: CheckCircle2 },
  { href: "/patients", label: "Patient search", icon: Stethoscope },
  { href: "/ipd", label: "Ward board", icon: BedDouble, group: "ward", module: "ipd" },
  // Labelled from the site's vocabulary below: "Theatre" in a hospital,
  // "Procedures" in a clinic whose list is fifteen-minute scopes.
  { href: "/theatre", label: "Theatre", icon: Scissors, group: "ward", module: "theatre" },
  { href: "/diet", label: "Diet sheet", icon: UtensilsCrossed, group: "ward", module: "diet" },
  { href: "/radiology", label: "Radiology", icon: FileImage, group: "ward", module: "radiology" },
  // The laboratory runs in its own terminal; doctors verify results there.
  { href: "/lab", label: "Laboratory", icon: FlaskConical, group: "ward",
    roles: ["admin", "doctor"], module: "laboratory" },
  // Hospital-wide takings: finance:read is held by admin and manager only.
  { href: "/accounts", label: "Accounts", icon: Landmark, group: "desk", roles: ["admin", "manager"] },
  { href: "/insurance", label: "Insurance claims", icon: ShieldCheck, group: "desk",
    roles: ["admin", "manager", "doctor", "supervisor", "reception"], module: "insurance" },
  { href: "/reports", label: "Reports", icon: BarChart3, group: "desk" },
  // Consultants, operation list, room charges, diet list, pad layouts and staff
  // accounts are all opened from the Settings page, filtered there by role.
  { href: "/settings", label: "Settings", icon: Settings, roles: ["admin", "manager", "doctor"] },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user } = useAuth();
  const { has, words } = useModules();
  const items = NAV.filter(
    (item) =>
      (!item.adminOnly || user?.role === "admin") &&
      (!item.roles || (user !== null && user !== undefined && item.roles.includes(user.role))) &&
      (!item.module || has(item.module))
  );
  return (
    <nav className="thin-scroll flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-3 pb-2">
      {items.map((item) => {
        // The most specific link wins, so "Settings" is not lit on every settings page.
        const matches = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
        const active = matches(item.href)
          && !items.some((other) => other.href.length > item.href.length && matches(other.href));
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            className={cn(
              "relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition",
              active ? "text-mint" : "text-mint/60 hover:bg-white/5 hover:text-mint/90"
            )}
          >
            {active && (
              <motion.span
                layoutId="nav-active"
                className="absolute inset-0 rounded-lg bg-white/10"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            )}
            <item.icon className="relative h-4 w-4 shrink-0" />
            <span className="relative">
              {item.href === "/theatre" ? words.board : item.label}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth();
  return (
    <div className="flex h-full flex-col bg-pine-deep">
      {/* The logo sits on a white strip rather than directly on the navy.
          Its blue mark (#0B55A1) is close enough to the sidebar (#073E75)
          that the letterform disappears against it, and putting a stroke on
          the mark would mean altering the hospital's logo. A white panel
          keeps the brand colours exact and the contrast unambiguous. */}
      <div className="flex shrink-0 flex-wrap items-center gap-3 bg-white px-5 py-4">
        <Logo width={132} priority />
        <PlatformMark variant="inline" width={72} />
      </div>
      <p className="shrink-0 px-5 pb-1 pt-4 text-[10px] uppercase tracking-[0.18em] text-mint/45">
        Clinical console
      </p>

      <NavLinks onNavigate={onNavigate} />

      <div className="shrink-0 border-t border-white/10 p-4">
        <div className="flex items-center gap-3 px-1 pb-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-semibold text-mint">
            {initials(user?.full_name)}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-mint">{user?.full_name ?? "—"}</p>
            <p className="truncate text-xs capitalize text-mint/50">
              {user?.department ? `${user.role} · ${user.department}` : user?.role ?? ""}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={logout}
          className="w-full justify-start text-mint/60 hover:bg-white/5 hover:text-mint"
        >
          <LogOut className="h-4 w-4" /> Sign out
        </Button>
      </div>
    </div>
  );
}

export function Sidebar() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 lg:block">
        <SidebarBody />
      </aside>

      <div className="sticky top-0 z-40 flex items-center justify-between border-b border-border bg-white px-4 py-2.5 lg:hidden">
        <span className="flex items-center gap-2">
          <Logo width={116} />
          <PlatformMark variant="inline" width={64} />
        </span>
        <button
          onClick={() => setOpen((v) => !v)}
          className="rounded-md p-2 text-pine transition hover:bg-mint"
          aria-label={open ? "Close navigation" : "Open navigation"}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-pine-deep/50" onClick={() => setOpen(false)} />
          <motion.div
            initial={{ x: -280 }}
            animate={{ x: 0 }}
            transition={{ type: "spring", stiffness: 420, damping: 38 }}
            className="absolute inset-y-0 left-0 w-64"
          >
            <SidebarBody onNavigate={() => setOpen(false)} />
          </motion.div>
        </div>
      )}
    </>
  );
}
