"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { DietModesAdmin } from "@/components/diet/diet-modes-admin";

export default function DietModesPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Diet list" subtitle="The diets the ward orders and the kitchen prepares." />
      <DietModesAdmin />
    </div>
  );
}
