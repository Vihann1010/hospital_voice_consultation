"use client";

/**
 * After the intake ends, invite the patient to add any earlier reports they
 * have brought with them.
 *
 * This is a deliberately low-friction moment: the patient is already holding
 * their file of old X-rays and blood tests while they wait to be called, and
 * a photograph taken now is on the doctor's screen before the consultation
 * starts instead of being handed across the desk halfway through it.
 *
 * The one question asked before the camera opens is what the page is — a
 * prescription, a lab report or a scan. It is not paperwork. Those three
 * things are read by three different analysers, and the wrong one produces
 * confident nonsense rather than an error: a prescription put through the
 * laboratory parser turned the dose instruction "1-0-0" into a reference
 * range and flagged the patient's pantoprazole as an abnormal result.
 *
 * So the choice is the button. Tapping "Prescription" opens the camera, and
 * the answer travels with the photograph. Nobody fills in a form.
 *
 * Everything is optional. Nothing here blocks the patient from simply waiting
 * to be seen.
 */
import { useCallback, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  FlaskConical,
  Loader2,
  Pill,
  Scan,
  Upload,
  X,
} from "lucide-react";
import { API_URL } from "@/lib/api";
import type { DocumentKind } from "@/lib/investigationTypes";

interface UploadedFile {
  id: string;
  name: string;
  kind: DocumentKind;
  status: "uploading" | "done" | "failed";
  error?: string;
}

const MAX_FILES = 10;

/**
 * Worded for a patient, not a clerk. "Blood or lab report" beats "laboratory
 * investigation", and the examples matter more than the label — people
 * recognise their own paperwork by what is printed on it.
 */
const KINDS: {
  kind: DocumentKind;
  label: string;
  hint: string;
  icon: typeof Pill;
}[] = [
  {
    kind: "prescription",
    label: "Prescription",
    hint: "A doctor's slip listing medicines",
    icon: Pill,
  },
  {
    kind: "lab_report",
    label: "Blood or lab report",
    hint: "Printed test results with numbers",
    icon: FlaskConical,
  },
  {
    kind: "imaging",
    label: "Scan or X-ray report",
    hint: "The typed report, not the film",
    icon: Scan,
  },
  {
    kind: "other",
    label: "Something else",
    hint: "Discharge summary, any other paper",
    icon: FileText,
  },
];

export function PreviousReportsUpload({
  sessionToken,
  /** Drop the heading when the page around it already says all this — the
   *  phone upload page opens on nothing else, so it introduces itself. */
  bare = false,
}: {
  sessionToken: string;
  bare?: boolean;
}) {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [pendingKind, setPendingKind] = useState<DocumentKind | null>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const uploadOne = useCallback(
    async (file: File, kind: DocumentKind) => {
      const key = `${file.name}-${Date.now()}-${Math.random()}`;
      setFiles((current) => [
        ...current,
        { id: key, name: file.name, kind, status: "uploading" },
      ]);

      const body = new FormData();
      body.append("session_token", sessionToken);
      body.append("file", file);
      body.append("title", file.name);
      body.append("document_kind", kind);

      try {
        const response = await fetch(`${API_URL}/api/v1/patient-uploads/reports`, {
          method: "POST",
          body,
        });
        if (!response.ok) {
          const detail = await response
            .json()
            .then((data) => data?.detail)
            .catch(() => null);
          throw new Error(detail || "That file could not be uploaded.");
        }
        setFiles((current) =>
          current.map((item) =>
            item.id === key ? { ...item, status: "done" } : item
          )
        );
      } catch (err) {
        setFiles((current) =>
          current.map((item) =>
            item.id === key
              ? {
                  ...item,
                  status: "failed",
                  error: err instanceof Error ? err.message : "Upload failed.",
                }
              : item
          )
        );
      }
    },
    [sessionToken]
  );

  const accept = useCallback(
    (list: FileList | null) => {
      // `pendingKind` is set by the tile that opened the picker. Losing it
      // would mean uploading a document with no declared kind, so the files
      // are dropped rather than sent unlabelled.
      if (!list || !pendingKind) return;
      const room = MAX_FILES - files.length;
      Array.from(list)
        .slice(0, Math.max(room, 0))
        .forEach((file) => void uploadOne(file, pendingKind));
      setPendingKind(null);
    },
    [files.length, pendingKind, uploadOne]
  );

  const open = useCallback((kind: DocumentKind, camera: boolean) => {
    setPendingKind(kind);
    // The ref click has to follow the state update in the same tick; React
    // batches the setState but the input opens regardless, and `accept`
    // reads `pendingKind` from a later render.
    (camera ? cameraRef : fileRef).current?.click();
  }, []);

  const succeeded = files.filter((file) => file.status === "done").length;
  const full = files.length >= MAX_FILES;

  return (
    <section className={bare ? "" : "rounded-2xl border border-pine/10 bg-white p-5"}>
      {!bare && (
        <>
          <h2 className="font-display text-base font-semibold text-pine">
            Have any earlier reports with you?
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-ink-muted">
            Photograph or upload any previous X-rays, scans or blood tests you
            have brought. The doctor will see them before you go in. This is
            optional — you can simply wait to be called.
          </p>
        </>
      )}

      <p className="mt-4 text-sm font-medium text-ink">
        What are you adding?
      </p>
      <p className="mt-0.5 text-xs text-ink-muted">
        Tap one and the camera opens. Add as many as you like, one kind at a time.
      </p>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {KINDS.map(({ kind, label, hint, icon: Icon }) => (
          <button
            key={kind}
            type="button"
            disabled={full}
            onClick={() => open(kind, true)}
            className="flex items-center gap-3 rounded-xl border border-pine/15 bg-mint/40 px-3 py-3 text-left transition hover:border-pine/40 hover:bg-mint disabled:opacity-50"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-pine/10">
              <Icon className="h-4 w-4 text-pine" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-pine">{label}</span>
              <span className="block text-[11px] leading-snug text-ink-muted">
                {hint}
              </span>
            </span>
          </button>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-[11px] text-ink-faint">Already have a PDF?</span>
        {KINDS.map(({ kind, label }) => (
          <button
            key={kind}
            type="button"
            disabled={full}
            onClick={() => open(kind, false)}
            className="inline-flex items-center gap-1 rounded-md border border-pine/15 px-2 py-1 text-[11px] font-medium text-pine transition hover:bg-mint disabled:opacity-50"
          >
            <Upload className="h-3 w-3" /> {label}
          </button>
        ))}
      </div>

      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        capture="environment"
        multiple
        className="hidden"
        onChange={(event) => {
          accept(event.target.files);
          event.target.value = "";
        }}
      />
      <input
        ref={fileRef}
        type="file"
        accept="image/*,application/pdf"
        multiple
        className="hidden"
        onChange={(event) => {
          accept(event.target.files);
          event.target.value = "";
        }}
      />

      {full && (
        <p className="mt-2 text-xs text-marigold-deep">
          That is the maximum for this visit. Please hand any others to the front desk.
        </p>
      )}

      <AnimatePresence initial={false}>
        {files.map((file) => (
          <motion.div
            key={file.id}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-2 flex items-center gap-2.5 rounded-lg bg-mint/60 px-3 py-2"
          >
            {file.status === "uploading" && (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-pine" />
            )}
            {file.status === "done" && (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-pine" />
            )}
            {file.status === "failed" && (
              <AlertCircle className="h-4 w-4 shrink-0 text-clay" />
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-ink">{file.name}</p>
              <p className="text-[11px] text-ink-faint">
                {KINDS.find((entry) => entry.kind === file.kind)?.label}
              </p>
              {file.error && <p className="text-xs text-clay">{file.error}</p>}
            </div>
            {file.status === "failed" && (
              <button
                type="button"
                onClick={() =>
                  setFiles((current) => current.filter((item) => item.id !== file.id))
                }
                className="shrink-0 rounded p-1 text-ink-faint hover:text-clay"
                aria-label={`Dismiss ${file.name}`}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </motion.div>
        ))}
      </AnimatePresence>

      {succeeded > 0 && (
        <p className="mt-3 text-sm font-medium text-pine">
          {succeeded} {succeeded === 1 ? "report" : "reports"} sent to your doctor.
        </p>
      )}
    </section>
  );
}
