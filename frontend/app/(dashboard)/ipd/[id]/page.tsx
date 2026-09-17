"use client";

/**
 * A case sheet from the clinical dashboard — where the ward board's "Open
 * chart" and the deteriorating-patient alerts have always linked.
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { CaseSheet } from "@/components/ipd/case-sheet";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function CaseSheetPage() {
  const { id } = useParams<{ id: string }>();

  // The ward board's "Admit a patient here" links to /ipd/admit, which lands
  // on this dynamic route. Admitting happens at the ward terminal.
  if (id === "admit") {
    return (
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-sm text-ink-muted">
            Patients are admitted from the ward terminal, where the bed can be chosen.
          </p>
          <Link href="/ward">
            <Button size="sm">Open the ward terminal</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  return <CaseSheet admissionId={id} basePath="/ipd" homePath="/ipd" />;
}
