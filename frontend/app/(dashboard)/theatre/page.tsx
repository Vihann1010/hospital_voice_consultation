"use client";

import Link from "next/link";
import { PageHeader } from "@/components/dashboard/page-header";
import { TheatreBoard } from "@/components/theatre/theatre-board";

export default function TheatrePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Theatre"
        subtitle="The day's operating list, by theatre, and whether each patient is ready."
      />
      <TheatreBoard basePath="/theatre" />
      <p className="text-xs text-ink-faint">
        Theatres and the operation list are kept under{" "}
        <Link href="/settings/theatre" className="text-pine hover:underline">Operation list</Link>.
      </p>
    </div>
  );
}
