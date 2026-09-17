"use client";

import { ReportViewer } from "@/components/reports/report-viewer";
import { useAuth } from "@/components/dashboard/auth-provider";
import { PageHeader } from "@/components/dashboard/page-header";

export default function ReportsPage() {
  const { user } = useAuth();
  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="Collections, billing and the day's closing."
      />
      <div className="mt-5">
        <ReportViewer canConfigure={user?.role === "admin"} />
      </div>
    </div>
  );
}
