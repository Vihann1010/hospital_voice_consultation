"use client";

/**
 * Certificates and consent forms for one patient.
 *
 * The same panel on the patient's page, a consultation, the case sheet and a
 * theatre case — each showing the forms that belong there, and starting new
 * ones linked to it, so a hospitalisation certificate knows its admission
 * and a surgical consent knows its operation and side.
 *
 * A consent form shows its fixed wording, in English and Hindi, above the
 * pad: the doctor should read what the patient is about to sign. After it is
 * signed in the system and printed, the patient signs the paper; recording
 * that the signed copy came back is the last step, and the list shows which
 * forms are still waiting for it.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, ChevronDown, FileSignature, Loader2, Plus } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type { FormWording, PadDocumentSummary, PadDocumentTypeInfo } from "@/lib/types/pad";
import { formatDateTime } from "@/lib/format";
import { VisitPad } from "@/components/pad/visit-pad";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const mayWrite = (role?: string) => role === "admin" || role === "doctor";
const mayRecordPaper = (role?: string) => role === "admin" || role === "doctor" || role === "nurse";

function Wording({ documentType }: { documentType: string }) {
  const [wording, setWording] = useState<FormWording | null>(null);
  const [open, setOpen] = useState(true);

  useEffect(() => {
    setWording(null);
    void staffApi.padForm(documentType).then(setWording).catch(() => undefined);
  }, [documentType]);

  if (!wording?.statement) return null;
  return (
    <Card className="border-pine/20 bg-mint/40">
      <CardContent className="space-y-2 p-4">
        <button type="button" onClick={() => setOpen((value) => !value)}
                className="flex w-full items-center justify-between text-left text-sm font-semibold text-pine">
          What the patient signs
          <ChevronDown className={cn("h-4 w-4 transition", open && "rotate-180")} />
        </button>
        {open && (
          <div className="grid gap-4 text-sm leading-relaxed text-ink lg:grid-cols-2">
            <ol className="list-decimal space-y-1 pl-5">
              {wording.statement.en.map((line) => <li key={line}>{line}</li>)}
            </ol>
            <ol lang="hi" className="list-decimal space-y-1 pl-5">
              {wording.label_hi && <p className="-ml-5 mb-1 font-medium text-pine">{wording.label_hi}</p>}
              {wording.statement.hi.map((line) => <li key={line}>{line}</li>)}
            </ol>
          </div>
        )}
        <p className="text-xs text-ink-faint">
          Fixed wording, printed on the form. Record below who consented, the language it was
          explained in, and the witness.
        </p>
      </CardContent>
    </Card>
  );
}

export function PatientForms({
  patientId,
  consultationId,
  admissionId,
  surgeryId,
  only,
  active = true,
  title = "Certificates and consent forms",
}: {
  patientId: string;
  consultationId?: string;
  admissionId?: string;
  surgeryId?: string;
  /** Limit to these document types — a theatre case shows only its consents. */
  only?: string[];
  /** A discharged admission or cancelled case: forms can be read, not started. */
  active?: boolean;
  title?: string;
}) {
  const { user } = useAuth();
  const [types, setTypes] = useState<PadDocumentTypeInfo[]>([]);
  const [documents, setDocuments] = useState<PadDocumentSummary[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const scanInput = useRef<HTMLInputElement>(null);
  const [scanFor, setScanFor] = useState<string | null>(null);

  async function attachScan(file: File) {
    if (!scanFor) return;
    setBusy(scanFor);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("patient_id", patientId);
      form.append("category", "signed_consent");
      form.append("pad_document_id", scanFor);
      await staffApi.uploadPatientFile(form);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The signed scan could not be attached.");
    } finally {
      setBusy(null);
      setScanFor(null);
      if (scanInput.current) scanInput.current.value = "";
    }
  }

  const available = useMemo(
    () =>
      types.filter(
        (item) =>
          (item.family === "certificate" || item.family === "consent") &&
          (!only || only.includes(item.key)) &&
          (item.requires !== "admission" || Boolean(admissionId || surgeryId))
      ),
    [admissionId, only, surgeryId, types]
  );
  const familyOf = useMemo(
    () => Object.fromEntries(types.map((item) => [item.key, item.family ?? null])),
    [types]
  );

  const load = useCallback(async () => {
    try {
      const [typeList, list] = await Promise.all([
        staffApi.padDocumentTypes(),
        staffApi.padDocuments({ patient_id: patientId }),
      ]);
      const families = new Set(
        typeList.items
          .filter((item) => item.family === "certificate" || item.family === "consent")
          .map((item) => item.key)
      );
      setTypes(typeList.items);
      setDocuments(
        list.filter(
          (item) =>
            families.has(item.document_type) &&
            (!only || only.includes(item.document_type)) &&
            (surgeryId
              ? item.surgery_id === surgeryId
              : admissionId
                ? item.admission_id === admissionId
                : consultationId
                  ? item.consultation_id === consultationId
                  : true)
        )
      );
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Forms could not be loaded.");
    }
  }, [admissionId, consultationId, only, patientId, surgeryId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function start(documentType: string) {
    setBusy(documentType);
    setError(null);
    try {
      const document = await staffApi.openPatientPad(patientId, documentType, {
        consultation_id: consultationId,
        admission_id: admissionId,
        surgery_id: surgeryId,
      });
      setOpenId(document.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The form could not be started.");
    } finally {
      setBusy(null);
    }
  }

  async function paperSigned(id: string) {
    setBusy(id);
    setError(null);
    try {
      await staffApi.recordPaperSigned(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the signed copy.");
    } finally {
      setBusy(null);
    }
  }

  const opened = documents?.find((item) => item.id === openId) ?? null;
  const certificates = available.filter((item) => item.family === "certificate");
  const consents = available.filter((item) => item.family === "consent");

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center gap-2 pb-2">
          <CardTitle className="mr-auto flex items-center gap-2">
            <FileSignature className="h-4 w-4" /> {title}
          </CardTitle>
          {mayWrite(user?.role) && active && available.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" disabled={busy !== null}>
                  {busy && !documents?.some((d) => d.id === busy) ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )}
                  New <ChevronDown className="h-3.5 w-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {certificates.length > 0 && <DropdownMenuLabel>Certificates</DropdownMenuLabel>}
                {certificates.map((item) => (
                  <DropdownMenuItem key={item.key} onSelect={() => void start(item.key)}>
                    {item.label}
                  </DropdownMenuItem>
                ))}
                {certificates.length > 0 && consents.length > 0 && <DropdownMenuSeparator />}
                {consents.length > 0 && <DropdownMenuLabel>Consent forms</DropdownMenuLabel>}
                {consents.map((item) => (
                  <DropdownMenuItem key={item.key} onSelect={() => void start(item.key)}>
                    {item.label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </CardHeader>
        <CardContent className="p-0">
          {error && <p className="px-4 pb-2 text-sm text-clay">{error}</p>}
          {!documents ? (
            <div className="px-4 pb-4"><Skeleton className="h-12 w-full rounded-lg" /></div>
          ) : documents.length === 0 ? (
            <p className="px-4 pb-4 text-sm text-ink-muted">None yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {documents.map((item) => {
                const consent = familyOf[item.document_type] === "consent";
                return (
                  <li key={item.id}
                      className={cn("flex flex-wrap items-center gap-2 px-4 py-2.5",
                                    item.id === openId && "bg-mint/60")}>
                    <button type="button" onClick={() => setOpenId(item.id === openId ? null : item.id)}
                            className="min-w-0 flex-1 text-left">
                      <p className="text-sm font-medium text-ink">
                        {item.title}
                        {item.version > 1 && <span className="ml-1 text-xs text-ink-faint">v{item.version}</span>}
                      </p>
                      <p className="text-xs text-ink-muted">
                        {item.serial_number ?? "Not numbered yet"} ·{" "}
                        {item.status === "signed"
                          ? `signed by ${item.signed_by_name} · ${formatDateTime(item.signed_at)}`
                          : `draft by ${item.author_name} · ${formatDateTime(item.created_at)}`}
                      </p>
                    </button>
                    <Badge variant={item.status === "signed" ? "success" : "warning"} size="sm">
                      {item.status === "signed" ? "Signed" : "Draft"}
                    </Badge>
                    {consent && item.status === "signed" && (
                      item.paper_signed_at ? (
                        <span className="flex items-center gap-1 text-xs text-pine">
                          <CheckCircle2 className="h-3.5 w-3.5" /> Signed copy on file
                        </span>
                      ) : mayRecordPaper(user?.role) ? (
                        <span className="flex gap-1">
                          <Button size="sm" variant="outline" disabled={busy !== null}
                                  onClick={() => { setScanFor(item.id); scanInput.current?.click(); }}>
                            {busy === item.id && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                            Attach signed scan
                          </Button>
                          <Button size="sm" variant="ghost" disabled={busy !== null}
                                  onClick={() => void paperSigned(item.id)}>
                            Received, no scan
                          </Button>
                        </span>
                      ) : (
                        <span className="text-xs text-marigold-deep">Awaiting patient&apos;s signature</span>
                      )
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <input
        ref={scanInput}
        type="file"
        accept="application/pdf,image/*"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void attachScan(file);
          else setScanFor(null);
        }}
      />

      {opened && (
        <div className="space-y-3">
          {familyOf[opened.document_type] === "consent" && <Wording documentType={opened.document_type} />}
          <VisitPad key={opened.id} documentId={opened.id} onChanged={() => void load()} />
        </div>
      )}
    </div>
  );
}
