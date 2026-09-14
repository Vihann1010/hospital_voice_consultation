"use client";

import { LabTestList } from "@/components/lab/lab-test-list";

export default function LabTestsPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-display text-2xl font-semibold text-pine">Test list</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Each test&apos;s result lines, units and reference ranges. Every flag on a report is computed from these,
          so a test cannot be verified until a doctor has reviewed its ranges.
        </p>
      </div>
      <LabTestList />
    </div>
  );
}
