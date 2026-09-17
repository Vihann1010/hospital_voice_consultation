"use client";

import { useParams } from "next/navigation";
import { SurgeryDetail } from "@/components/theatre/surgery-detail";

export default function WardSurgeryPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <div className="mx-auto max-w-[1400px] px-4 py-5 sm:px-6">
      <SurgeryDetail surgeryId={id} caseSheetPath="/ward/admissions" boardPath="/ward/theatre" />
    </div>
  );
}
