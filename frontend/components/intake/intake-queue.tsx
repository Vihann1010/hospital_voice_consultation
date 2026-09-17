"use client";

/**
 * The voice intake terminal.
 *
 * This is the second half of the counter handover. Reception registers and
 * bills; this screen picks the patient up from that record. Nothing is
 * re-typed — asking a patient for their name and phone a second time is how
 * the same person ends up in the database twice, with their history split
 * across both copies.
 *
 * Starting a session opens the consultation workspace for the operator, so the
 * confirmation step matters: tapping the wrong row would put someone else's
 * name on this consultation.
 */
import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Clock, Loader2, Mic, RefreshCw, Users } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { ConsultationDetail, ConsultationListItem, Department } from "@/lib/types/core";
import { formatDate } from "@/lib/format";
import type { QueuedPatient } from "@/lib/types/emr";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { LiveIntakeWorkspace } from "@/components/intake/live-intake-workspace";

const REFRESH_MS = 15000;

function waitedFor(registeredAt: string): string {
  const minutes = Math.max(
    0,
    Math.round((Date.now() - new Date(registeredAt).getTime()) / 60000)
  );
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} hr ${minutes % 60} min`;
}

export function IntakeQueue() {
  const toast = useToast();

  const [queue, setQueue] = useState<QueuedPatient[] | null>(null);
  const [completed, setCompleted] = useState<ConsultationListItem[] | null>(null);
  const [department, setDepartment] = useState<Department | "all">("all");
  const [confirming, setConfirming] = useState<QueuedPatient | null>(null);
  const [starting, setStarting] = useState(false);
  const [activeSession, setActiveSession] = useState<{
    patient: QueuedPatient;
    consultationId: string;
    token: string | null;
    consultation?: ConsultationDetail | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await staffApi.intakeQueue(
        department === "all" ? {} : { department }
      );
      setQueue(result.patients);
      const completedResult = await staffApi.consultations({
        status: "completed",
        visit_type: "new",
        department: department === "all" ? undefined : department,
        limit: 50,
      });
      setCompleted(completedResult.items);
      setError(null);
    } catch (err) {
      // Said out loud rather than swallowed: an empty queue and a failed
      // request look identical, and only one of them means "wait".
      setError(err instanceof Error ? err.message : "Could not load the queue.");
    }
  }, [department]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  async function beginIntake(entry: QueuedPatient) {
    setStarting(true);
    try {
      const session = await staffApi.startConsultationFromVisit(entry.visit_id);
      // The session page reads its token from sessionStorage, so it is written
      // before navigating rather than passed in the URL where it would end up
      // in browser history and server logs.
      sessionStorage.setItem(
        `consult:${session.consultation_id}`,
        session.session_token
      );
      setActiveSession({
        patient: entry,
        consultationId: session.consultation_id,
        token: session.session_token,
      });
      setConfirming(null);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not start the consultation.";
      toast.error("Could not start", message);
      setConfirming(null);
      void load();
    } finally {
      setStarting(false);
    }
  }

  async function openCompleted(entry: ConsultationListItem) {
    try {
      const detail = await staffApi.consultation(entry.id);
      setActiveSession({
        consultationId: entry.id,
        token: null,
        consultation: detail,
        patient: {
          visit_id: entry.id,
          visit_number: entry.id,
          token_number: null,
          department: entry.department,
          doctor_name: "",
          visit_type: "new",
          registered_at: entry.started_at,
          patient: {
            id: entry.patient?.id ?? "",
            uhid: null,
            name: entry.patient?.name ?? "Registered patient",
            age: entry.patient?.age ?? 0,
            gender: entry.patient?.gender ?? "other",
            phone_number: entry.patient?.phone_number ?? "",
          },
        },
      });
    } catch (err) {
      toast.error(
        "Could not open consultation",
        err instanceof Error ? err.message : "Please try again."
      );
    }
  }

  if (activeSession) {
    return (
      <LiveIntakeWorkspace
        patient={activeSession.patient}
        consultationId={activeSession.consultationId}
        token={activeSession.token}
        consultation={activeSession.consultation}
        onRestartSession={(session) => {
          setActiveSession((current) => current ? {
            ...current,
            consultationId: session.consultation_id,
            token: session.session_token,
            consultation: null,
          } : current);
        }}
        onBack={() => {
          setActiveSession(null);
          void load();
        }}
      />
    );
  }

  return (
    <div className="space-y-5">
      {error && (
        <Card className="border-clay/30 bg-clay/5 p-4 text-sm text-clay">{error}</Card>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {([
          { value: "all", label: "Everyone" },
          { value: "orthopedics", label: "Orthopedics" },
          { value: "gynecology", label: "Gynecology" },
        ] as const).map((option) => (
          <button
            key={option.value}
            onClick={() => setDepartment(option.value)}
            className={cn(
              "rounded-lg border px-3 py-1.5 text-sm font-medium transition",
              department === option.value
                ? "border-pine bg-pine text-mint"
                : "border-border bg-white text-ink-muted hover:bg-mint"
            )}
          >
            {option.label}
          </button>
        ))}
        <Button variant="ghost" size="sm" className="ml-auto" onClick={() => void load()}>
          <RefreshCw /> Refresh
        </Button>
      </div>

      {queue === null && !error ? (
        <div className="space-y-3">
          {[0, 1, 2].map((index) => <Skeleton key={index} className="h-20 rounded-xl" />)}
        </div>
      ) : queue && queue.length === 0 ? (
        <Card>
          <CardContent className="py-14 text-center">
            <Users className="mx-auto h-8 w-8 text-pine/25" />
            <p className="mt-3 font-display text-sm font-semibold text-pine">
              Nobody is waiting
            </p>
            <p className="mt-1 text-sm text-ink-muted">
              Patients appear here as soon as reception registers them.
            </p>
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-2.5">
          <AnimatePresence initial={false}>
            {(queue ?? []).map((entry) => (
              <motion.li
                key={entry.visit_id}
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                <button
                  onClick={() => setConfirming(entry)}
                  className="flex w-full items-center gap-4 rounded-xl border border-pine/10 bg-white p-4 text-left transition hover:border-pine/30 hover:shadow-sm"
                >
                  <span className="tabular flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-marigold/20 font-display text-lg font-semibold text-marigold-deep">
                    {entry.token_number ?? "—"}
                  </span>

                  <div className="min-w-0 flex-1">
                    <p className="truncate font-display text-base font-semibold text-pine">
                      {entry.patient.name}
                    </p>
                    <p className="truncate text-sm text-ink-muted">
                      {entry.patient.age} yrs · {entry.patient.gender} ·{" "}
                      {entry.patient.uhid}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-ink-faint">
                      {entry.department === "orthopedics" ? "Orthopedics" : "Gynecology"}
                      {entry.doctor_name ? ` · ${entry.doctor_name}` : ""}
                    </p>
                  </div>

                  <div className="shrink-0 text-right">
                    <span className="flex items-center gap-1 text-xs text-ink-faint">
                      <Clock className="h-3 w-3" />
                      {waitedFor(entry.registered_at)}
                    </span>
                    <span className="mt-1 inline-flex items-center gap-1 rounded-lg bg-pine px-3 py-1.5 text-xs font-semibold text-mint">
                      <Mic className="h-3 w-3" /> Start
                    </span>
                  </div>
                </button>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}

      <section className="space-y-3">
        <div>
          <h2 className="font-display text-lg font-semibold text-pine">Completed consultations</h2>
          <p className="text-sm text-ink-muted">Patients who have completed voice intake.</p>
        </div>
        {completed === null ? (
          <Skeleton className="h-20 rounded-xl" />
        ) : completed.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-ink-muted">
              No completed consultations yet.
            </CardContent>
          </Card>
        ) : (
          <ul className="space-y-2.5">
            {completed.map((entry) => (
              <li key={entry.id}>
                <button
                  type="button"
                  onClick={() => void openCompleted(entry)}
                  className="group flex w-full items-center gap-4 rounded-xl border border-pine/10 bg-white p-4 text-left transition hover:border-pine/30 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-pine/30"
                  aria-label={`View completed consultation for ${entry.patient?.name ?? "registered patient"}`}
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-mint text-sm font-semibold text-pine">
                    {entry.patient?.name.slice(0, 1).toUpperCase() ?? "?"}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-display text-base font-semibold text-pine">
                      {entry.patient?.name ?? "Registered patient"}
                    </p>
                    <p className="truncate text-sm text-ink-muted">
                      {entry.patient?.phone_number ?? ""} · {entry.department === "orthopedics" ? "Orthopedics" : "Gynecology"}
                    </p>
                  </div>
                  <p className="hidden text-right text-xs text-ink-faint sm:block">
                    Completed {formatDate(entry.ended_at ?? entry.started_at)}
                  </p>
                  <span className="flex shrink-0 items-center gap-1 text-xs font-semibold text-pine">
                    View details <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Confirmation: the next thing that happens is handing over the tablet. */}
      {confirming && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-4 sm:items-center"
          onClick={() => !starting && setConfirming(null)}
        >
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            onClick={(event) => event.stopPropagation()}
            className="w-full max-w-sm rounded-2xl bg-white p-6 text-center shadow-xl"
          >
            <p className="text-sm text-ink-muted">Starting voice intake for</p>
            <p className="mt-1 font-display text-xl font-semibold text-pine">
              {confirming.patient.name}
            </p>
            <p className="mt-0.5 text-sm text-ink-muted">
              {confirming.patient.age} yrs · {confirming.patient.gender} ·{" "}
              {confirming.patient.uhid}
            </p>
            <p className="mt-3 rounded-lg bg-mint px-3 py-2 text-xs text-ink-muted">
              The assistant will greet the patient while you record the clinical
              context, vitals, and live transcript on this screen.
            </p>

            <div className="mt-5 flex gap-2">
              <Button
                variant="outline"
                className="flex-1"
                disabled={starting}
                onClick={() => setConfirming(null)}
              >
                Cancel
              </Button>
              <Button
                className="flex-1"
                disabled={starting}
                onClick={() => void beginIntake(confirming)}
              >
                {starting ? <Loader2 className="animate-spin" /> : <Mic />}
                Begin
              </Button>
            </div>
          </motion.div>
        </div>
      )}

    </div>
  );
}
