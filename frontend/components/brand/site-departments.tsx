"use client";

/**
 * The line under the logo naming what this site does.
 *
 * It used to read "Trauma & Orthopedics · Maternity & Gynecology", typed into
 * the layout. That is the first thing a patient sees, and at a clinic that is
 * neither of those it is the first thing that is wrong. Read from the same
 * setting the registration screens offer.
 */
import { useModules } from "@/components/dashboard/modules-provider";
import { DEPARTMENT_FULL_LABEL } from "@/lib/format";

export function SiteDepartments({ className }: { className?: string }) {
  const { departments } = useModules();
  return (
    <p className={className}>
      {departments.map((d) => DEPARTMENT_FULL_LABEL[d] ?? d).join(" · ")}
    </p>
  );
}
