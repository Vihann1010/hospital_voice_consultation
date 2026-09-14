"use client";

import { useParams } from "next/navigation";
import { LabRequestView } from "@/components/lab/lab-request-view";

export default function LabRequestPage() {
  const params = useParams<{ id: string }>();
  return <LabRequestView requestId={params.id} />;
}
