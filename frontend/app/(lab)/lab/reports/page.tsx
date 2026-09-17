"use client";

import { ReportViewer } from "@/components/reports/report-viewer";
import { useAuth } from "@/components/dashboard/auth-provider";

export default function LabReportsPage() {
  const { user } = useAuth();
  return (
    <div>
      <div className="mb-5">
        <h1 className="font-display text-2xl font-semibold text-pine">Reports</h1>
        <p className="mt-1 text-sm text-ink-muted">
          The lab register, pending results, turnaround, critical values and culture sensitivity.
        </p>
      </div>
      <ReportViewer canConfigure={user?.role === "admin"} />
    </div>
  );
}
