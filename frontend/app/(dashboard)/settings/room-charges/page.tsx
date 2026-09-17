"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { RoomChargesAdmin } from "@/components/ipd/room-charges-admin";

export default function RoomChargesPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Room charges"
        subtitle="The morning posting of bed and nursing charges for every admitted patient."
      />
      <RoomChargesAdmin />
    </div>
  );
}
