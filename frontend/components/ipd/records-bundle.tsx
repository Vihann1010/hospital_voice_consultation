"use client";

/**
 * The records file for an admission.
 *
 * Every document the hospital holds for the stay, in the order the records
 * room files it, with what is missing said plainly at the top. Unsigned
 * documents start unticked. Building the file runs on the server and shows
 * its progress document by document; the finished file opens with a cover
 * sheet and a contents page giving each document's page.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, FileStack, Loader2 } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { BundleJob, ChecklistItem, RecordsChecklist } from "@/lib/types/records";
import { openBlob } from "@/lib/types/records";
import { formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const ALWAYS = new Set(["cover", "vitals", "mar"]);

function outside(item: ChecklistItem, from: string, to: string): boolean {
  if (ALWAYS.has(item.kind) || !item.on) return false;
  return Boolean((from && item.on < from) || (to && item.on > to));
}

export function RecordsBundle({ admissionId }: { admissionId: string }) {
  const [checklist, setChecklist] = useState<RecordsChecklist | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [job, setJob] = useState<BundleJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await staffApi.recordsChecklist(admissionId);
      setChecklist(result);
      setChosen(new Set(result.items.filter((item) => item.included).map((item) => item.key)));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The checklist could not be loaded.");
    }
  }, [admissionId]);

  useEffect(() => {
    void load();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [load]);

  const sections = useMemo(() => {
    const grouped = new Map<string, ChecklistItem[]>();
    for (const item of checklist?.items ?? []) {
      grouped.set(item.section, [...(grouped.get(item.section) ?? []), item]);
    }
    return [...grouped.entries()];
  }, [checklist]);

  function toggle(key: string) {
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function follow(jobId: string) {
    try {
      const state = await staffApi.recordsJob(jobId);
      setJob(state);
      if (state.status === "running") timer.current = setTimeout(() => void follow(jobId), 700);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lost track of the records file.");
    }
  }

  async function build() {
    setError(null);
    if (from && to && to < from) return setError("The start date is after the end date.");
    try {
      const started = await staffApi.buildRecords(admissionId, {
        items: [...chosen],
        date_from: from || undefined,
        date_to: to || undefined,
      });
      setJob(started);
      void follow(started.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The records file could not be started.");
    }
  }

  async function open() {
    if (!job) return;
    setOpening(true);
    try {
      openBlob(await staffApi.recordsFile(job.job_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The records file could not be opened.");
    } finally {
      setOpening(false);
    }
  }

  if (!checklist) {
    return error ? <p className="text-sm text-clay">{error}</p> : <Skeleton className="h-64 w-full rounded-xl" />;
  }

  const running = job?.status === "running";
  const percent = job && job.total ? Math.round((job.done / job.total) * 100) : 0;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center gap-2 pb-2">
          <CardTitle className="mr-auto flex items-center gap-2"><FileStack className="h-4 w-4" /> Records file</CardTitle>
          <Button size="sm" variant="ghost" onClick={() => setChosen(new Set(checklist.items.map((i) => i.key)))}>
            Tick all
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setChosen(new Set(["cover"]))}>Clear</Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {checklist.missing.length > 0 && (
            <div className="rounded-md border border-marigold/40 bg-marigold/10 p-3 text-sm text-marigold-deep">
              <p className="mb-1 flex items-center gap-1.5 font-medium"><AlertTriangle className="h-4 w-4" /> Missing from the record</p>
              <ul className="list-disc space-y-0.5 pl-5">
                {checklist.missing.map((line) => <li key={line}>{line}</li>)}
              </ul>
            </div>
          )}
          {sections.map(([section, items]) => (
            <div key={section}>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-faint">{section}</p>
              <ul className="divide-y divide-border rounded-lg border border-border">
                {items.map((item) => {
                  const dimmed = outside(item, from, to);
                  return (
                    <li key={item.key} className={cn("flex items-start gap-2 px-3 py-2", dimmed && "opacity-50")}>
                      <input type="checkbox" className="mt-1" checked={chosen.has(item.key)}
                             disabled={item.key === "cover"} onChange={() => toggle(item.key)} />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-ink">{item.title}</p>
                        <p className="text-xs text-ink-muted">
                          {item.on ? formatDate(item.on) : ""}
                          {item.status === "draft" && <span className="ml-1 text-marigold-deep">· draft</span>}
                          {dimmed && <span className="ml-1">· outside the chosen dates</span>}
                        </p>
                        {item.note && <p className="text-xs text-marigold-deep">{item.note}</p>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="h-fit">
        <CardHeader className="pb-2"><CardTitle>Build the file</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1 text-xs text-ink-muted">
              From
              <Input type="date" value={from} min={checklist.admission.admitted_on ?? undefined}
                     onChange={(event) => setFrom(event.target.value)} />
            </label>
            <label className="space-y-1 text-xs text-ink-muted">
              To
              <Input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
            </label>
          </div>
          <p className="text-xs text-ink-faint">
            Leave the dates empty for the whole stay. The cover sheet is always included; charts are cut to the dates.
          </p>
          <Button className="w-full" disabled={running || chosen.size === 0} onClick={() => void build()}>
            {running && <Loader2 className="h-4 w-4 animate-spin" />} Build records file ({chosen.size})
          </Button>
          {job && (
            <div className="space-y-2">
              <div className="h-2 overflow-hidden rounded-full bg-mint">
                <div className="h-full bg-pine transition-all" style={{ width: `${job.status === "done" ? 100 : percent}%` }} />
              </div>
              <p className="text-xs text-ink-muted">
                {job.status === "running"
                  ? `${job.done} of ${job.total} · ${job.current || "starting"}`
                  : job.status === "done"
                    ? `Ready — ${job.pages} pages`
                    : job.error}
              </p>
              {job.status === "done" && (
                <Button className="w-full" variant="outline" disabled={opening} onClick={() => void open()}>
                  {opening && <Loader2 className="h-4 w-4 animate-spin" />} Open records file
                </Button>
              )}
              {job.skipped.length > 0 && (
                <div className="text-xs text-ink-muted">
                  <p className="font-medium">Left out</p>
                  <ul className="list-disc pl-4">
                    {job.skipped.map((item) => <li key={item.title}>{item.title} — {item.reason}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
          {error && <p className="text-sm text-clay">{error}</p>}
        </CardContent>
      </Card>
    </div>
  );
}
