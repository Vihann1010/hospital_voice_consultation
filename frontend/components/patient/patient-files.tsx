"use client";

/**
 * Files on a patient's record: ID proofs, referral letters, old records,
 * outside films, clinical photographs.
 *
 * Nothing is read out of these files; they are kept, categorised and bound
 * into the records file. A file attached in error is withdrawn with a reason —
 * never deleted — and stays on the record, out of the everyday list.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { FolderOpen, Loader2, Paperclip, Upload } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type { FileCategoryOption, PatientFileCategory, PatientFileRecord } from "@/lib/recordsTypes";
import { fileSize, openBlob } from "@/lib/recordsTypes";
import { formatDate, formatDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ReasonDialog, type ReasonRequest } from "@/components/ui/reason-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const SELECT =
  "h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-pine/30";

const mayAttach = (role?: string) =>
  ["admin", "doctor", "nurse", "reception", "supervisor"].includes(role ?? "");

export function PatientFiles({
  patientId,
  admissionId,
  consultationId,
  title = "Files",
}: {
  patientId: string;
  admissionId?: string;
  consultationId?: string;
  title?: string;
}) {
  const { user } = useAuth();
  const [categories, setCategories] = useState<FileCategoryOption[]>([]);
  const [files, setFiles] = useState<PatientFileRecord[] | null>(null);
  const [showWithdrawn, setShowWithdrawn] = useState(false);
  const [adding, setAdding] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState<PatientFileCategory | "">("");
  const [name, setName] = useState("");
  const [documentDate, setDocumentDate] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [withdrawRequest, setWithdrawRequest] = useState<ReasonRequest | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const [options, list] = await Promise.all([
        staffApi.patientFileCategories(),
        staffApi.patientFiles({
          patient_id: patientId,
          admission_id: admissionId,
          consultation_id: consultationId,
          include_withdrawn: showWithdrawn || undefined,
        }),
      ]);
      setCategories(options.items);
      setFiles(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Files could not be loaded.");
    }
  }, [admissionId, consultationId, patientId, showWithdrawn]);

  useEffect(() => {
    void load();
  }, [load]);

  function reset() {
    setAdding(false);
    setFile(null);
    setCategory("");
    setName("");
    setDocumentDate("");
    setNotes("");
    if (inputRef.current) inputRef.current.value = "";
  }

  async function upload() {
    if (!file) return setError("Choose a file.");
    if (!category) return setError("Say what the file is.");
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("patient_id", patientId);
      form.append("category", category);
      if (name.trim()) form.append("title", name.trim());
      if (admissionId) form.append("admission_id", admissionId);
      if (consultationId) form.append("consultation_id", consultationId);
      if (documentDate) form.append("document_date", documentDate);
      if (notes.trim()) form.append("notes", notes.trim());
      await staffApi.uploadPatientFile(form);
      reset();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The file could not be attached.");
    } finally {
      setBusy(false);
    }
  }

  const label = (key: string) => categories.find((item) => item.key === key)?.label ?? key;

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center gap-2 pb-2">
        <CardTitle className="mr-auto flex items-center gap-2">
          <Paperclip className="h-4 w-4" /> {title}
        </CardTitle>
        <label className="flex items-center gap-1.5 text-xs text-ink-muted">
          <input type="checkbox" checked={showWithdrawn} onChange={(e) => setShowWithdrawn(e.target.checked)} />
          Show withdrawn
        </label>
        {mayAttach(user?.role) && !adding && (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Upload className="h-4 w-4" /> Attach a file
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {adding && (
          <div className="grid gap-2 rounded-lg border border-border p-3 sm:grid-cols-2">
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,image/*"
              className="text-sm sm:col-span-2"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <select className={SELECT} value={category}
                    onChange={(event) => setCategory(event.target.value as PatientFileCategory)}>
              <option value="">What is it?</option>
              {categories.filter((item) => item.key !== "signed_consent").map((item) => (
                <option key={item.key} value={item.key}>{item.label}</option>
              ))}
            </select>
            <Input placeholder="Title (optional)" value={name} onChange={(event) => setName(event.target.value)} />
            <label className="space-y-1 text-xs text-ink-muted">
              Date on the document
              <Input type="date" value={documentDate} onChange={(event) => setDocumentDate(event.target.value)} />
            </label>
            <label className="space-y-1 text-xs text-ink-muted">
              Notes
              <Input value={notes} onChange={(event) => setNotes(event.target.value)} />
            </label>
            <p className="text-[11px] text-ink-faint sm:col-span-2">
              Signed consent scans are attached from the consent form itself, so the form records that its
              signed copy came back.
            </p>
            <div className="flex gap-2 sm:col-span-2">
              <Button size="sm" disabled={busy || !file || !category} onClick={() => void upload()}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Attach
              </Button>
              <Button size="sm" variant="ghost" onClick={reset}>Cancel</Button>
            </div>
          </div>
        )}
        {error && <p className="text-sm text-clay">{error}</p>}
        {!files ? (
          <Skeleton className="h-12 w-full rounded-lg" />
        ) : files.length === 0 ? (
          <p className="text-sm text-ink-muted">No files attached.</p>
        ) : (
          <ul className="divide-y divide-border">
            {files.map((item) => (
              <li key={item.id} className={cn("flex flex-wrap items-center gap-2 py-2", item.withdrawn_at && "opacity-60")}>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-ink">{item.title}</p>
                  <p className="text-xs text-ink-muted">
                    {label(item.category)}
                    {item.document_date ? ` · dated ${formatDate(item.document_date)}` : ""} · {fileSize(item.size_bytes)} ·
                    attached by {item.uploaded_by_name} · {formatDateTime(item.created_at)}
                  </p>
                  {item.withdrawn_at && (
                    <p className="text-xs text-clay">
                      Withdrawn by {item.withdrawn_by_name}: {item.withdraw_reason}
                    </p>
                  )}
                </div>
                {item.withdrawn_at && <Badge variant="outline" size="sm">Withdrawn</Badge>}
                <Button size="sm" variant="ghost"
                        onClick={async () => {
                          try { openBlob(await staffApi.patientFileBlob(item.id)); }
                          catch (err) { setError(err instanceof Error ? err.message : "The file could not be opened."); }
                        }}>
                  <FolderOpen className="h-4 w-4" /> Open
                </Button>
                {mayAttach(user?.role) && !item.withdrawn_at && (
                  <Button size="sm" variant="ghost" className="text-clay hover:text-clay"
                          onClick={() => setWithdrawRequest({
                            title: "Withdraw this file",
                            detail: `${item.title}. The file stays on the record with your reason, but leaves the everyday list and the records file.`,
                            confirmLabel: "Withdraw",
                            destructive: true,
                            run: async (reason) => {
                              await staffApi.withdrawPatientFile(item.id, reason);
                              await load();
                            },
                          })}>
                    Withdraw
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
      <ReasonDialog request={withdrawRequest} onClose={() => setWithdrawRequest(null)} />
    </Card>
  );
}
