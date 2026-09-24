"use client";

/**
 * Medicines, written on the Visit Pad itself.
 *
 * There is no separate prescription screen any more: what is written here is
 * what signing the pad issues. Two lists are kept apart on purpose — what the
 * doctor has accepted, and what is merely suggested. A suggestion is never
 * prescribed, never printed and never ordered until it is tapped across, so a
 * drug the dictation misheard cannot reach the patient by inattention.
 */
import { useEffect, useRef, useState } from "react";
import { Loader2, Mic, MicOff, Plus, Sparkles, Trash2 } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useDictation } from "@/lib/hooks/useDictation";
import type { PadMedicine } from "@/lib/types/pad";
import { FREQUENCY_OPTIONS, TIMING_OPTIONS } from "@/lib/types/prescriptions";
import type { FormularyMedicine } from "@/lib/types/prescriptions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

/** What a line reads as on one line, for a suggestion chip. */
export function medicineSummary(row: PadMedicine): string {
  const head = [row.name, row.strength, row.form].filter(Boolean).join(" ");
  const rest = [row.dosage, row.frequency_text ?? row.frequency_code, row.duration, row.timing]
    .filter(Boolean)
    .join(", ");
  return rest ? `${head} — ${rest}` : head;
}

function Row({
  row,
  editable,
  onChange,
  onRemove,
}: {
  row: PadMedicine;
  editable: boolean;
  onChange: (row: PadMedicine) => void;
  onRemove: () => void;
}) {
  const [matches, setMatches] = useState<FormularyMedicine[]>([]);
  const [looking, setLooking] = useState(false);

  function search(name: string) {
    onChange({ ...row, name, source: row.source ?? "manual" });
    if (name.trim().length < 2) {
      setMatches([]);
      return;
    }
    staffApi
      .formulary({ q: name.trim(), limit: 6 })
      .then((result) => setMatches(result.items))
      .catch(() => setMatches([]));
  }

  function take(medicine: FormularyMedicine) {
    onChange({
      ...row,
      name: medicine.name,
      formulary_code: medicine.code,
      generic: medicine.ingredients.join(", "),
      form: row.form || medicine.form,
      strength:
        row.strength || (medicine.strengths.length === 1 ? medicine.strengths[0] : row.strength),
      frequency_text: row.frequency_text || medicine.default_frequency,
      duration: row.duration || medicine.default_duration,
      timing: row.timing || medicine.default_timing,
      source: "catalog",
    });
    setMatches([]);
    setLooking(false);
  }

  if (!editable) {
    return (
      <li className="text-sm text-ink">
        {medicineSummary(row)}
        {row.instructions && (
          <span className="block text-xs text-ink-muted">{row.instructions}</span>
        )}
      </li>
    );
  }

  return (
    <li className="rounded-lg border border-border bg-white p-2">
      <div className="flex items-start gap-2">
        <div className="relative min-w-0 flex-1">
          <Input
            className="h-8 text-sm"
            value={row.name}
            placeholder="Medicine"
            aria-label="Medicine"
            onFocus={() => setLooking(true)}
            onChange={(event) => search(event.target.value)}
          />
          {looking && matches.length > 0 && (
            <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-border bg-white shadow-lg">
              {matches.map((medicine) => (
                <li key={medicine.code}>
                  <button
                    type="button"
                    className="block w-full px-2.5 py-1.5 text-left text-xs hover:bg-mint"
                    onClick={() => take(medicine)}
                  >
                    <span className="font-medium text-ink">{medicine.name}</span>{" "}
                    <span className="text-ink-muted">
                      {[medicine.form, medicine.ingredients.join(", ")].filter(Boolean).join(" · ")}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {/* A medicine typed rather than picked is prescribed exactly as
              typed, so it is worth saying that nothing checked the spelling. */}
          {!row.formulary_code && row.name.trim().length > 1 && (
            <p className="mt-0.5 text-[11px] text-marigold-deep">Not in the formulary</p>
          )}
        </div>
        <button
          type="button"
          aria-label={`Remove ${row.name || "this medicine"}`}
          className="rounded p-1 text-ink-faint hover:text-clay"
          onClick={onRemove}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="mt-1.5 flex flex-wrap gap-1.5">
        <Input
          className="h-7 w-20 text-xs"
          value={row.strength ?? ""}
          placeholder="Strength"
          aria-label="Strength"
          onChange={(event) => onChange({ ...row, strength: event.target.value })}
        />
        <Input
          className="h-7 w-16 text-xs"
          value={row.dosage ?? ""}
          placeholder="Dose"
          aria-label="Dose"
          onChange={(event) => onChange({ ...row, dosage: event.target.value })}
        />
        <select
          className="h-7 rounded-md border border-input bg-white px-1.5 text-xs text-ink"
          value={row.frequency_text ?? ""}
          aria-label="How often"
          onChange={(event) => onChange({ ...row, frequency_text: event.target.value })}
        >
          <option value="">How often</option>
          {FREQUENCY_OPTIONS.map((option) => (
            <option key={option.code} value={option.label}>
              {option.label}
            </option>
          ))}
        </select>
        <Input
          className="h-7 w-24 text-xs"
          value={row.duration ?? ""}
          placeholder="For how long"
          aria-label="For how long"
          onChange={(event) => onChange({ ...row, duration: event.target.value })}
        />
        <select
          className="h-7 rounded-md border border-input bg-white px-1.5 text-xs text-ink"
          value={row.timing ?? ""}
          aria-label="When"
          onChange={(event) => onChange({ ...row, timing: event.target.value })}
        >
          <option value="">When</option>
          {TIMING_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <Input
          className="h-7 min-w-[8rem] flex-1 text-xs"
          value={row.instructions ?? ""}
          placeholder="Instructions for the patient"
          aria-label="Instructions"
          onChange={(event) => onChange({ ...row, instructions: event.target.value })}
        />
      </div>
    </li>
  );
}

export function MedicineSection({
  medicines,
  suggestions,
  editable,
  patientId,
  onChange,
}: {
  medicines: PadMedicine[];
  suggestions: PadMedicine[];
  editable: boolean;
  patientId?: string;
  onChange: (next: { medicines: PadMedicine[]; suggestions: PadMedicine[] }) => void;
}) {
  const toast = useToast();
  const [reading, setReading] = useState(false);
  const dictation = useDictation();
  // What has already been sent to the parser, so a long dictation is parsed
  // in pieces as the doctor speaks rather than re-parsed from the beginning.
  const parsedUpTo = useRef(0);

  const set = (next: Partial<{ medicines: PadMedicine[]; suggestions: PadMedicine[] }>) =>
    onChange({ medicines, suggestions, ...next });

  const accept = (row: PadMedicine) =>
    set({
      medicines: [...medicines, row],
      suggestions: suggestions.filter((item) => item !== row),
    });

  /**
   * Turn spoken words into offered lines.
   *
   * Offered, never prescribed: the parser is good but it is listening to a
   * busy room, and "Amlodipine" and "Amlodipine besylate" are one syllable
   * apart from something the patient should not take. Everything lands in the
   * suggestion strip for the doctor to accept.
   */
  async function parse(words: string, quiet = false) {
    if (!words.trim()) {
      if (!quiet) {
        toast.notify({
          tone: "info",
          title: "Nothing said yet",
          description: "Dictate the medicines, or add them by hand.",
        });
      }
      return;
    }
    setReading(true);
    try {
      const parsed = await staffApi.parseDictation(words, patientId);
      const already = new Set(
        [...medicines, ...suggestions].map((row) => row.name.toLowerCase())
      );
      const heard: PadMedicine[] = parsed.medicines
        .filter((row) => row.name && !already.has(row.name.toLowerCase()))
        .map((row) => ({
          name: row.name,
          formulary_code: row.formulary_code ?? null,
          generic: row.generic ?? null,
          form: row.form ?? null,
          strength: row.strength ?? null,
          dosage: row.dosage ?? null,
          frequency_code: row.frequency_code ?? null,
          frequency_text: row.frequency_text ?? null,
          duration: row.duration ?? null,
          timing: row.timing ?? null,
          route: row.route ?? null,
          instructions: row.instructions ?? null,
          source: "dictated",
        }));
      if (heard.length === 0) {
        if (!quiet) {
          toast.notify({
            tone: "info",
            title: "No medicines found",
            description: "Nothing said read as a prescription.",
          });
        }
      } else {
        set({ suggestions: [...suggestions, ...heard] });
      }
    } catch {
      toast.error("Could not read the dictation", "Add the medicines by hand.");
    } finally {
      setReading(false);
    }
  }

  // Parse each finished sentence while the doctor keeps speaking, so the
  // lines appear as they are said instead of all at once at the end.
  useEffect(() => {
    if (!dictation.listening) return;
    const fresh = dictation.transcript.slice(parsedUpTo.current);
    if (fresh.trim().length < 12) return;
    parsedUpTo.current = dictation.transcript.length;
    void parse(fresh, true);
    // parse closes over the current rows on purpose; re-running on every
    // keystroke elsewhere would re-send the same words.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dictation.transcript, dictation.listening]);

  async function toggleDictation() {
    if (dictation.listening || dictation.state === "connecting") {
      await dictation.stop();
      // Whatever was said after the last sentence break still counts.
      const tail = dictation.transcript.slice(parsedUpTo.current);
      parsedUpTo.current = dictation.transcript.length;
      if (tail.trim()) await parse(tail, true);
      return;
    }
    parsedUpTo.current = 0;
    dictation.reset();
    await dictation.start();
  }

  return (
    <div className="space-y-2">
      <ul className="space-y-1.5">
        {medicines.map((row, index) => (
          <Row
            key={index}
            row={row}
            editable={editable}
            onChange={(next) =>
              set({ medicines: medicines.map((item, at) => (at === index ? next : item)) })
            }
            onRemove={() => set({ medicines: medicines.filter((_, at) => at !== index) })}
          />
        ))}
      </ul>

      {medicines.length === 0 && !editable && (
        <p className="text-sm text-ink-faint">No medicines prescribed.</p>
      )}

      {editable && (dictation.listening || dictation.error) && (
        <p className="text-[11px] text-ink-muted">
          {dictation.error ? (
            <span className="text-clay">{dictation.error}</span>
          ) : (
            <>
              <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-clay align-middle" />
              Listening — {dictation.transcript.trim() || "say the medicine, dose and duration"}
            </>
          )}
        </p>
      )}

      {editable && suggestions.length > 0 && (
        <div className="rounded-lg border border-dashed border-pine/40 bg-pine/5 p-2">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <p className="flex items-center gap-1 text-[11px] font-medium text-pine">
              <Sparkles className="h-3 w-3" />
              Heard in the consultation — tap to prescribe
            </p>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 text-[11px]"
              onClick={() => set({ medicines: [...medicines, ...suggestions], suggestions: [] })}
            >
              Add all
            </Button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {suggestions.map((row, index) => (
              <button
                key={index}
                type="button"
                className="rounded-full border border-pine/30 bg-white px-2.5 py-1 text-xs text-ink hover:border-pine hover:bg-mint"
                onClick={() => accept(row)}
              >
                <Plus className="mr-1 inline h-3 w-3 text-pine" />
                {medicineSummary(row)}
              </button>
            ))}
          </div>
        </div>
      )}

      {editable && (
        <div className="flex flex-wrap gap-1.5">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() =>
              set({ medicines: [...medicines, { name: "", source: "manual" }] })
            }
          >
            <Plus className="mr-1 h-3 w-3" />
            Add a medicine
          </Button>
          <Button
            size="sm"
            variant={dictation.listening ? "default" : "ghost"}
            className="h-7 text-xs"
            onClick={() => void toggleDictation()}
          >
            {dictation.state === "connecting" ? (
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
            ) : dictation.listening ? (
              <MicOff className="mr-1 h-3 w-3" />
            ) : (
              <Mic className="mr-1 h-3 w-3" />
            )}
            {dictation.listening ? "Stop dictating" : "Dictate medicines"}
          </Button>

        </div>
      )}
    </div>
  );
}
