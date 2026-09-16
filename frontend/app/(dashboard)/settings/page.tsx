"use client";

/** The settings home: every set-up screen this person may open, in one place. */
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  BedDouble, ClipboardList, Contact, LayoutTemplate, Receipt, Salad, ShieldCheck, Tags, UserCog,
} from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { useAuth } from "@/components/dashboard/auth-provider";
import { Card, CardContent } from "@/components/ui/card";

const SCREENS: { href: string; title: string; detail: string; icon: LucideIcon; roles: string[] }[] = [
  { href: "/settings/consultants", title: "Consultants", icon: Contact, roles: ["admin", "manager"],
    detail: "Doctors, OPD days and hours, fees, free follow-up and registration numbers." },
  { href: "/settings/price-list", title: "Price list", icon: Tags, roles: ["admin", "manager"],
    detail: "What each service costs. Needs the finance PIN." },
  { href: "/settings/organisations", title: "Insurers, TPAs and employers", icon: ShieldCheck,
    roles: ["admin", "manager"],
    detail: "Payers a claim can name, and the rates agreed with each." },
  { href: "/settings/wards", title: "Wards and beds", icon: BedDouble, roles: ["admin", "doctor"],
    detail: "Wards, nightly rates, beds, and taking a bed out of service." },
  { href: "/settings/theatre", title: "Operation list", icon: ClipboardList, roles: ["admin", "manager"],
    detail: "Operations, their prices, and the theatre rooms." },
  { href: "/settings/room-charges", title: "Room charges", icon: Receipt, roles: ["admin", "manager"],
    detail: "The morning room-charge run and its history." },
  { href: "/settings/diet-modes", title: "Diet list", icon: Salad, roles: ["admin", "manager"],
    detail: "The diets the ward orders and the kitchen prepares." },
  { href: "/settings/pad-layouts", title: "Pad layouts", icon: LayoutTemplate, roles: ["admin", "doctor"],
    detail: "Sections of the Visit Pad for yourself, a department or the hospital." },
  { href: "/settings/users", title: "Staff accounts", icon: UserCog, roles: ["admin"],
    detail: "Logins, roles and passwords for staff." },
];

export default function SettingsPage() {
  const { user } = useAuth();
  const shown = SCREENS.filter((screen) => screen.roles.includes(user?.role ?? ""));

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" subtitle="Set-up screens for the hospital's lists, prices and staff." />
      {shown.length === 0 ? (
        <p className="text-sm text-ink-muted">There are no settings screens for your role.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map(({ href, title, detail, icon: Icon }) => (
            <Link key={href} href={href}>
              <Card className="h-full transition hover:border-pine/40 hover:bg-pine/5">
                <CardContent className="flex gap-3 p-4">
                  <Icon className="mt-0.5 h-5 w-5 shrink-0 text-pine" />
                  <div>
                    <p className="font-medium text-ink">{title}</p>
                    <p className="text-sm text-ink-muted">{detail}</p>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
