"use client";

import { useParams } from "next/navigation";
import { SurgeryDetail } from "@/components/theatre/surgery-detail";

export default function SurgeryPage() {
  const { id } = useParams<{ id: string }>();
  return <SurgeryDetail surgeryId={id} caseSheetPath="/ipd" boardPath="/theatre" />;
}
