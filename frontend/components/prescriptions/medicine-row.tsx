"use client";

/** One editable medicine line, with formulary autocomplete. */
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Sparkles, X } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { FormularyMedicine, MedicineRow } from "@/lib/types/prescriptions";
import { FREQUENCY_OPTIONS, TIMING_OPTIONS } from "@/lib/types/prescriptions";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function MedicineRowEditor({
  row,
  index,
  onChange,
  onRemove,
}: {
  row: MedicineRow;
  index: number;
  onChange: (row: MedicineRow) => void;
  onRemove: () => void;
}) {
  const [suggestions, setSuggestions] = useState<FormularyMedicine[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open || !row.name || row.name.length < 2) {
      setSuggestions([]);
      return;
    }
    const timer = setTimeout(() => {
      staffApi
        .formulary({ q: row.name, limit: 8 })
        .then((result) => setSuggestions(result.items))
        .catch(() => setSuggestions([]));
    }, 150);
    return () => clearTimeout(timer);
  }, [row.name, open]);

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function applySuggestion(medicine: FormularyMedicine) {
    onChange({
      ...row,
      name: medicine.name,
      formulary_code: medicine.code,
      generic: medicine.ingredients.join(", "),
      form: row.form || medicine.form,
      strength: row.strength || (medicine.strengths.length === 1 ? medicine.strengths[0] : row.strength),
      frequency_text: row.frequency_text || medicine.default_frequency || null,
      duration: row.duration || medicine.default_duration || null,
      timing: row.timing || medicine.default_timing || null,
      source: "catalog",
      unmatched: false,
      substituted: false,
      warnings: medicine.note ? [medicine.note] : [],
    });
    setOpen(false);
    setSuggestions([]);
  }

  const needsAttention = row.unmatched || row.substituted || (row.confidence ?? 1) < 0.6;

  return (
    <div
      className={cn(
        "rounded-lg border p-3 transition",
        needsAttention ? "border-marigold/50 bg-marigold/[0.04]" : "border-border bg-white"
      )}
    >
      <div className="flex items-start gap-2">
        <div className="mt-2 flex w-5 shrink-0 items-center justify-center">
          <span className="tabular text-xs font-bold text-marigold-deep">{index + 1}</span>
        </div>

        <div className="min-w-0 flex-1 space-y-2">
          {/* Name with autocomplete */}
          <div className="relative" ref={containerRef}>
            <Input
              value={row.name}
              onChange={(event) => {
                onChange({ ...row, name: event.target.value, source: row.source === "catalog" ? "manual" : row.source });
                setOpen(true);
                setHighlight(0);
              }}
              onFocus={() => setOpen(true)}
              placeholder="Medicine name"
              className="h-9 font-medium"
              aria-label={`Medicine ${index + 1} name`}
            />
            {open && suggestions.length > 0 && (
              <ul className="absolute z-30 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-border bg-white py-1 shadow-lift">
                {suggestions.map((medicine, position) => (
                  <li key={medicine.code}>
                    <button
                      type="button"
                      onMouseEnter={() => setHighlight(position)}
                      onClick={() => applySuggestion(medicine)}
                      className={cn(
                        "flex w-full items-start gap-2 px-3 py-2 text-left transition",
                        position === highlight ? "bg-mint" : "hover:bg-mint/60"
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-ink">
                          {medicine.form} {medicine.name}
                          {medicine.strengths.length > 0 && (
                            <span className="ml-1 text-xs font-normal text-ink-muted">
                              {medicine.strengths.join(" / ")}
                            </span>
                          )}
                        </p>
                        <p className="text-[11px] text-ink-faint">
                          {medicine.ingredients.join(", ")} · {medicine.category}
                        </p>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Structured fields */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Input
              value={row.strength ?? ""}
              onChange={(event) => onChange({ ...row, strength: event.target.value })}
              placeholder="Strength"
              className="h-8 text-xs"
              aria-label="Strength"
            />
            <select
              value={row.frequency_code ?? ""}
              onChange={(event) => {
                const option = FREQUENCY_OPTIONS.find((o) => o.code === event.target.value);
                onChange({
                  ...row,
                  frequency_code: event.target.value || null,
                  frequency_text: option?.label ?? row.frequency_text ?? null,
                });
              }}
              className="field-input h-8 py-0 text-xs"
              aria-label="Frequency"
            >
              <option value="">{row.frequency_text || "Frequency"}</option>
              {FREQUENCY_OPTIONS.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>
            <Input
              value={row.duration ?? ""}
              onChange={(event) =>
                // Typing a duration takes ownership of it: a later change to
                // the follow-up interval must not overwrite the doctor.
                onChange({
                  ...row,
                  duration: event.target.value,
                  durationFromFollowUp: false,
                })
              }
              placeholder="Duration"
              className="h-8 text-xs"
              aria-label="Duration"
            />
            <select
              value={row.timing ?? ""}
              onChange={(event) => onChange({ ...row, timing: event.target.value || null })}
              className="field-input h-8 py-0 text-xs"
              aria-label="Timing"
            >
              <option value="">Timing</option>
              {TIMING_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>

          <Input
            value={row.instructions ?? ""}
            onChange={(event) => onChange({ ...row, instructions: event.target.value })}
            placeholder="Extra instruction for the patient (optional)"
            className="h-8 text-xs"
            aria-label="Instructions"
          />

          {/* Provenance and warnings */}
          <div className="flex flex-wrap items-center gap-1.5">
            {row.source === "dictated" && (
              <Badge variant="ai" size="sm" className="gap-1">
                <Sparkles className="h-3 w-3" /> From dictation
              </Badge>
            )}
            {row.source === "template" && (
              <Badge variant="ai" size="sm" className="gap-1">
                <Sparkles className="h-3 w-3" /> Disease template
              </Badge>
            )}
            {row.formulary_code && !row.substituted && (
              <Badge variant="success" size="sm" className="gap-1">
                <Check className="h-3 w-3" /> {row.generic || "In formulary"}
              </Badge>
            )}
            {row.unmatched && (
              <Badge variant="warning" size="sm" className="gap-1">
                <AlertTriangle className="h-3 w-3" /> Not in formulary
              </Badge>
            )}
            {(row.warnings ?? []).map((warning) => (
              <span key={warning} className="text-[11px] text-marigold-deep">
                {warning}
              </span>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={onRemove}
          className="mt-1 shrink-0 rounded p-1 text-ink-faint transition hover:bg-clay/10 hover:text-clay"
          aria-label={`Remove medicine ${index + 1}`}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
