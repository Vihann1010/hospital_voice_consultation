"use client";

/**
 * AI Copilot — clinical decision support.
 *
 * Design rule enforced throughout this file: nothing here is presented as a
 * decision. Every generated element carries an explicit "AI Recommendation"
 * mark, deterministic checks are labelled as rule-based, and each suggestion
 * can be accepted or dismissed by the doctor. The doctor's ruling is stored
 * separately from the AI output, so the record shows both what was suggested
 * and what the clinician decided.
 */
import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  CircleAlert,
  ClipboardList,
  FlaskConical,
  GraduationCap,
  HelpCircle,
  Loader2,
  Pill,
  RefreshCw,
  ShieldAlert,
  Split,
  UserPlus,
  X,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type {
  ClinicalDossier,
  CopilotBriefing,
  CopilotDecision,
  MedicationAlert,
} from "@/lib/types/core";
import { titleCase } from "@/lib/format";
import { AiBadge } from "@/components/dashboard/badges";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const SEVERITY_STYLE: Record<MedicationAlert["severity"], string> = {
  serious: "border-clay/40 bg-clay/[0.04]",
  caution: "border-marigold/40 bg-marigold/[0.05]",
  info: "border-border bg-white",
};

const ALERT_ICON = {
  interaction: Split,
  allergy: ShieldAlert,
  duplicate: Pill,
} as const;

const ALERT_TITLE = {
  interaction: "Drug interaction",
  allergy: "Allergy conflict",
  duplicate: "Duplicate medicine",
} as const;

/** Accept / dismiss control. The doctor's decision is the authoritative record. */
function DecisionControls({
  itemKey,
  decision,
  onDecide,
  busy,
}: {
  itemKey: string;
  decision?: CopilotDecision;
  onDecide: (key: string, value: "accepted" | "dismissed") => void;
  busy: boolean;
}) {
  if (decision && decision.decision !== "pending") {
    const accepted = decision.decision === "accepted";
    return (
      <div className="flex items-center gap-2">
        <Badge variant={accepted ? "success" : "outline"} className="gap-1">
          {accepted ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
          {accepted ? "Accepted" : "Dismissed"}
          {decision.doctor_name ? ` · ${decision.doctor_name.split(" ")[0]}` : ""}
        </Badge>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-2 text-[11px]"
          disabled={busy}
          onClick={() => onDecide(itemKey, accepted ? "dismissed" : "accepted")}
        >
          Change
        </Button>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1.5">
      <Button
        size="sm"
        variant="outline"
        className="h-7 px-2.5 text-[11px]"
        disabled={busy}
        onClick={() => onDecide(itemKey, "accepted")}
      >
        <Check className="h-3 w-3" /> Accept
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="h-7 px-2.5 text-[11px]"
        disabled={busy}
        onClick={() => onDecide(itemKey, "dismissed")}
      >
        <X className="h-3 w-3" /> Dismiss
      </Button>
    </div>
  );
}

function Section({
  title,
  icon: Icon,
  count,
  children,
  defaultOpen = true,
  tone = "default",
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  count?: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
  tone?: "default" | "danger";
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-border last:border-0">
      <button
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2.5 px-5 py-3.5 text-left transition hover:bg-mint/50"
        aria-expanded={open}
      >
        <Icon className={cn("h-4 w-4 shrink-0", tone === "danger" ? "text-clay" : "text-pine")} />
        <span
          className={cn(
            "flex-1 font-display text-sm font-semibold",
            tone === "danger" ? "text-clay" : "text-pine"
          )}
        >
          {title}
        </span>
        {count !== undefined && count > 0 && (
          <Badge variant={tone === "danger" ? "danger" : "secondary"} size="sm">
            {count}
          </Badge>
        )}
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 text-ink-faint transition-transform", open && "rotate-180")}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="space-y-3 px-5 pb-4">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function CopilotPanel({
  consultationId,
  dossier,
}: {
  consultationId: string;
  dossier: ClinicalDossier | null;
}) {
  const [briefing, setBriefing] = useState<CopilotBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, CopilotDecision>>({});

  const load = useCallback(
    async (refresh = false) => {
      refresh ? setRefreshing(true) : setLoading(true);
      try {
        const result = await staffApi.copilot(consultationId, refresh);
        setBriefing(result);
        setDecisions(result.decisions ?? {});
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Copilot is unavailable right now.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [consultationId]
  );

  useEffect(() => {
    void load();
  }, [load]);

  const decide = useCallback(
    async (key: string, value: "accepted" | "dismissed") => {
      setBusyKey(key);
      const previous = decisions[key];
      setDecisions((current) => ({ ...current, [key]: { decision: value } }));
      try {
        const saved = await staffApi.recordCopilotDecision(consultationId, {
          item_key: key,
          decision: value,
        });
        setDecisions((current) => ({ ...current, [key]: saved }));
      } catch {
        setDecisions((current) => {
          const next = { ...current };
          if (previous) next[key] = previous;
          else delete next[key];
          return next;
        });
      } finally {
        setBusyKey(null);
      }
    },
    [consultationId, decisions]
  );

  const risk = dossier?.risk_assessment;
  const summary = dossier?.clinical_summary;
  const differentials = dossier?.differential_diagnosis?.differentials ?? [];
  const investigations = dossier?.investigations?.investigations ?? [];
  const education = dossier?.patient_education;

  const allergyAlerts = (briefing?.medication_alerts ?? []).filter((a) => a.kind === "allergy");
  const duplicateAlerts = (briefing?.medication_alerts ?? []).filter((a) => a.kind === "duplicate");
  const interactionAlerts = (briefing?.medication_alerts ?? []).filter((a) => a.kind === "interaction");

  return (
    <Card className="overflow-hidden">
      {/* Header — the framing the doctor sees first */}
      <div className="border-b border-border bg-gradient-to-br from-pine to-pine-soft px-5 py-4 text-mint">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-display text-base font-semibold">AI Copilot</p>
            <p className="mt-0.5 text-xs leading-relaxed text-mint/70">
              Decision support only. Every item below is a suggestion for you to verify —
              <strong className="font-semibold text-mint"> you remain the final authority</strong>.
            </p>
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon"
                variant="ghost"
                className="shrink-0 text-mint/70 hover:bg-white/10 hover:text-mint"
                onClick={() => void load(true)}
                disabled={refreshing}
                aria-label="Regenerate copilot briefing"
              >
                <RefreshCw className={refreshing ? "animate-spin" : ""} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Regenerate from the latest record</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {error && (
        <div className="border-b border-border bg-clay/5 px-5 py-3 text-sm text-clay">{error}</div>
      )}

      {loading ? (
        <div className="space-y-3 p-5">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      ) : (
        <div>
          {/* 1. Clinical summary */}
          <Section title="Clinical summary" icon={ClipboardList}>
            {summary?.one_liner || summary?.summary_for_doctor ? (
              <div className="rounded-lg border-l-2 border-marigold bg-marigold/[0.04] p-3.5">
                <AiBadge className="mb-2" />
                {summary?.one_liner && (
                  <p className="text-sm font-medium leading-relaxed text-ink">{summary.one_liner}</p>
                )}
                {summary?.summary_for_doctor && (
                  <p className="mt-2 text-sm leading-relaxed text-ink-muted">
                    {summary.summary_for_doctor}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-sm text-ink-faint">No summary generated for this visit.</p>
            )}
          </Section>

          {/* 2. Red flags */}
          <Section
            title="Red flags"
            icon={AlertTriangle}
            count={risk?.red_flags?.length ?? 0}
            tone={risk?.emergency || (risk?.red_flags?.length ?? 0) > 0 ? "danger" : "default"}
          >
            {risk?.emergency && (
              <div className="flex items-start gap-2 rounded-lg bg-clay px-3.5 py-3 text-white">
                <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  <p className="text-sm font-semibold">Emergency features detected</p>
                  {risk.recommended_action && (
                    <p className="mt-0.5 text-xs text-white/85">{risk.recommended_action}</p>
                  )}
                </div>
              </div>
            )}
            {!risk?.red_flags?.length && !risk?.emergency ? (
              <p className="text-sm text-ink-faint">No red flags identified.</p>
            ) : (
              risk?.red_flags?.map((flag, index) => (
                <div
                  key={`${flag.flag}-${index}`}
                  className="rounded-lg border-l-2 border-clay bg-clay/[0.04] p-3.5"
                >
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-clay">{titleCase(flag.flag)}</span>
                    <Badge variant="danger" size="sm">
                      {titleCase(flag.severity)}
                    </Badge>
                  </div>
                  {flag.rationale && <p className="text-xs text-ink-muted">{flag.rationale}</p>}
                </div>
              ))
            )}
          </Section>

          {/* 3. Allergy alerts */}
          <Section
            title="Allergy alerts"
            icon={ShieldAlert}
            count={allergyAlerts.length}
            tone={allergyAlerts.length > 0 ? "danger" : "default"}
          >
            <AlertList
              alerts={allergyAlerts}
              emptyText="No conflicts between recorded allergies and current medicines."
              decisions={decisions}
              onDecide={decide}
              busyKey={busyKey}
            />
          </Section>

          {/* 4. Duplicate medicines */}
          <Section title="Duplicate medicine alerts" icon={Pill} count={duplicateAlerts.length}>
            <AlertList
              alerts={duplicateAlerts}
              emptyText="No duplicate ingredients or overlapping drug classes found."
              decisions={decisions}
              onDecide={decide}
              busyKey={busyKey}
            />
          </Section>

          {/* 5. Drug interactions */}
          <Section title="Drug interaction alerts" icon={Split} count={interactionAlerts.length}>
            <AlertList
              alerts={interactionAlerts}
              emptyText="No significant interactions suggested for the current medicine list."
              decisions={decisions}
              onDecide={decide}
              busyKey={busyKey}
            />
          </Section>

          {/* 6. Differentials */}
          <Section title="Likely differential diagnoses" icon={Split} count={differentials.length}>
            {differentials.length === 0 ? (
              <p className="text-sm text-ink-faint">No differentials generated.</p>
            ) : (
              differentials.map((item, index) => {
                const key = `differential:${item.condition}`;
                return (
                  <div key={key} className="rounded-lg border-l-2 border-marigold bg-marigold/[0.04] p-3.5">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <span className="tabular text-xs font-bold text-marigold-deep">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <span className="text-sm font-semibold text-ink">{item.condition}</span>
                      <Badge variant="outline" size="sm">
                        {titleCase(item.likelihood)} likelihood
                      </Badge>
                      <AiBadge label="AI Suggestion" />
                    </div>
                    {item.supporting_features && item.supporting_features.length > 0 && (
                      <p className="text-xs text-ink-muted">
                        <span className="font-semibold text-pine">Supports: </span>
                        {item.supporting_features.join("; ")}
                      </p>
                    )}
                    {item.features_against && item.features_against.length > 0 && (
                      <p className="mt-1 text-xs text-ink-muted">
                        <span className="font-semibold text-clay">Against: </span>
                        {item.features_against.join("; ")}
                      </p>
                    )}
                    {item.would_change_with && (
                      <p className="mt-1.5 text-xs italic text-ink-muted">
                        Would be settled by: {item.would_change_with}
                      </p>
                    )}
                    <div className="mt-2.5">
                      <DecisionControls
                        itemKey={key}
                        decision={decisions[key]}
                        onDecide={decide}
                        busy={busyKey === key}
                      />
                    </div>
                  </div>
                );
              })
            )}
            <p className="pt-1 text-[11px] leading-relaxed text-ink-faint">
              {dossier?.differential_diagnosis?.disclaimer ??
                "Decision support for the treating doctor only; not a diagnosis."}
            </p>
          </Section>

          {/* 7. Investigations */}
          <Section title="Suggested investigations" icon={FlaskConical} count={investigations.length}>
            {investigations.length === 0 ? (
              <p className="text-sm text-ink-faint">No investigations suggested.</p>
            ) : (
              investigations.map((item, index) => {
                const key = `investigation:${item.test}`;
                return (
                  <div key={key} className="rounded-lg border-l-2 border-marigold bg-marigold/[0.04] p-3.5">
                    <div className="mb-1.5 flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-ink">{item.test}</span>
                      <Badge
                        variant={
                          item.priority === "immediate"
                            ? "danger"
                            : item.priority === "urgent"
                              ? "warning"
                              : "secondary"
                        }
                        size="sm"
                      >
                        {titleCase(item.priority)}
                      </Badge>
                      <AiBadge />
                    </div>
                    {item.rationale && <p className="text-xs text-ink-muted">{item.rationale}</p>}
                    {item.fasting_or_prep_required && (
                      <p className="mt-1 text-xs text-ink-faint">Prep: {item.fasting_or_prep_required}</p>
                    )}
                    <div className="mt-2.5">
                      <DecisionControls
                        itemKey={key}
                        decision={decisions[key]}
                        onDecide={decide}
                        busy={busyKey === key}
                      />
                    </div>
                  </div>
                );
              })
            )}
            {dossier?.investigations?.already_done_to_review &&
              dossier.investigations.already_done_to_review.length > 0 && (
                <div className="rounded-lg bg-mint p-3">
                  <p className="text-xs font-semibold text-pine">Already done — review reports</p>
                  <p className="mt-1 text-xs text-ink-muted">
                    {dossier.investigations.already_done_to_review.join(", ")}
                  </p>
                </div>
              )}
          </Section>

          {/* 8. Follow-up questions */}
          <Section
            title="Suggested follow-up questions"
            icon={HelpCircle}
            count={briefing?.follow_up_questions?.length ?? 0}
          >
            {!briefing?.follow_up_questions?.length ? (
              <p className="text-sm text-ink-faint">
                The intake covered the expected ground; no additional questions suggested.
              </p>
            ) : (
              briefing.follow_up_questions.map((item, index) => {
                const key = `question:${index}`;
                return (
                  <div key={key} className="rounded-lg border-l-2 border-marigold bg-marigold/[0.04] p-3.5">
                    <div className="mb-1.5 flex items-start justify-between gap-2">
                      <p className="text-sm font-medium leading-snug text-ink">
                        &ldquo;{item.question}&rdquo;
                      </p>
                      <AiBadge className="shrink-0" />
                    </div>
                    {item.why_it_matters && (
                      <p className="text-xs text-ink-muted">{item.why_it_matters}</p>
                    )}
                    {item.targets && (
                      <p className="mt-1 text-xs italic text-ink-faint">Discriminates: {item.targets}</p>
                    )}
                    <div className="mt-2.5">
                      <DecisionControls
                        itemKey={key}
                        decision={decisions[key]}
                        onDecide={decide}
                        busy={busyKey === key}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </Section>

          {/* 9. Referrals */}
          <Section title="Referral suggestions" icon={UserPlus} count={briefing?.referrals?.length ?? 0}>
            {!briefing?.referrals?.length ? (
              <p className="text-sm text-ink-faint">No referral suggested for this presentation.</p>
            ) : (
              briefing.referrals.map((item, index) => {
                const key = `referral:${item.specialty}-${index}`;
                return (
                  <div key={key} className="rounded-lg border-l-2 border-marigold bg-marigold/[0.04] p-3.5">
                    <div className="mb-1.5 flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-ink">{item.specialty}</span>
                      <Badge variant={item.urgency === "urgent" ? "danger" : "secondary"} size="sm">
                        {titleCase(item.urgency)}
                      </Badge>
                      <AiBadge />
                    </div>
                    <p className="text-xs text-ink-muted">{item.reason}</p>
                    <div className="mt-2.5">
                      <DecisionControls
                        itemKey={key}
                        decision={decisions[key]}
                        onDecide={decide}
                        busy={busyKey === key}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </Section>

          {/* 10. Patient education */}
          <Section title="Patient education suggestions" icon={GraduationCap} defaultOpen={false}>
            {!education ? (
              <p className="text-sm text-ink-faint">No education material generated.</p>
            ) : (
              <div className="space-y-3">
                <AiBadge />
                {education.understanding_your_visit && (
                  <p className="text-sm leading-relaxed text-ink">{education.understanding_your_visit}</p>
                )}
                {education.what_to_expect_at_hospital && (
                  <p className="text-sm leading-relaxed text-ink-muted">
                    {education.what_to_expect_at_hospital}
                  </p>
                )}
                {education.general_self_care && education.general_self_care.length > 0 && (
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-pine">
                      Self-care to share
                    </p>
                    <ul className="space-y-1">
                      {education.general_self_care.map((tip) => (
                        <li key={tip} className="flex gap-2 text-xs text-ink-muted">
                          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-pine/40" />
                          {tip}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {education.warning_signs_return_immediately &&
                  education.warning_signs_return_immediately.length > 0 && (
                    <div className="rounded-lg bg-clay/[0.05] p-3">
                      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-clay">
                        Tell the patient to return immediately if
                      </p>
                      <ul className="space-y-1">
                        {education.warning_signs_return_immediately.map((sign) => (
                          <li key={sign} className="flex gap-2 text-xs text-ink-muted">
                            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-clay/50" />
                            {sign}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
              </div>
            )}
          </Section>
        </div>
      )}

      <CardContent className="border-t border-border bg-mint/60 py-3.5">
        <p className="text-[11px] leading-relaxed text-ink-muted">
          {briefing?.disclaimer ??
            "AI-generated decision support. Every item must be verified by the treating doctor, who remains the final authority on this patient's care."}
        </p>
        {briefing?.errors && briefing.errors.length > 0 && (
          <p className="mt-2 text-[11px] text-clay">
            Some copilot checks could not complete ({briefing.errors.length}). The clinical record
            above is unaffected.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function AlertList({
  alerts,
  emptyText,
  decisions,
  onDecide,
  busyKey,
}: {
  alerts: MedicationAlert[];
  emptyText: string;
  decisions: Record<string, CopilotDecision>;
  onDecide: (key: string, value: "accepted" | "dismissed") => void;
  busyKey: string | null;
}) {
  if (alerts.length === 0) {
    return <p className="text-sm text-ink-faint">{emptyText}</p>;
  }
  return (
    <>
      {alerts.map((alert, index) => {
        const Icon = ALERT_ICON[alert.kind];
        const key = `alert:${alert.kind}:${alert.medicines_involved.join("+")}:${index}`;
        return (
          <motion.div
            key={key}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.16 }}
            className={cn("rounded-lg border p-3.5", SEVERITY_STYLE[alert.severity])}
          >
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  alert.severity === "serious" ? "text-clay" : "text-marigold-deep"
                )}
              />
              <span className="text-sm font-semibold text-ink">{ALERT_TITLE[alert.kind]}</span>
              <Badge variant={alert.severity === "serious" ? "danger" : "warning"} size="sm">
                {titleCase(alert.severity)}
              </Badge>
              <AiBadge source={alert.detected_by} />
            </div>
            <p className="text-xs leading-relaxed text-ink-muted">{alert.description}</p>
            {alert.suggested_action && (
              <p className="mt-1.5 text-xs font-medium text-pine">{alert.suggested_action}</p>
            )}
            {alert.medicines_involved.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {alert.medicines_involved.map((medicine) => (
                  <Badge key={medicine} variant="outline" size="sm">
                    {medicine}
                  </Badge>
                ))}
              </div>
            )}
            <div className="mt-2.5">
              <DecisionControls
                itemKey={key}
                decision={decisions[key]}
                onDecide={onDecide}
                busy={busyKey === key}
              />
            </div>
          </motion.div>
        );
      })}
    </>
  );
}
