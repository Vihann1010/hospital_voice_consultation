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
 * Everything is optional. Nothing here blocks the patient from simply waiting
 * to be seen.
 */
import { useCallback, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, Camera, CheckCircle2, FileText, Loader2, Upload, X } from "lucide-react";
import { API_URL } from "@/lib/api";

interface UploadedFile {
  id: string;
  name: string;
  status: "uploading" | "done" | "failed";
  error?: string;
}

const MAX_FILES = 10;

export function PreviousReportsUpload({ sessionToken }: { sessionToken: string }) {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);

  const uploadOne = useCallback(
    async (file: File) => {
      const key = `${file.name}-${Date.now()}-${Math.random()}`;
      setFiles((current) => [
        ...current,
        { id: key, name: file.name, status: "uploading" },
      ]);

      const body = new FormData();
      body.append("session_token", sessionToken);
      body.append("file", file);
      body.append("title", file.name);

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
      if (!list) return;
      const room = MAX_FILES - files.length;
      Array.from(list)
        .slice(0, Math.max(room, 0))
        .forEach((file) => void uploadOne(file));
    },
    [files.length, uploadOne]
  );

  const succeeded = files.filter((file) => file.status === "done").length;
  const full = files.length >= MAX_FILES;

  return (
    <section className="rounded-2xl border border-pine/10 bg-white p-5">
      <h2 className="font-display text-base font-semibold text-pine">
        Have any earlier reports with you?
      </h2>
      <p className="mt-1 text-sm leading-relaxed text-ink-muted">
        Photograph or upload any previous X-rays, scans or blood tests you have
        brought. The doctor will see them before you go in. This is optional —
        you can simply wait to be called.
      </p>

      <div
        onDragOver={(event: React.DragEvent<HTMLDivElement>) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event: React.DragEvent<HTMLDivElement>) => {
          event.preventDefault();
          setDragging(false);
          accept(event.dataTransfer.files);
        }}
        className={`mt-4 rounded-xl border-2 border-dashed p-5 text-center transition ${
          dragging ? "border-marigold bg-marigold/[0.06]" : "border-pine/15 bg-mint/40"
        }`}
      >
        <FileText className="mx-auto h-7 w-7 text-pine/40" aria-hidden="true" />
        <p className="mt-2 text-sm text-ink-muted">
          Photos or PDFs, up to {MAX_FILES} files
        </p>

        <div className="mt-3 flex flex-wrap justify-center gap-2">
          {/* Separate camera entry point: on a phone this opens the camera
              directly, which is how most patients will actually do this. */}
          <button
            type="button"
            onClick={() => cameraRef.current?.click()}
            disabled={full}
            className="inline-flex items-center gap-2 rounded-lg bg-pine px-4 py-2.5 text-sm font-semibold text-mint transition hover:bg-pine-deep disabled:opacity-50"
          >
            <Camera className="h-4 w-4" /> Take a photo
          </button>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={full}
            className="inline-flex items-center gap-2 rounded-lg border border-pine/20 px-4 py-2.5 text-sm font-semibold text-pine transition hover:bg-mint disabled:opacity-50"
          >
            <Upload className="h-4 w-4" /> Choose a file
          </button>
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
          ref={inputRef}
          type="file"
          accept="image/*,application/pdf"
          multiple
          className="hidden"
          onChange={(event) => {
            accept(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

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
