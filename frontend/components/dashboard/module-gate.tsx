"use client";

/**
 * Wraps a page that belongs to an optional module.
 *
 * The link to it is already hidden when the module is off, but a bookmark, a
 * typed URL or an old printout still gets someone here, and what they would
 * otherwise see is a screen whose every request 404s — which reads as a broken
 * system rather than a feature this clinic does not have. So say which it is.
 *
 * This is politeness, not security: the endpoints behind the page are not
 * registered at all, which is the actual switch.
 */
import Link from "next/link";
import { PackageX } from "lucide-react";
import { useModules, type ModuleName } from "@/components/dashboard/modules-provider";
import { Card, CardContent } from "@/components/ui/card";

const MODULE_LABEL: Record<ModuleName, string> = {
  laboratory: "the laboratory",
  ipd: "admissions and wards",
  diet: "diet orders",
  theatre: "the operation theatre",
  insurance: "insurance claims",
  room_charges: "room charges",
};

export function ModuleGate({
  module,
  children,
}: {
  module: ModuleName;
  children: React.ReactNode;
}) {
  const { enabled, has } = useModules();

  // Still asking. Render nothing rather than flashing either answer.
  if (enabled === null) return null;

  if (!has(module)) {
    return (
      <Card>
        <CardContent className="flex gap-3 p-6">
          <PackageX className="mt-0.5 h-5 w-5 shrink-0 text-ink-faint" />
          <div>
            <p className="font-medium text-ink">
              This clinic does not run {MODULE_LABEL[module]}.
            </p>
            <p className="mt-1 text-sm text-ink-muted">
              The screen is switched off for this installation, so there is
              nothing here to show.{" "}
              <Link href="/dashboard" className="underline">
                Back to the dashboard
              </Link>
              .
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return <>{children}</>;
}
