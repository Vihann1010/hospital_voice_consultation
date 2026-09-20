"use client";

import Link from "next/link";
import { ModuleGate } from "@/components/dashboard/module-gate";
import { PageHeader } from "@/components/dashboard/page-header";
import { TheatreBoard } from "@/components/theatre/theatre-board";
import { useModules } from "@/components/dashboard/modules-provider";

export default function TheatrePage() {
  const { words } = useModules();
  return (
    <ModuleGate module="theatre">
      <div className="space-y-6">
        <PageHeader
          title={words.board}
          subtitle={`The day's list, by room, and whether each patient is ready.`}
        />
        <TheatreBoard basePath="/theatre" />
        <p className="text-xs text-ink-faint">
          Rooms and the list of {words.caseWord}s are kept under{" "}
          <Link href="/settings/theatre" className="text-pine hover:underline">{words.setup}</Link>.
        </p>
      </div>
    </ModuleGate>
  );
}
