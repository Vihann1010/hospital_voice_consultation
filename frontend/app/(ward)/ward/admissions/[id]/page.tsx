"use client";

/** A case sheet at the ward terminal, where nurses sign in. */
import { useParams } from "next/navigation";
import { CaseSheet } from "@/components/ipd/case-sheet";

export default function WardCaseSheetPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <div className="mx-auto max-w-[1400px] px-4 py-5 sm:px-6">
      <CaseSheet admissionId={id} basePath="/ward/admissions" homePath="/ward" />
    </div>
  );
}
