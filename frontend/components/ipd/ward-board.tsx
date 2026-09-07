"use client";

/**
 * The ward board.
 *
 * This is the screen a ward sister has open all shift, so it is built for
 * scanning rather than reading: bed colour carries occupancy, a NEWS2 badge
 * carries risk, and the deteriorating patients are lifted out of the grid
 * entirely into a banner at the top.
 *
 * The critical band is deliberately not a darker shade of the warning band.
 * A gradient makes a scanning eye compare; a solid red block makes it stop.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { AlertTriangle, BedDouble, Droplet, RefreshCw, Users } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type {
  BedCell, Census, DeterioratingPatient, WardBoard,
} from "@/lib/ipdTypes";
import {
  BED_STATUS_STYLE, NEWS_BANDS, WARD_TYPE_LABEL, dayOfStay,
} from "@/lib/ipdTypes";
import { formatINR } from "@/lib/emrTypes";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const REFRESH_MS = 30000;

function CensusStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-pine/10 bg-white px-4 py-3">
      <p className="text-[11px] uppercase tracking-wide text-ink-faint">{label}</p>
      <p className="tabular mt-0.5 font-display text-xl font-semibold text-pine">{value}</p>
      {hint && <p className="text-[11px] text-ink-muted">{hint}</p>}
    </div>
  );
}

function BedTile({
  bed, scores, onSelect,
}: {
  bed: BedCell;
  scores: Map<string, DeterioratingPatient>;
  onSelect: (bed: BedCell) => void;
}) {
  const occupant = bed.occupant;
  const alert = occupant ? scores.get(occupant.admission_id) : undefined;
  const band = alert ? NEWS_BANDS[alert.risk] : null;

  return (
    <button
      onClick={() => onSelect(bed)}
      className={cn(
        "relative flex h-[104px] w-full flex-col rounded-xl border p-2.5 text-left transition",
        BED_STATUS_STYLE[bed.status],
        alert?.risk === "critical" && "ring-2 ring-clay"
      )}
    >
      <div className="flex items-center gap-1">
        <span className="font-display text-xs font-semibold text-pine">{bed.label}</span>
        {bed.oxygen && (
          <Droplet className="h-3 w-3 text-pine/40" aria-label="Oxygen available" />
        )}
        {band && (
          <span className={cn(
            "ml-auto rounded px-1.5 py-0.5 text-[10px] font-bold leading-none",
            band.className
          )}>
            {alert!.news2_score}
          </span>
        )}
      </div>

      {occupant ? (
        <div className="mt-1 min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium leading-tight text-ink">
            {occupant.patient_name}
          </p>
          <p className="truncate text-[11px] text-ink-muted">
            {occupant.age}
            {occupant.gender.charAt(0).toUpperCase()} · Day {dayOfStay(occupant.admitted_at)}
          </p>
          <p className="mt-0.5 truncate text-[10px] text-ink-faint">
            {occupant.diagnosis || occupant.ip_number}
          </p>
        </div>
      ) : (
        <div className="mt-1 flex flex-1 items-center justify-center">
          <span className="text-[11px] capitalize text-ink-faint">
            {bed.status === "vacant" ? "Free" : bed.status}
          </span>
        </div>
      )}
    </button>
  );
}

export function WardBoardView() {
  const [wards, setWards] = useState<WardBoard[] | null>(null);
  const [census, setCensus] = useState<Census | null>(null);
  const [alerts, setAlerts] = useState<DeterioratingPatient[]>([]);
  const [selected, setSelected] = useState<BedCell | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [board, stats, deteriorating] = await Promise.all([
        staffApi.wardBoard(),
        staffApi.ipdCensus(),
        staffApi.deterioratingPatients(),
      ]);
      setWards(board.wards);
      setCensus(stats);
      setAlerts(deteriorating.patients);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the ward board.");
    }
  }, []);

  useEffect(() => {
    void load();
    // A ward board that is thirty seconds stale is worse than useless, because
    // it looks current.
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const scores = useMemo(
    () => new Map(alerts.map((item) => [item.admission_id, item])),
    [alerts]
  );

  const critical = alerts.filter((item) => item.risk === "critical");

  return (
    <div className="space-y-5">
      {error && (
        <Card className="border-clay/30 bg-clay/5 p-4 text-sm text-clay">{error}</Card>
      )}

      {/* Deteriorating patients come out of the grid entirely. */}
      {alerts.length > 0 && (
        <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}>
          <Card className={cn(
            "border-2",
            critical.length > 0 ? "border-clay bg-clay/5" : "border-marigold bg-marigold/5"
          )}>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <AlertTriangle className={cn(
                  "h-4 w-4",
                  critical.length > 0 ? "text-clay" : "text-marigold-deep"
                )} />
                <p className="font-display text-sm font-semibold text-ink">
                  {alerts.length} patient{alerts.length === 1 ? "" : "s"} needing review
                </p>
              </div>
              <ul className="mt-3 space-y-2">
                {alerts.map((patient) => (
                  <li key={patient.admission_id}>
                    <Link
                      href={`/ipd/${patient.admission_id}`}
                      className="flex flex-wrap items-center gap-2 rounded-lg bg-white px-3 py-2 transition hover:shadow-sm"
                    >
                      <span className={cn(
                        "rounded px-2 py-0.5 text-xs font-bold",
                        NEWS_BANDS[patient.risk].className
                      )}>
                        NEWS2 {patient.news2_score}
                      </span>
                      <span className="text-sm font-medium text-ink">
                        {patient.patient_name}
                      </span>
                      <span className="text-xs text-ink-muted">
                        {patient.ward} · {patient.bed}
                      </span>
                      <span className="w-full text-xs text-ink-muted sm:ml-auto sm:w-auto">
                        {patient.response}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {census && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <CensusStat label="Occupancy"
                      value={`${census.occupancy_percent}%`}
                      hint={`${census.occupied} of ${census.total_beds} beds`} />
          <CensusStat label="Inpatients" value={String(census.current_inpatients)} />
          <CensusStat label="Free beds" value={String(census.vacant)}
                      hint={census.cleaning ? `${census.cleaning} being cleaned` : undefined} />
          <CensusStat label="Today"
                      value={`${census.admissions_today} in · ${census.discharges_today} out`} />
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-xs text-ink-faint">Refreshes automatically every 30 seconds</p>
        <Button variant="ghost" size="sm" onClick={() => void load()}>
          <RefreshCw /> Refresh
        </Button>
      </div>

      {wards === null ? (
        <div className="space-y-4">
          {[0, 1].map((index) => <Skeleton key={index} className="h-48 rounded-xl" />)}
        </div>
      ) : (
        wards.map((ward) => (
          <Card key={ward.id}>
            <CardContent className="p-4">
              <div className="mb-3 flex flex-wrap items-baseline gap-2">
                <h3 className="font-display text-sm font-semibold text-pine">{ward.name}</h3>
                <span className="rounded bg-mint px-1.5 py-0.5 text-[10px] font-medium text-pine">
                  {WARD_TYPE_LABEL[ward.ward_type]}
                </span>
                <span className="text-xs text-ink-muted">
                  {ward.occupied}/{ward.total_beds} occupied
                </span>
                <span className="ml-auto text-xs text-ink-faint">
                  {formatINR(ward.daily_rate_paise)}/day
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                {ward.beds.map((bed) => (
                  <BedTile key={bed.id} bed={bed} scores={scores} onSelect={setSelected} />
                ))}
              </div>
            </CardContent>
          </Card>
        ))
      )}

      {/* Tapping a bed: open the chart, or show it is free. */}
      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-ink/30 p-4 sm:items-center"
          onClick={() => setSelected(null)}
        >
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            onClick={(event) => event.stopPropagation()}
            className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl"
          >
            <div className="flex items-center gap-2">
              <BedDouble className="h-4 w-4 text-pine" />
              <h3 className="font-display font-semibold text-pine">{selected.label}</h3>
              <span className="ml-auto text-xs capitalize text-ink-muted">
                {selected.status}
              </span>
            </div>

            {selected.occupant ? (
              <>
                <div className="mt-3 rounded-lg bg-mint p-3">
                  <p className="font-medium text-ink">{selected.occupant.patient_name}</p>
                  <p className="text-xs text-ink-muted">
                    {selected.occupant.uhid} · {selected.occupant.age} yrs ·{" "}
                    {selected.occupant.gender}
                  </p>
                  <p className="mt-1 text-xs text-ink-muted">
                    {selected.occupant.ip_number} · Day{" "}
                    {dayOfStay(selected.occupant.admitted_at)} · under{" "}
                    {selected.occupant.doctor}
                  </p>
                  {selected.occupant.diagnosis && (
                    <p className="mt-1 text-sm text-ink">{selected.occupant.diagnosis}</p>
                  )}
                </div>
                <Link href={`/ipd/${selected.occupant.admission_id}`}>
                  <Button className="mt-4 w-full">Open chart</Button>
                </Link>
              </>
            ) : (
              <>
                <p className="mt-3 text-sm text-ink-muted">
                  {selected.status === "vacant"
                    ? "This bed is free and can be assigned."
                    : `This bed is ${selected.status} and cannot be assigned yet.`}
                </p>
                {selected.status === "vacant" && (
                  <Link href={`/ipd/admit?bed=${selected.id}`}>
                    <Button className="mt-4 w-full">
                      <Users /> Admit a patient here
                    </Button>
                  </Link>
                )}
              </>
            )}
          </motion.div>
        </div>
      )}
    </div>
  );
}
