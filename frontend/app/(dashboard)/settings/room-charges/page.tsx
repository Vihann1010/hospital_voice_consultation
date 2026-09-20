"use client";

import { ModuleGate } from "@/components/dashboard/module-gate";
import { PageHeader } from "@/components/dashboard/page-header";
import { RoomChargesAdmin } from "@/components/ipd/room-charges-admin";

export default function RoomChargesPage() {
  return (
    <ModuleGate module="room_charges">
      <div className="space-y-6">
        <PageHeader
          title="Room charges"
          subtitle="The morning posting of bed and nursing charges for every admitted patient."
        />
        <RoomChargesAdmin />
      </div>
    </ModuleGate>
  );
}
