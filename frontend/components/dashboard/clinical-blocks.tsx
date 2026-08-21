"use client";

/** Reusable clinical presentation blocks shared by patient and consultation views. */
import { AlertTriangle, Pill, ShieldAlert, Scissors, Stethoscope } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { titleCase } from "@/lib/format";

export function InfoRow({ label, value }: { label: string; value?: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex items-baseline gap-3 py-1.5">
      <span className="w-32 shrink-0 text-xs uppercase tracking-wide text-ink-faint">{label}</span>
      <span className="text-sm text-ink">{value}</span>
    </div>
  );
}

export function MedicinesCard({
  medicines,
  className,
}: {
  medicines?: { name: string; dose_or_frequency?: string | null }[];
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
        <Pill className="h-4 w-4 text-pine" />
        <CardTitle>Current medicines</CardTitle>
      </CardHeader>
      <CardContent>
        {!medicines || medicines.length === 0 ? (
          <p className="text-sm text-ink-faint">None reported.</p>
        ) : (
          <ul className="space-y-2">
            {medicines.map((medicine, index) => (
              <li key={`${medicine.name}-${index}`} className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-medium text-ink">{medicine.name}</span>
                {medicine.dose_or_frequency && (
                  <span className="tabular shrink-0 text-xs text-ink-muted">
                    {medicine.dose_or_frequency}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function AllergiesCard({ allergies, className }: { allergies?: string[]; className?: string }) {
  const has = allergies && allergies.length > 0;
  return (
    <Card className={cn(has && "border-clay/35 bg-clay/[0.03]", className)}>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
        <ShieldAlert className={cn("h-4 w-4", has ? "text-clay" : "text-pine")} />
        <CardTitle className={cn(has && "text-clay")}>Allergies</CardTitle>
      </CardHeader>
      <CardContent>
        {!has ? (
          <p className="text-sm text-ink-faint">No known allergies reported.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {allergies!.map((allergy) => (
              <Badge key={allergy} variant="danger" className="gap-1">
                <AlertTriangle className="h-3 w-3" />
                {allergy}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function ConditionsCard({ conditions, className }: { conditions?: string[]; className?: string }) {
  return (
    <Card className={className}>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
        <Stethoscope className="h-4 w-4 text-pine" />
        <CardTitle>Medical history</CardTitle>
      </CardHeader>
      <CardContent>
        {!conditions || conditions.length === 0 ? (
          <p className="text-sm text-ink-faint">Nothing recorded.</p>
        ) : (
          <ul className="space-y-1.5">
            {conditions.map((condition) => (
              <li key={condition} className="flex gap-2 text-sm text-ink">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-pine/40" />
                {condition}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function SurgeriesCard({
  surgeries,
  className,
}: {
  surgeries?: { name: string; year_or_when?: string | null }[];
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
        <Scissors className="h-4 w-4 text-pine" />
        <CardTitle>Previous surgeries</CardTitle>
      </CardHeader>
      <CardContent>
        {!surgeries || surgeries.length === 0 ? (
          <p className="text-sm text-ink-faint">None reported.</p>
        ) : (
          <ul className="space-y-2">
            {surgeries.map((surgery, index) => (
              <li key={`${surgery.name}-${index}`} className="flex items-baseline justify-between gap-3">
                <span className="text-sm text-ink">{surgery.name}</span>
                {surgery.year_or_when && (
                  <span className="tabular shrink-0 text-xs text-ink-muted">{surgery.year_or_when}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function RedFlagList({ flags }: { flags?: string[] }) {
  if (!flags || flags.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {flags.map((flag) => (
        <Badge key={flag} variant="danger" className="gap-1">
          <AlertTriangle className="h-3 w-3" />
          {titleCase(flag)}
        </Badge>
      ))}
    </div>
  );
}
