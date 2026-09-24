"use client";

/**
 * The Visit Pad: where the doctor writes the visit.
 *
 * It opens already half-written. The intake conversation has drafted the
 * history, red flags, differentials and investigations, each marked as AI, so
 * the doctor's job is to correct and complete rather than to start from a
 * blank page. Everything else follows the old system's habits, because they
 * are this staff's muscle memory:
 *
 *   Copy previous visit   the patient's own diagnosis and standing advice
 *   Load template         the same content for many patients
 *   Save as template      turn this pad into one
 *
 * Three rules the screen enforces rather than hopes for:
 *
 * * Nothing is lost. Typing autosaves; switching tab or closing the page
 *   flushes first; a save that would overwrite a colleague's newer changes is
 *   refused and said so, not silently merged.
 * * A signed document is read-only. Correcting it starts a new version with a
 *   written reason, and the original stays readable.
 * * What prints is visible before printing — every section shows whether it
 *   will appear on the patient's copy.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BookmarkPlus,
  BookOpen,
  CheckCircle2,
  Copy,
  Eye,
  EyeOff,
  ListOrdered,
  Loader2,
  PenLine,
  Plus,
  Printer,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { ApiError, staffApi } from "@/lib/staffApi";
import { getToken } from "@/lib/auth";
import type {
  FieldSpec,
  FieldValue,
  PadDocument,
  PadInvestigation,
  PadMedicine,
  PadTemplate,
  SectionOrigin,
  SectionSpec,
  SectionValue,
} from "@/lib/types/pad";
import { formatDateTime, formatTime } from "@/lib/format";
import { PhraseInput } from "@/components/pad/phrase-input";
import { useShortcut } from "@/components/keyboard/keyboard-provider";
import { AiBadge } from "@/components/dashboard/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ReasonDialog, type ReasonRequest } from "@/components/ui/reason-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { MedicineSection } from "@/components/pad/medicine-section";
import { InvestigationSection } from "@/components/pad/investigation-section";
import type { SafetyAlert } from "@/lib/types/prescriptions";
import { cn } from "@/lib/utils";

type SaveState = "idle" | "pending" | "saving" | "saved" | "conflict" | "error";

const AUTOSAVE_DELAY = 1200;

/* ------------------------------------------------------------- helpers -- */

function isBlank(section: SectionSpec, value?: SectionValue): boolean {
  if (!value) return true;
  if (value.text && value.text.trim()) return false;
  if (value.items && value.items.length) return false;
  // Suggestions do not count: a section holding only what was offered has
  // nothing the doctor has actually written.
  if (value.medicines?.length || value.investigations?.length) return false;
  const fields = value.fields ?? {};
  return section.fields.every((spec) => {
    const item = fields[spec.key];
    return item === null || item === undefined || item === "" || item === false ||
      (Array.isArray(item) && item.length === 0);
  });
}

/** An AI section holds prose or a list depending on what it was drafted from. */
function aiHoldsText(section: SectionSpec): boolean {
  return section.ai_source === "intake_summary";
}

function originLabel(origin?: SectionOrigin, signed = false): string | null {
  if (!origin) return null;
  if (origin.source.startsWith("ai:")) {
    const from =
      origin.source === "ai:discharge_summary" ? "Drafted from the ward record" : "Drafted from intake";
    // "Check before signing" on a document that has been signed reads as a
    // warning that the check was skipped. Once signed, say what happened.
    if (signed) {
      return origin.edited ? `${from} · edited before signing` : `${from} · reviewed at signing`;
    }
    return origin.edited ? `${from} · edited` : `${from} — check before signing`;
  }
  if (origin.source.startsWith("admission:")) return "From the admission record";
  if (origin.source === "template") return `From template “${origin.name ?? ""}”`;
  if (origin.source === "previous_visit") {
    return origin.signed_at
      ? `Carried from the visit of ${formatDateTime(origin.signed_at)}`
      : "Carried from the previous visit";
  }
  return null;
}

function openBlob(blob: Blob) {
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/* --------------------------------------------------------- field input -- */

function FieldInput({
  spec,
  value,
  disabled,
  onChange,
}: {
  spec: FieldSpec;
  value: FieldValue | undefined;
  disabled: boolean;
  onChange: (value: FieldValue) => void;
}) {
  const base =
    "h-8 w-full rounded-md border border-input bg-white px-2.5 text-sm text-ink focus-visible:border-pine focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pine/20 disabled:bg-mint/40";

  switch (spec.type) {
    case "textarea":
      return (
        <textarea
          value={(value as string) ?? ""}
          disabled={disabled}
          rows={2}
          onChange={(event) => onChange(event.target.value)}
          className={cn(base, "h-auto py-1.5")}
        />
      );
    case "select":
      return (
        <select
          value={(value as string) ?? ""}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value || null)}
          className={base}
        >
          <option value="">—</option>
          {spec.options.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      );
    case "multiselect": {
      const chosen = Array.isArray(value) ? value : [];
      return (
        <div className="flex flex-wrap gap-1.5">
          {spec.options.map((option) => {
            const on = chosen.includes(option);
            return (
              <button
                key={option}
                type="button"
                disabled={disabled}
                aria-pressed={on}
                onClick={() =>
                  onChange(on ? chosen.filter((item) => item !== option) : [...chosen, option])
                }
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-xs transition",
                  on ? "border-pine bg-pine text-mint" : "border-border text-ink-muted hover:bg-mint"
                )}
              >
                {option}
              </button>
            );
          })}
        </div>
      );
    }
    case "checkbox":
      return (
        <input
          type="checkbox"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          className="h-4 w-4 accent-pine"
        />
      );
    default:
      return (
        <div className="flex items-center gap-1.5">
          <input
            type={spec.type === "number" ? "text" : spec.type}
            // Numbers are kept as typed ("98." mid-keystroke) and converted by
            // the server; a numeric input would eat the decimal point.
            inputMode={spec.type === "number" ? "decimal" : undefined}
            value={value === null || value === undefined ? "" : String(value)}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
            className={base}
          />
          {spec.unit && <span className="shrink-0 text-[11px] text-ink-faint">{spec.unit}</span>}
        </div>
      );
  }
}

/* ------------------------------------------------------ section editors -- */

function ItemList({
  items,
  editable,
  category,
  placeholder,
  onChange,
}: {
  items: string[];
  editable: boolean;
  category?: string | null;
  placeholder?: string | null;
  onChange: (items: string[]) => void;
}) {
  return (
    <div className="space-y-1.5">
      {items.length > 0 && (
        <ul className="space-y-1">
          {items.map((item, index) => (
            <li
              key={index}
              className="group flex items-start gap-2 rounded-md px-1.5 py-1 hover:bg-mint/50"
            >
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-pine/50" />
              {/* A line the doctor accepted is theirs to reword. A drafted
                  differential usually wants a word changed, not deleting and
                  typing again from nothing. Empty on blur means removed. */}
              {editable ? (
                <textarea
                  value={item}
                  rows={1}
                  aria-label={`Edit ${item}`}
                  onChange={(event) =>
                    onChange(
                      items.map((existing, at) => (at === index ? event.target.value : existing))
                    )
                  }
                  onBlur={(event) => {
                    if (!event.target.value.trim()) {
                      onChange(items.filter((_, at) => at !== index));
                    }
                  }}
                  onInput={(event) => {
                    const box = event.currentTarget;
                    box.style.height = "auto";
                    box.style.height = `${box.scrollHeight}px`;
                  }}
                  className="min-w-0 flex-1 resize-none overflow-hidden border-0 border-b border-transparent bg-transparent p-0 text-sm leading-6 text-ink focus:border-pine/40 focus:outline-none focus:ring-0"
                />
              ) : (
                <span className="min-w-0 flex-1 text-sm text-ink">{item}</span>
              )}
              {editable && (
                <button
                  type="button"
                  onClick={() => onChange(items.filter((_, at) => at !== index))}
                  className="shrink-0 rounded p-0.5 text-ink-faint opacity-60 transition hover:text-clay group-hover:opacity-100"
                  aria-label={`Remove ${item}`}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {editable && (
        <PhraseInput
          category={category}
          placeholder={placeholder}
          existing={items}
          onAdd={(phrase) => onChange([...items, phrase])}
        />
      )}
    </div>
  );
}

function SectionBody({
  section,
  value,
  editable,
  patientId,
  department,
  transcript,
  onChange,
}: {
  section: SectionSpec;
  value: SectionValue | undefined;
  editable: boolean;
  patientId?: string;
  department?: string;
  transcript?: string;
  onChange: (value: SectionValue) => void;
}) {
  // An AI section drafted as prose still shows a textarea, but once it holds
  // bullets — or has bullets waiting to be tapped — it is a list.
  const holdsText =
    section.kind === "text" ||
    (section.kind === "ai" &&
      aiHoldsText(section) &&
      !(value?.items?.length || value?.suggestions?.length));

  if (section.kind === "medicines") {
    return (
      <MedicineSection
        medicines={value?.medicines ?? []}
        suggestions={(value?.suggestions ?? []) as PadMedicine[]}
        editable={editable}
        patientId={patientId}
        onChange={(next) => onChange({ ...value, ...next })}
      />
    );
  }

  if (section.kind === "investigations") {
    return (
      <InvestigationSection
        investigations={value?.investigations ?? []}
        suggestions={(value?.suggestions ?? []) as PadInvestigation[]}
        editable={editable}
        department={department}
        onChange={(next) => onChange({ ...value, ...next })}
      />
    );
  }

  if (section.kind === "fields") {
    const fields = value?.fields ?? {};
    return (
      <div className="grid gap-x-3 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
        {section.fields.map((spec) => (
          <label key={spec.key} className="block min-w-0">
            <span className="mb-0.5 block text-[11px] font-medium text-ink-muted">
              {spec.label}
              {spec.required && <span className="text-clay"> *</span>}
            </span>
            <FieldInput
              spec={spec}
              value={fields[spec.key]}
              disabled={!editable}
              onChange={(next) => onChange({ fields: { ...fields, [spec.key]: next } })}
            />
          </label>
        ))}
      </div>
    );
  }

  if (holdsText) {
    const text = value?.text ?? "";
    if (!editable) {
      return <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{text}</p>;
    }
    return (
      <textarea
        value={text}
        placeholder={section.placeholder ?? undefined}
        onChange={(event) => onChange({ ...value, text: event.target.value })}
        rows={Math.min(12, Math.max(3, Math.ceil(text.length / 90) + text.split("\n").length))}
        className="w-full resize-y rounded-md border border-input bg-white px-2.5 py-2 text-sm leading-relaxed text-ink placeholder:text-ink-faint focus-visible:border-pine focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pine/20"
      />
    );
  }

  // A list section's suggestions are plain lines; the row kinds hold their
  // own shapes and render themselves.
  const suggestions = (value?.suggestions ?? []).filter(
    (item): item is string => typeof item === "string"
  );

  return (
    <div className="space-y-2">
      <ItemList
        items={value?.items ?? []}
        editable={editable}
        category={section.catalogue_category}
        placeholder={section.placeholder}
        onChange={(items) => onChange({ ...value, items })}
      />

      {/* What the intake offered, still waiting to be taken. Nothing here is
          part of the record or printed until the doctor taps it. */}
      {editable && suggestions.length > 0 && (
        <div className="rounded-lg border border-dashed border-pine/40 bg-pine/5 p-2">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <p className="flex items-center gap-1 text-[11px] font-medium text-pine">
              <Sparkles className="h-3 w-3" />
              Suggested from the intake — tap to add
            </p>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 text-[11px]"
              onClick={() =>
                onChange({
                  ...value,
                  items: [...(value?.items ?? []), ...suggestions],
                  suggestions: [],
                })
              }
            >
              Add all
            </Button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {suggestions.map((item, index) => (
              <button
                key={index}
                type="button"
                className="rounded-full border border-pine/30 bg-white px-2.5 py-1 text-left text-xs text-ink hover:border-pine hover:bg-mint"
                onClick={() =>
                  onChange({
                    ...value,
                    items: [...(value?.items ?? []), item],
                    suggestions: suggestions.filter((_, at) => at !== index),
                  })
                }
              >
                <Plus className="mr-1 inline h-3 w-3 text-pine" />
                {item}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------ the pad -- */

export function VisitPad({
  consultationId,
  admissionId,
  surgeryId,
  documentType = "opd_visit",
  documentId,
  // What was said in the consultation. Medicines are read off it on request,
  // which is the only way a drug reaches the pad without being typed.
  transcript,
  onChanged,
}: {
  transcript?: string;
  /** An OPD pad, opened for this consultation. */
  consultationId?: string;
  /** An inpatient document, opened for this admission. */
  admissionId?: string;
  /** A theatre note, opened for this surgery. */
  surgeryId?: string;
  documentType?: string;
  /** One particular document, opened as it stands — a note picked from a list. */
  documentId?: string;
  /** Told after signing, correcting or discarding, so the page around can refresh. */
  onChanged?: () => void;
}) {
  const [doc, setDoc] = useState<PadDocument | null>(null);
  const [values, setValues] = useState<Record<string, SectionValue>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [readOnlyNote, setReadOnlyNote] = useState<string | null>(null);
  const [emptyForReader, setEmptyForReader] = useState(false);

  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [previous, setPrevious] = useState<PadDocument | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [arranging, setArranging] = useState(false);
  const [order, setOrder] = useState<SectionSpec[]>([]);
  const [templates, setTemplates] = useState<PadTemplate[] | null>(null);
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [templateShared, setTemplateShared] = useState(false);
  const [signOpen, setSignOpen] = useState(false);
  // What the prescription on this pad raises, and whether the doctor has said
  // they mean it anyway.
  const [alerts, setAlerts] = useState<SafetyAlert[]>([]);
  const [acknowledged, setAcknowledged] = useState(false);
  const [checkingSafety, setCheckingSafety] = useState(false);
  const [amendRequest, setAmendRequest] = useState<ReasonRequest | null>(null);

  // Refs hold what async callbacks must read fresh: the latest typed values,
  // the server's last timestamp, and whether a save is in flight.
  const docRef = useRef<PadDocument | null>(null);
  const valuesRef = useRef<Record<string, SectionValue>>({});
  const updatedAtRef = useRef<string>("");
  const dirtyRef = useRef(false);
  const savingRef = useRef<Promise<void> | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const conflictRef = useRef(false);

  const accept = useCallback((document: PadDocument) => {
    docRef.current = document;
    valuesRef.current = document.values ?? {};
    updatedAtRef.current = document.updated_at;
    dirtyRef.current = false;
    conflictRef.current = false;
    setDoc(document);
    setValues(document.values ?? {});
    setOrder(document.sections);
    setSaveState("idle");
  }, []);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      if (documentId) {
        accept(await staffApi.padDocument(documentId));
      } else if (surgeryId) {
        accept(await staffApi.openSurgeryPad(surgeryId, documentType));
      } else if (admissionId) {
        accept(await staffApi.openAdmissionPad(admissionId, documentType));
      } else if (consultationId) {
        accept(await staffApi.openPad(consultationId, documentType));
      }
      setReadOnlyNote(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        // Can read the record but not write this document — a nurse opening
        // the doctor's admission note. Show the signed copy, if there is
        // one, with the server's reason, rather than an error.
        setReadOnlyNote(err.message || "You can read this document but not write in it.");
        try {
          const list = await staffApi.padDocuments(
            surgeryId
              ? { surgery_id: surgeryId, document_type: documentType }
              : admissionId
              ? { admission_id: admissionId, document_type: documentType }
              : { consultation_id: consultationId, document_type: documentType }
          );
          const signed = list.find((item) => item.status === "signed");
          if (signed) accept(await staffApi.padDocument(signed.id));
          else setEmptyForReader(true);
        } catch (inner) {
          setLoadError(inner instanceof Error ? inner.message : "Could not load the pad.");
        }
        return;
      }
      setLoadError(err instanceof Error ? err.message : "Could not open the pad.");
    }
  }, [accept, admissionId, consultationId, documentId, documentType, surgeryId]);

  useEffect(() => {
    void load();
  }, [load]);

  const editable = doc?.status === "draft" && !readOnlyNote;

  // The patient's last signed visit, offered for "copy previous".
  useEffect(() => {
    if (!doc || doc.status !== "draft") return;
    let cancelled = false;
    staffApi
      .padPreviousVisit(doc.id)
      .then((found) => !cancelled && setPrevious(found))
      .catch(() => !cancelled && setPrevious(null));
    return () => {
      cancelled = true;
    };
  }, [doc?.id, doc?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ---------------------------------------------------------- saving -- */

  const flush = useCallback(async (): Promise<void> => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    // One save at a time. A second flush waits for the first, then saves
    // whatever was typed while it was in flight.
    if (savingRef.current) {
      await savingRef.current;
    }
    const current = docRef.current;
    if (!current || current.status !== "draft" || !dirtyRef.current || conflictRef.current) return;

    const run = (async () => {
      dirtyRef.current = false;
      setSaveState("saving");
      try {
        const saved = await staffApi.savePad(current.id, valuesRef.current, updatedAtRef.current);
        updatedAtRef.current = saved.updated_at;
        docRef.current = saved;
        // The server's copy updates provenance and timestamps. The values on
        // screen stay as typed — the doctor may have kept typing meanwhile.
        setDoc(saved);
        setSavedAt(new Date());
        setSaveState(dirtyRef.current ? "pending" : "saved");
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          conflictRef.current = true;
          setSaveState("conflict");
        } else if (err instanceof ApiError && err.status === 403) {
          // Opened by id, the page could not know this person may only read
          // it. Stop retrying and say so, instead of "will retry" forever.
          conflictRef.current = true;
          setReadOnlyNote(err.message);
          setSaveState("idle");
        } else {
          dirtyRef.current = true;
          setSaveState("error");
        }
      }
    })();
    savingRef.current = run;
    await run;
    savingRef.current = null;
    if (dirtyRef.current && !conflictRef.current) {
      timerRef.current = setTimeout(() => void flush(), AUTOSAVE_DELAY);
    }
  }, []);

  const update = useCallback(
    (key: string, value: SectionValue) => {
      const next = { ...valuesRef.current, [key]: value };
      valuesRef.current = next;
      setValues(next);
      dirtyRef.current = true;
      setSaveState("pending");
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => void flush(), AUTOSAVE_DELAY);
    },
    [flush]
  );

  // Leaving the tab unmounts this component. Whatever was typed in the last
  // second is saved on the way out, and closing the page asks first.
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirtyRef.current || savingRef.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
      if (dirtyRef.current) void flush();
    };
  }, [flush]);

  /* --------------------------------------------------------- actions -- */

  const act = useCallback(
    async (label: string, work: () => Promise<void>) => {
      setBusy(label);
      setActionError(null);
      setNotice(null);
      try {
        await flush();
        if (conflictRef.current) {
          throw new Error("Resolve the conflicting change before doing anything else.");
        }
        await work();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "That did not go through.");
      } finally {
        setBusy(null);
      }
    },
    [flush]
  );

  const sendWhatsApp = () =>
    act("whatsapp", async () => {
      if (!doc?.prescription_id) return;
      await staffApi.sendPrescriptionWhatsApp(doc.prescription_id);
      setNotice("Sent on WhatsApp to the patient's registered number.");
    });

  const print = () =>
    act("print", async () => {
      const current = docRef.current;
      if (!current) return;
      // Once the pad has issued a prescription, that is what the patient is
      // handed: the printed prescription with the Rx heading, the medicines
      // laid out to be read at a chemist's counter and the doctor's
      // registration under the signature. The pad's own sheet is the clinical
      // record, and is what prints while the document is still a draft.
      // Fetched with the login token rather than opened as a plain URL: the
      // PDF endpoints need the Authorization header, and a bare window.open
      // reaches them signed out and comes back 401.
      if (current.prescription_id) {
        const response = await fetch(
          staffApi.prescriptionPdfUrl(current.prescription_id),
          { headers: { Authorization: `Bearer ${getToken() ?? ""}` }, cache: "no-store" }
        );
        if (!response.ok) throw new Error("The prescription could not be printed.");
        openBlob(await response.blob());
      } else {
        openBlob(await staffApi.padPdf(current.id));
      }
      if (current.status !== "draft") accept(await staffApi.padDocument(current.id));
    });

  const copyPrevious = () =>
    act("copy", async () => {
      const current = docRef.current;
      if (!current || !previous) return;
      const result = await staffApi.copyPadFromPrevious(current.id);
      accept(result);
      const carried = result.sections
        .filter((section) => result.provenance[section.key]?.source === "previous_visit")
        .map((section) => section.title.toLowerCase());
      setNotice(
        carried.length
          ? `Copied ${carried.join(" and ")} from the visit of ${formatDateTime(previous.signed_at ?? previous.created_at)}.`
          : "Nothing new to copy from the previous visit."
      );
    });

  const openTemplates = async () => {
    setTemplatesOpen(true);
    setTemplates(null);
    try {
      setTemplates(await staffApi.padTemplates(docRef.current?.document_type));
    } catch (err) {
      setTemplates([]);
      setActionError(err instanceof Error ? err.message : "Could not load templates.");
    }
  };

  const applyTemplate = (template: PadTemplate, replace: boolean) =>
    act("template", async () => {
      const current = docRef.current;
      if (!current) return;
      accept(await staffApi.applyPadTemplate(current.id, template.id, replace));
      setTemplatesOpen(false);
      setNotice(`${replace ? "Replaced with" : "Added"} template “${template.name}”.`);
    });

  const saveTemplate = () =>
    act("save-template", async () => {
      const current = docRef.current;
      if (!current) return;
      const saved = await staffApi.savePadTemplate({
        document_id: current.id,
        name: templateName.trim(),
        shared: templateShared,
      });
      setSaveTemplateOpen(false);
      setTemplateName("");
      setNotice(
        `Saved “${saved.name}” as ${saved.shared ? "a shared" : "your"} template. AI-drafted sections are never included.`
      );
    });

  const saveArrangement = () =>
    act("arrange", async () => {
      const current = docRef.current;
      if (!current) return;
      accept(
        await staffApi.arrangePad(
          current.id,
          order.map((section) => ({
            key: section.key,
            visible_in_pad: section.visible_in_pad,
            visible_in_print: section.visible_in_print,
          }))
        )
      );
      setArranging(false);
    });

  /** Every medicine written on the pad, whichever section holds them. */
  const prescribed = useMemo(
    () =>
      order
        .filter((section) => section.kind === "medicines")
        .flatMap((section) => values[section.key]?.medicines ?? []),
    [order, values]
  );

  /**
   * Ask about the prescription before the dialog offers to sign.
   *
   * The server refuses a signature while a serious warning stands. Asking here
   * as well is not duplication: it is what turns "refused" into something the
   * doctor can read and answer.
   */
  const openSignDialog = () => {
    setAlerts([]);
    setAcknowledged(false);
    setSignOpen(true);
    if (prescribed.length === 0 || !doc?.patient_id) return;
    setCheckingSafety(true);
    void staffApi
      .safetyCheck(doc.patient_id, prescribed as unknown as Record<string, unknown>[])
      .then((result) => setAlerts(result.alerts))
      .catch(() => setAlerts([]))
      .finally(() => setCheckingSafety(false));
  };

  const serious = alerts.filter((alert) => alert.severity === "serious");

  const sign = () =>
    act("sign", async () => {
      const current = docRef.current;
      if (!current) return;
      accept(await staffApi.signPad(current.id, serious));
      setSignOpen(false);
      onChanged?.();
      setNotice("Signed. The pad is now part of the record and can only be corrected by a new version.");
    });

  const startCorrection = () => {
    const current = docRef.current;
    if (!current) return;
    setAmendRequest({
      title: "Correct this signed pad",
      detail:
        "A new version is started with everything on this one. The signed original stays in the record and is marked superseded once the correction is signed.",
      confirmLabel: "Start correction",
      run: async (reason) => {
        accept(await staffApi.amendPad(current.id, reason));
        setNotice(`Correcting version ${current.version}. Sign when done.`);
        onChanged?.();
      },
    });
  };

  const draftDischarge = () =>
    act("ai-discharge", async () => {
      const current = docRef.current;
      if (!current) return;
      const result = await staffApi.draftDischargeWithAi(current.id);
      accept(result.document);
      setNotice(
        result.filled.length
          ? `Drafted ${result.filled.join(", ").toLowerCase()} from the ward record. Read every line — the medicines especially — before signing.`
          : "Every section already has something written in it, so nothing was drafted."
      );
      if (result.uncertain.length) {
        setActionError(`The draft could not confirm: ${result.uncertain.join("; ")}`);
      }
    });

  const discardCorrection = () =>
    act("discard", async () => {
      const current = docRef.current;
      if (!current) return;
      await staffApi.discardPad(current.id);
      await load();
      onChanged?.();
      setNotice("Correction discarded. The signed version is unchanged.");
    });

  const moveSection = (index: number, step: -1 | 1) => {
    setOrder((current) => {
      const next = [...current];
      const target = index + step;
      if (target < 0 || target >= next.length) return current;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const toggleSection = (key: string, field: "visible_in_pad" | "visible_in_print") => {
    setOrder((current) =>
      current.map((section) =>
        section.key === key ? { ...section, [field]: !section[field] } : section
      )
    );
  };

  // The old system's Ctrl+S and Ctrl+P, carried over unchanged. Save flushes
  // the autosave immediately rather than waiting out the delay.
  useShortcut("ctrl+s", "Save the pad now", () => void flush(), {
    order: 20,
    enabled: Boolean(editable),
  });
  useShortcut("ctrl+p", "Print the pad", () => void print(), {
    order: 21,
    enabled: Boolean(doc) && !arranging,
  });

  const hasAi = useMemo(
    () => Object.values(doc?.provenance ?? {}).some((origin) => origin.source.startsWith("ai:")),
    [doc?.provenance]
  );

  /* ---------------------------------------------------------- render -- */

  if (loadError) {
    return (
      <Card className="border-clay/30 bg-clay/5">
        <CardContent className="flex items-center justify-between gap-3 p-4">
          <p className="text-sm text-clay">{loadError}</p>
          <Button size="sm" variant="outline" onClick={() => void load()}>Try again</Button>
        </CardContent>
      </Card>
    );
  }

  if (emptyForReader) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-ink-muted">
          Nothing has been signed here yet.
        </CardContent>
      </Card>
    );
  }

  if (!doc) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-14 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    );
  }

  const shown = doc.sections.filter(
    // `!== false`, not truthiness: a section with the switch missing is shown.
    // Hiding it would make a whole pad look empty over one absent key.
    (section) =>
      section.visible_in_pad !== false && (editable || !isBlank(section, values[section.key]))
  );

  return (
    <div className="space-y-3">
      {/* ------------------------------------------------ header bar -- */}
      <Card>
        <CardContent className="flex flex-wrap items-center gap-x-3 gap-y-2 p-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-display text-base font-semibold text-pine">{doc.title}</h2>
              {doc.status === "draft" && (
                <Badge variant="outline" size="sm">
                  {doc.version > 1 ? `Correction · v${doc.version}` : "Draft"}
                </Badge>
              )}
              {doc.status === "signed" && (
                <Badge variant="success" size="sm">
                  Signed{doc.version > 1 ? ` · v${doc.version}` : ""}
                </Badge>
              )}
            </div>
            <p className="mt-0.5 text-[11px] text-ink-faint" aria-live="polite">
              {doc.status === "signed" && doc.signed_by_name
                ? `${doc.signed_by_name} · ${formatDateTime(doc.signed_at ?? doc.updated_at)}`
                : saveState === "saving"
                  ? "Saving…"
                  : saveState === "pending"
                    ? "Unsaved changes"
                    : saveState === "error"
                      ? "Not saved — will retry on the next change"
                      : savedAt
                        ? `Saved ${formatTime(savedAt.toISOString())}`
                        : `Started by ${doc.author_name}`}
              {doc.amendment_reason && doc.version > 1 ? ` · Correcting: ${doc.amendment_reason}` : ""}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {editable && !arranging && (
              <>
                {doc.document_type === "ipd_discharge_summary" && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy !== null}
                    onClick={() => void draftDischarge()}
                    title="Fills only the sections nobody has written in yet"
                  >
                    {busy === "ai-discharge" ? <Loader2 className="animate-spin" /> : <Sparkles />}
                    Draft from ward record
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={!previous || busy !== null}
                  onClick={() => void copyPrevious()}
                  title={
                    previous
                      ? `From the visit of ${formatDateTime(previous.signed_at ?? previous.created_at)}`
                      : "No earlier signed visit for this patient"
                  }
                >
                  {busy === "copy" ? <Loader2 className="animate-spin" /> : <Copy />} Copy previous
                </Button>
                <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => void openTemplates()}>
                  <BookOpen /> Templates
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy !== null}
                  onClick={() => setSaveTemplateOpen(true)}
                >
                  <BookmarkPlus /> Save as template
                </Button>
                <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => setArranging(true)}>
                  <ListOrdered /> Arrange
                </Button>
              </>
            )}
            {arranging && (
              <>
                <Button size="sm" variant="ghost" onClick={() => { setOrder(doc.sections); setArranging(false); }}>
                  Cancel
                </Button>
                <Button size="sm" disabled={busy !== null} onClick={() => void saveArrangement()}>
                  {busy === "arrange" ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Done
                </Button>
              </>
            )}
            {editable && !arranging && doc.version > 1 && (
              <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => void discardCorrection()}>
                Discard correction
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ------------------------------------------------------ notices -- */}
      {saveState === "conflict" && (
        <div className="flex items-start gap-2.5 rounded-lg border border-clay/40 bg-clay/5 px-3 py-2.5">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
          <p className="flex-1 text-sm text-ink">
            Someone else changed this pad after you opened it, so your last edit was not saved over
            theirs. Reload to see their version — anything you typed since your last save will need
            re-entering.
          </p>
          <Button size="sm" variant="outline" onClick={() => void load()}>Reload</Button>
        </div>
      )}
      {readOnlyNote && <p className="px-1 text-xs text-ink-muted">{readOnlyNote}</p>}
      {actionError && (
        <p className="flex items-center gap-1.5 px-1 text-xs text-clay">
          <AlertTriangle className="h-3.5 w-3.5" /> {actionError}
        </p>
      )}
      {notice && <p className="px-1 text-xs text-pine">{notice}</p>}
      {editable && hasAi && !arranging && (
        <p className="flex items-start gap-1.5 px-1 text-[11px] leading-snug text-ink-muted">
          <Sparkles className="mt-0.5 h-3 w-3 shrink-0 text-marigold-deep" />
          Sections marked AI were drafted by AI from the patient&apos;s record. Check them before
          signing. A section prints only when its printer mark is on.
        </p>
      )}

      {/* ----------------------------------------------------- arrange -- */}
      {arranging ? (
        <Card>
          <CardContent className="divide-y divide-border p-0">
            {order.map((section, index) => (
              <div key={section.key} className="flex items-center gap-2 px-3 py-2">
                <div className="flex flex-col">
                  <button
                    type="button"
                    disabled={index === 0}
                    onClick={() => moveSection(index, -1)}
                    className="rounded p-0.5 text-ink-faint hover:text-pine disabled:opacity-30"
                    aria-label={`Move ${section.title} up`}
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    disabled={index === order.length - 1}
                    onClick={() => moveSection(index, 1)}
                    className="rounded p-0.5 text-ink-faint hover:text-pine disabled:opacity-30"
                    aria-label={`Move ${section.title} down`}
                  >
                    <ArrowDown className="h-3.5 w-3.5" />
                  </button>
                </div>
                <span className={cn("flex-1 text-sm", section.visible_in_pad ? "text-ink" : "text-ink-faint line-through")}>
                  {section.title}
                </span>
                {section.kind === "ai" && <AiBadge />}
                <button
                  type="button"
                  onClick={() => toggleSection(section.key, "visible_in_pad")}
                  aria-pressed={section.visible_in_pad}
                  className={cn(
                    "flex items-center gap-1 rounded-md border px-2 py-1 text-[11px]",
                    section.visible_in_pad ? "border-pine/30 text-pine" : "border-border text-ink-faint"
                  )}
                >
                  {section.visible_in_pad ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
                  On screen
                </button>
                <button
                  type="button"
                  onClick={() => toggleSection(section.key, "visible_in_print")}
                  aria-pressed={section.visible_in_print}
                  className={cn(
                    "flex items-center gap-1 rounded-md border px-2 py-1 text-[11px]",
                    section.visible_in_print ? "border-pine/30 text-pine" : "border-border text-ink-faint"
                  )}
                >
                  <Printer className="h-3 w-3" /> {section.visible_in_print ? "Prints" : "Not printed"}
                </button>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : (
        /* ------------------------------------------------- sections -- */
        shown.map((section) => {
          const origin = doc.provenance[section.key];
          const label = originLabel(origin, doc.status !== "draft");
          return (
            <Card key={section.key}>
              <CardContent className="p-3">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold text-ink">{section.title}</h3>
                  {(section.kind === "ai" || origin?.source.startsWith("ai:")) && <AiBadge />}
                  {label && <span className="text-[11px] text-ink-faint">{label}</span>}
                  <span className="ml-auto flex items-center gap-2 text-[10px] text-ink-faint">
                    {section.carry_forward && <span title="Copied forward to the next visit">Carries forward</span>}
                    {/* Only when printing is explicitly off — the server's
                        own default for a missing switch is to print. */}
                    {section.visible_in_print === false && (
                      <span className="flex items-center gap-0.5" title="Not on the printed copy">
                        <Printer className="h-3 w-3" /> not printed
                      </span>
                    )}
                  </span>
                </div>
                <SectionBody
                  section={section}
                  value={values[section.key]}
                  editable={editable}
                  patientId={doc?.patient_id}
                  department={doc?.department ?? undefined}
                  transcript={transcript}
                  onChange={(next) => update(section.key, next)}
                />
              </CardContent>
            </Card>
          );
        })
      )}

      {!editable && shown.length === 0 && (
        <Card>
          <CardContent className="py-8 text-center text-sm text-ink-muted">
            Nothing was written on this pad.
          </CardContent>
        </Card>
      )}

      {/* --------------------------------------------- finishing the pad --
          Signing and printing come after the last section, where the doctor
          arrives having read what they are putting their name to, rather than
          at the top where they meet them before writing anything. */}
      {!arranging && (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-end gap-1.5 p-3">
            {doc.prescription_id && (
              <Button
                size="sm"
                variant="outline"
                disabled={busy !== null}
                onClick={() => void sendWhatsApp()}
              >
                {busy === "whatsapp" ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Send className="h-3.5 w-3.5" />
                )}
                Send on WhatsApp
              </Button>
            )}
            <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void print()}>
              {busy === "print" ? <Loader2 className="animate-spin" /> : <Printer />}
              {doc.status === "draft" ? "Print draft" : "Print"}
            </Button>
            {doc.status === "signed" && !readOnlyNote && (
              <Button size="sm" variant="outline" disabled={busy !== null} onClick={startCorrection}>
                <PenLine /> Correct
              </Button>
            )}
            {editable && (
              <Button size="sm" disabled={busy !== null} onClick={openSignDialog}>
                <CheckCircle2 /> Sign
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {/* ------------------------------------------------------ dialogs -- */}
      <Dialog open={templatesOpen} onOpenChange={setTemplatesOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Load a template</DialogTitle>
            <DialogDescription>
              Add fills empty sections and appends to lists. Replace overwrites every section the
              template has content for.
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[50vh] space-y-2 overflow-y-auto">
            {templates === null && (
              <p className="flex items-center gap-1.5 text-xs text-ink-faint">
                <Loader2 className="h-3 w-3 animate-spin" /> Loading…
              </p>
            )}
            {templates?.length === 0 && (
              <p className="text-sm text-ink-muted">
                No templates yet. Write a pad the way you like it and use “Save as template”.
              </p>
            )}
            {templates?.map((template) => (
              <div key={template.id} className="rounded-lg border border-border p-3">
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-ink">{template.name}</p>
                    <p className="text-[11px] text-ink-faint">
                      {template.shared ? "Shared" : "Yours"} · {template.owner_name}
                      {template.use_count ? ` · used ${template.use_count}×` : ""}
                    </p>
                    <p className="mt-1 text-[11px] text-ink-muted">
                      {template.section_keys
                        .map((key) => doc.sections.find((section) => section.key === key)?.title ?? key)
                        .join(" · ")}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy !== null}
                    onClick={() => void applyTemplate(template, false)}
                  >
                    Add
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy !== null}
                    onClick={() => void applyTemplate(template, true)}
                  >
                    Replace
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={saveTemplateOpen} onOpenChange={setSaveTemplateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save as template</DialogTitle>
            <DialogDescription>
              Everything on this pad except the AI-drafted sections, which belong to this patient
              alone. Template text can use {"{{patient_name}}"}, {"{{age}}"}, {"{{date}}"} and similar.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              autoFocus
              value={templateName}
              placeholder="e.g. Knee OA — first visit"
              onChange={(event) => setTemplateName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && templateName.trim()) void saveTemplate();
              }}
            />
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={templateShared}
                onChange={(event) => setTemplateShared(event.target.checked)}
                className="h-4 w-4 accent-pine"
              />
              Share with the department
            </label>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setSaveTemplateOpen(false)}>Cancel</Button>
            <Button disabled={!templateName.trim() || busy !== null} onClick={() => void saveTemplate()}>
              {busy === "save-template" && <Loader2 className="animate-spin" />} Save template
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={signOpen} onOpenChange={setSignOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sign this pad?</DialogTitle>
            <DialogDescription>
              Signing makes it part of the patient&apos;s record. After this it cannot be edited — only
              corrected by a new version with a stated reason, and the original stays readable.
            </DialogDescription>
          </DialogHeader>
          {hasAi && (
            <p className="flex items-start gap-1.5 rounded-md bg-marigold/10 px-3 py-2 text-xs text-ink">
              <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-marigold-deep" />
              This document contains sections drafted by AI. Your signature confirms you have
              checked them.
            </p>
          )}

          {checkingSafety && (
            <p className="flex items-center gap-1.5 text-xs text-ink-muted">
              <Loader2 className="h-3 w-3 animate-spin" /> Checking the prescription…
            </p>
          )}

          {serious.length > 0 && (
            <div className="space-y-2 rounded-md border border-clay/40 bg-clay/5 px-3 py-2">
              <p className="flex items-center gap-1.5 text-xs font-medium text-clay">
                <AlertTriangle className="h-3.5 w-3.5" />
                {serious.length === 1 ? "A serious warning" : `${serious.length} serious warnings`}
              </p>
              <ul className="space-y-1.5">
                {serious.map((alert, index) => (
                  <li key={index} className="text-xs text-ink">
                    <span className="font-medium">{alert.medicines.join(" + ") || "Prescription"}</span>
                    {" — "}
                    {alert.description}
                    {alert.suggested_action && (
                      <span className="block text-ink-muted">{alert.suggested_action}</span>
                    )}
                  </li>
                ))}
              </ul>
              <label className="flex items-start gap-2 text-xs text-ink">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={acknowledged}
                  onChange={(event) => setAcknowledged(event.target.checked)}
                />
                I have read these and mean to prescribe anyway.
              </label>
            </div>
          )}

          {/* Anything not serious is worth reading but does not stand in the
              way of a signature. */}
          {alerts.length > serious.length && (
            <ul className="space-y-1">
              {alerts
                .filter((alert) => alert.severity !== "serious")
                .map((alert, index) => (
                  <li key={index} className="text-[11px] text-ink-muted">
                    {alert.description}
                  </li>
                ))}
            </ul>
          )}

          {actionError && <p className="text-xs text-clay">{actionError}</p>}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setSignOpen(false)}>Not yet</Button>
            <Button
              disabled={busy !== null || checkingSafety || (serious.length > 0 && !acknowledged)}
              onClick={() => void sign()}
            >
              {busy === "sign" ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
              {serious.length > 0 ? "Acknowledge and sign" : "Sign"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ReasonDialog request={amendRequest} onClose={() => setAmendRequest(null)} />
    </div>
  );
}
