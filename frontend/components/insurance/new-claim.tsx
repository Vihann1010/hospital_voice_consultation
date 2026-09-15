"use client";

/**
 * Opening a claim: find the patient, pick or add their policy, and say which
 * admission or bill it is for.
 */
import { FormEvent, useCallback, useState } from "react";
import { Loader2, Plus, Search } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { PatientListItem } from "@/lib/types/core";
import type { InsuranceOptions, PatientInsurance } from "@/lib/types/insurance";
import { CLAIM_STATUS_LABEL, PAYER_TYPE_LABEL, statusClass } from "@/lib/types/insurance";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import { formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const SELECT = "h-9 rounded-md border border-border bg-white px-2 text-sm text-ink";

const EMPTY_POLICY = {
  organisation_id: "", payer_type: "insurance", insurer_name: "", tpa_name: "", policy_number: "", member_id: "",
  scheme_name: "", valid_from: "", valid_to: "", sum_insured: "",
};

export function NewClaim({ options, onOpened }: { options: InsuranceOptions | null; onOpened: (claimId: string) => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<PatientListItem[] | null>(null);
  const [context, setContext] = useState<PatientInsurance | null>(null);
  const [policyForm, setPolicyForm] = useState<typeof EMPTY_POLICY | null>(null);
  const [claim, setClaim] = useState({ policy_id: "", admission_id: "", invoice_id: "", external_reference: "", diagnosis: "", treatment_summary: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openPatient = useCallback(async (patientId: string) => {
    setError(null);
    try {
      const found = await staffApi.patientInsurance(patientId);
      setContext(found);
      setResults(null);
      const active = found.policies.filter((p) => p.is_active);
      setClaim({ policy_id: active.length === 1 ? active[0].id : "", admission_id: "", invoice_id: "", external_reference: "",
                 diagnosis: "", treatment_summary: "" });
      setPolicyForm(found.policies.length === 0 ? { ...EMPTY_POLICY } : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The patient could not be loaded.");
    }
  }, []);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (q.trim().length < 2) return;
    setError(null);
    try {
      setResults((await staffApi.patients({ q: q.trim(), limit: 10 })).items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    }
  }

  async function savePolicy() {
    if (!context || !policyForm) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await staffApi.savePolicy({
        patient_id: context.patient.id, organisation_id: policyForm.organisation_id || null,
        payer_type: policyForm.payer_type, insurer_name: policyForm.insurer_name.trim(),
        tpa_name: policyForm.tpa_name.trim() || null, policy_number: policyForm.policy_number.trim(),
        member_id: policyForm.member_id.trim() || null, scheme_name: policyForm.scheme_name.trim() || null,
        valid_from: policyForm.valid_from || null, valid_to: policyForm.valid_to || null,
        sum_insured_paise: policyForm.sum_insured ? rupeesToPaise(policyForm.sum_insured) : null,
      });
      await openPatient(context.patient.id);
      setClaim((current) => ({ ...current, policy_id: saved.id }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The policy could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function open() {
    setBusy(true);
    setError(null);
    try {
      const opened = await staffApi.openClaim({
        policy_id: claim.policy_id, admission_id: claim.admission_id || null, invoice_id: claim.invoice_id || null,
        external_reference: claim.external_reference.trim() || null, diagnosis: claim.diagnosis.trim() || null,
        treatment_summary: claim.treatment_summary.trim() || null,
      });
      onOpened(opened.id);
      setContext(null);
      setQ("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The claim could not be opened.");
    } finally {
      setBusy(false);
    }
  }

  const setPolicy = (patch: Partial<typeof EMPTY_POLICY>) => policyForm && setPolicyForm({ ...policyForm, ...patch });

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-clay">{error}</p>}
      <Card>
        <CardHeader className="pb-2"><CardTitle>Patient</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          <form onSubmit={search} className="flex max-w-lg gap-2">
            <Input placeholder="Name, phone or UHID" value={q} onChange={(e) => setQ(e.target.value)} />
            <Button type="submit" size="sm" variant="outline"><Search className="h-4 w-4" /> Find</Button>
          </form>
          {results && results.length === 0 && <p className="text-ink-muted">No patient found.</p>}
          {results && results.length > 0 && (
            <ul className="max-w-lg divide-y divide-border rounded-lg border border-border">
              {results.map((p) => (
                <li key={p.id}>
                  <button className="w-full px-3 py-2 text-left hover:bg-pine/5" onClick={() => void openPatient(p.id)}>
                    <span className="font-medium">{p.name}</span>
                    <span className="ml-2 text-xs text-ink-muted">{p.age} y · {p.gender} · {p.phone_number}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {context && (
            <p>
              <span className="font-medium">{context.patient.name}</span>
              {context.patient.uhid && <span className="ml-2 text-xs text-ink-muted">{context.patient.uhid}</span>}
            </p>
          )}
        </CardContent>
      </Card>

      {context && (
        <>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle>Policy</CardTitle>
              {!policyForm && (
                <Button size="sm" variant="outline" onClick={() => setPolicyForm({ ...EMPTY_POLICY })}>
                  <Plus className="h-4 w-4" /> Add policy
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {context.policies.length === 0 && !policyForm && <p className="text-ink-muted">No policy on record.</p>}
              {context.policies.map((p) => (
                <label key={p.id} className={`flex items-start gap-2 rounded-lg border border-border px-3 py-2 ${p.is_active ? "" : "opacity-60"}`}>
                  <input type="radio" name="policy" disabled={!p.is_active} checked={claim.policy_id === p.id}
                         onChange={() => setClaim({ ...claim, policy_id: p.id })} className="mt-1" />
                  <span>
                    <span className="font-medium">{p.insurer_name}</span>
                    {p.tpa_name && <span className="text-ink-muted"> via {p.tpa_name}</span>}
                    <span className="block text-xs text-ink-muted">
                      {PAYER_TYPE_LABEL[p.payer_type] ?? p.payer_type} · Policy {p.policy_number}
                      {p.member_id ? ` · Member ${p.member_id}` : ""}
                      {p.valid_from || p.valid_to ? ` · ${formatDate(p.valid_from) || "…"} to ${formatDate(p.valid_to) || "…"}` : ""}
                      {p.sum_insured_paise != null ? ` · Sum insured ${formatINR(p.sum_insured_paise)}` : ""}
                      {!p.is_active ? " · Not in use" : ""}
                    </span>
                  </span>
                </label>
              ))}

              {policyForm && (
                <div className="space-y-2 rounded-lg border border-border p-3">
                  <div className="grid gap-2 sm:grid-cols-3">
                    <label className="space-y-1"><span className="text-xs text-ink-muted">Payer in the register (optional)</span>
                      <select className={`${SELECT} w-full`} value={policyForm.organisation_id} onChange={(e) => {
                        const org = options?.payers.find((p) => p.id === e.target.value);
                        setPolicy({
                          organisation_id: e.target.value,
                          payer_type: org && org.payer_type !== "self_pay" ? org.payer_type : policyForm.payer_type,
                          tpa_name: org && org.payer_type === "tpa" && !policyForm.tpa_name ? org.name : policyForm.tpa_name,
                          insurer_name: org && org.payer_type !== "tpa" && !policyForm.insurer_name ? org.name : policyForm.insurer_name,
                        });
                      }}>
                        <option value="">Not in the register</option>
                        {options?.payers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </select></label>
                    <label className="space-y-1"><span className="text-xs text-ink-muted">Kind of payer</span>
                      <select className={`${SELECT} w-full`} value={policyForm.payer_type} onChange={(e) => setPolicy({ payer_type: e.target.value })}>
                        {(options?.payer_types ?? Object.keys(PAYER_TYPE_LABEL)).map((t) => (
                          <option key={t} value={t}>{PAYER_TYPE_LABEL[t] ?? t}</option>
                        ))}
                      </select></label>
                    <label className="space-y-1"><span className="text-xs text-ink-muted">Insurer (as on the card)</span>
                      <Input value={policyForm.insurer_name} onChange={(e) => setPolicy({ insurer_name: e.target.value })} /></label>
                    <label className="space-y-1"><span className="text-xs text-ink-muted">TPA</span>
                      <Input value={policyForm.tpa_name} onChange={(e) => setPolicy({ tpa_name: e.target.value })} /></label>
                    <label className="space-y-1"><span className="text-xs text-ink-muted">Policy number</span>
                      <Input value={policyForm.policy_number} onChange={(e) => setPolicy({ policy_number: e.target.value })} /></label>
                    <label className="space-y-1"><span className="text-xs text-ink-muted">Member / card ID</span>
                      <Input value={policyForm.member_id} onChange={(e) => setPolicy({ member_id: e.target.value })} /></label>
                    <label className="space-y-1"><span className="text-xs text-ink-muted">Scheme (e.g. Ayushman Bharat)</span>
                      <Input value={policyForm.scheme_name} onChange={(e) => setPolicy({ scheme_name: e.target.value })} /></label>
                    <label className="space-y-1"><span className="text-xs text-ink-muted">Valid from</span>
                      <Input type="date" value={policyForm.valid_from} onChange={(e) => setPolicy({ valid_from: e.target.value })} /></label>
                    <label className="space-y-1"><span className="text-xs text-ink-muted">Valid to</span>
                      <Input type="date" value={policyForm.valid_to} onChange={(e) => setPolicy({ valid_to: e.target.value })} /></label>
                    <label className="space-y-1"><span className="text-xs text-ink-muted">Sum insured (Rs)</span>
                      <Input inputMode="decimal" value={policyForm.sum_insured} onChange={(e) => setPolicy({ sum_insured: e.target.value })} /></label>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" disabled={busy || !policyForm.insurer_name.trim() || !policyForm.policy_number.trim()}
                            onClick={() => void savePolicy()}>
                      {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save policy
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setPolicyForm(null)}>Cancel</Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle>What the claim is for</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="space-y-1"><span className="text-xs text-ink-muted">Admission</span>
                  <select className={`${SELECT} w-full`} value={claim.admission_id} onChange={(e) => {
                    const admission = context.admissions.find((a) => a.id === e.target.value);
                    setClaim({ ...claim, admission_id: e.target.value, invoice_id: admission?.final_invoice_id ?? claim.invoice_id });
                  }}>
                    <option value="">Not for an admission</option>
                    {context.admissions.map((a) => (
                      <option key={a.id} value={a.id}>{a.ip_number} · admitted {formatDate(a.admitted_at)} · {a.status.replace(/_/g, " ")}</option>
                    ))}
                  </select></label>
                <label className="space-y-1"><span className="text-xs text-ink-muted">Bill</span>
                  <select className={`${SELECT} w-full`} value={claim.invoice_id} onChange={(e) => setClaim({ ...claim, invoice_id: e.target.value })}>
                    <option value="">No bill yet (pre-authorisation)</option>
                    {context.bills.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.invoice_number}{b.admission_ip_number ? ` (${b.admission_ip_number})` : ""} · {formatINR(b.total_paise)} · owes {formatINR(b.balance_paise)}
                      </option>
                    ))}
                  </select></label>
                <label className="space-y-1"><span className="text-xs text-ink-muted">Payer&apos;s reference, if already issued</span>
                  <Input value={claim.external_reference} onChange={(e) => setClaim({ ...claim, external_reference: e.target.value })} /></label>
                <label className="space-y-1"><span className="text-xs text-ink-muted">Diagnosis</span>
                  <Input value={claim.diagnosis} onChange={(e) => setClaim({ ...claim, diagnosis: e.target.value })} /></label>
                <label className="space-y-1 sm:col-span-2"><span className="text-xs text-ink-muted">Treatment summary</span>
                  <Input value={claim.treatment_summary} onChange={(e) => setClaim({ ...claim, treatment_summary: e.target.value })} /></label>
              </div>
              <Button size="sm" disabled={busy || !claim.policy_id} onClick={() => void open()}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Open claim
              </Button>
              {!claim.policy_id && <p className="text-xs text-ink-muted">Choose or add a policy first.</p>}
            </CardContent>
          </Card>

          {context.claims.length > 0 && (
            <Card>
              <CardHeader className="pb-2"><CardTitle>This patient&apos;s claims</CardTitle></CardHeader>
              <CardContent>
                <ul className="divide-y divide-border text-sm">
                  {context.claims.map((c) => (
                    <li key={c.id} className="flex flex-wrap items-center gap-3 py-2">
                      <button className="font-mono text-xs text-pine hover:underline" onClick={() => onOpened(c.id)}>{c.claim_number}</button>
                      <span className={statusClass(c.status)}>{CLAIM_STATUS_LABEL[c.status]}</span>
                      <span className="text-ink-muted">{c.payer_name}</span>
                      <span className="ml-auto">{formatINR(c.approved_paise || c.claimed_paise)}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
