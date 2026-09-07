"use client";

import { AlertTriangle, Check, CircleDot, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { titleCase } from "@/lib/format";
import type { ConsultationStatus, RiskLevel, TriagePriority } from "@/lib/types";

export function StatusBadge({
  status,
  reviewed,
}: {
  status: ConsultationStatus;
  reviewed?: boolean | null;
}) {
  if (status === "in_progress") {
    return (
      <Badge variant="warning" className="gap-1.5">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-marigold-deep opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-marigold-deep" />
        </span>
        Live intake
      </Badge>
    );
  }
  if (status === "abandoned") {
    return <Badge variant="outline">Disconnected</Badge>;
  }
  return reviewed ? (
    <Badge variant="success" className="gap-1">
      <Check className="h-3 w-3" /> Seen
    </Badge>
  ) : (
    <Badge variant="secondary" className="gap-1">
      <CircleDot className="h-3 w-3" /> Waiting
    </Badge>
  );
}

const RISK_STYLES: Record<RiskLevel, string> = {
  low: "bg-pine/10 text-pine border-transparent",
  moderate: "bg-marigold/20 text-marigold-deep border-transparent",
  high: "bg-clay/12 text-clay border-transparent",
  critical: "bg-clay text-white border-transparent",
};

export function RiskBadge({ risk, className }: { risk?: RiskLevel | null; className?: string }) {
  if (!risk) return null;
  const danger = risk === "high" || risk === "critical";
  return (
    <Badge className={cn(RISK_STYLES[risk], "gap-1", className)}>
      {danger && <AlertTriangle className="h-3 w-3" />}
      {titleCase(risk)} risk
    </Badge>
  );
}

const TRIAGE_STYLES: Record<TriagePriority, string> = {
  routine: "bg-mint text-pine border-transparent",
  soon: "bg-marigold/15 text-marigold-deep border-transparent",
  urgent: "bg-clay/12 text-clay border-transparent",
  immediate: "bg-clay text-white border-transparent",
};

export function TriageBadge({ priority }: { priority?: TriagePriority | null }) {
  if (!priority) return null;
  return <Badge className={cn(TRIAGE_STYLES[priority], "gap-1")}>{titleCase(priority)}</Badge>;
}

/**
 * Every AI-produced element in the dashboard carries this mark. It is
 * deliberately unmissable: the doctor should never have to wonder whether
 * they are looking at recorded fact or machine inference.
 */
export function AiBadge({
  label = "AI Recommendation",
  className,
  source,
}: {
  label?: string;
  className?: string;
  source?: "rule" | "ai";
}) {
  const text = source === "rule" ? "Rule-based check" : label;
  return (
    <Badge variant="ai" className={cn("gap-1 uppercase tracking-wide", className)}>
      <Sparkles className="h-3 w-3" />
      {text}
    </Badge>
  );
}
