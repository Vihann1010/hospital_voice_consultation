"use client";

/** TPA and insurance claims: the working list, opening a claim, and what payers owe. */
import { useCallback, useEffect, useState } from "react";
import { staffApi } from "@/lib/staffApi";
import type { Claim, InsuranceOptions, PayerOutstanding } from "@/lib/types/insurance";
import { CLAIM_STATUS_LABEL, canRecordSettlements, statusClass } from "@/lib/types/insurance";
import { formatINR } from "@/lib/types/emr";
import { formatDate, hospitalToday } from "@/lib/format";
import { useAuth } from "@/components/dashboard/auth-provider";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ClaimDetailPanel } from "@/components/insurance/claim-detail";
import { NewClaim } from "@/components/insurance/new-claim";

const SELECT = "h-9 rounded-md border border-border bg-white px-2 text-sm text-ink";

export function ClaimsWorkspace() {
  const { user } = useAuth();
  const canSettle = canRecordSettlements(user?.role);
  const [tab, setTab] = useState("claims");
  const [openId, setOpenId] = useState<string | null>(null);
  const [options, setOptions] = useState<InsuranceOptions | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    staffApi.insuranceOptions().then(setOptions).catch(() => setOptions(null));
  }, []);

  const open = (id: string) => {
    setOpenId(id);
    setTab("claims");
    setVersion((v) => v + 1);
  };

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList className="mb-4 w-fit">
        <TabsTrigger value="claims">Claims</TabsTrigger>
        <TabsTrigger value="new">New claim</TabsTrigger>
        <TabsTrigger value="owed">Payers owe</TabsTrigger>
      </TabsList>
      <TabsContent value="claims">
        <div className={openId ? "grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,600px)]" : ""}>
          <ClaimsList options={options} version={version} openId={openId} onOpen={setOpenId} />
          {openId && (
            <ClaimDetailPanel claimId={openId} canSettle={canSettle}
                              onChanged={() => setVersion((v) => v + 1)} onClose={() => setOpenId(null)} />
          )}
        </div>
      </TabsContent>
      <TabsContent value="new">
        <NewClaim options={options} onOpened={open} />
      </TabsContent>
      <TabsContent value="owed">
        <PayersOwe version={version} onOpen={open} />
      </TabsContent>
    </Tabs>
  );
}

function ClaimsList({
  options, version, openId, onOpen,
}: { options: InsuranceOptions | null; version: number; openId: string | null; onOpen: (id: string) => void }) {
  const [status, setStatus] = useState("open");
  const [payer, setPayer] = useState("");
  const [q, setQ] = useState("");
  const [claims, setClaims] = useState<Claim[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setClaims(await staffApi.claims({ status: status || undefined, organisation_id: payer || undefined, q: q.trim() || undefined }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Claims could not be loaded.");
    }
  }, [status, payer, q]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), q ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, q, version]);

  const owed = (claims ?? []).reduce((sum, c) => sum + c.outstanding_paise, 0);

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 pb-2">
        <CardTitle>Claims</CardTitle>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <select className={SELECT} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Stage">
            <option value="open">Open</option>
            <option value="">All</option>
            {(options?.statuses ?? []).map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <select className={SELECT} value={payer} onChange={(e) => setPayer(e.target.value)} aria-label="Payer">
            <option value="">Every payer</option>
            {(options?.payers ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <Input className="h-9 w-52" placeholder="Claim, patient, UHID, IP no." value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </CardHeader>
      <CardContent>
        {error && <p className="text-sm text-clay">{error}</p>}
        {claims && claims.length === 0 && <p className="text-sm text-ink-muted">No claims match.</p>}
        {claims && claims.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-left text-xs text-ink-muted">
                <tr>
                  <th className="py-2 pr-3">Claim</th>
                  <th className="py-2 pr-3">Patient</th>
                  <th className="py-2 pr-3">Payer</th>
                  <th className="py-2 pr-3">Stage</th>
                  <th className="py-2 pr-3 text-right">Claimed</th>
                  <th className="py-2 pr-3 text-right">Approved</th>
                  <th className="py-2 pr-3 text-right">Payer owes</th>
                  <th className="py-2 text-right">Days</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {claims.map((c) => (
                  <tr key={c.id} onClick={() => onOpen(c.id)}
                      className={`cursor-pointer hover:bg-pine/5 ${openId === c.id ? "bg-pine/5" : ""}`}>
                    <td className="py-2 pr-3 font-mono text-xs">
                      {c.claim_number}
                      {c.attention.length > 0 && <span className="ml-1 text-clay" title={c.attention.join(" ")}>!</span>}
                    </td>
                    <td className="py-2 pr-3">
                      {c.patient.name}
                      <span className="block text-xs text-ink-muted">
                        {[c.patient.uhid, c.admission?.ip_number, c.invoice?.invoice_number].filter(Boolean).join(" · ")}
                      </span>
                    </td>
                    <td className="py-2 pr-3">{c.payer_name}</td>
                    <td className={`py-2 pr-3 ${statusClass(c.status)}`}>{CLAIM_STATUS_LABEL[c.status]}</td>
                    <td className="py-2 pr-3 text-right">{formatINR(c.claimed_paise)}</td>
                    <td className="py-2 pr-3 text-right">{formatINR(c.approved_paise)}</td>
                    <td className="py-2 pr-3 text-right">{formatINR(c.outstanding_paise)}</td>
                    <td className="py-2 text-right">{c.age_days}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-border text-xs text-ink-muted">
                  <td className="py-2" colSpan={6}>{claims.length} claim{claims.length === 1 ? "" : "s"}</td>
                  <td className="py-2 pr-3 text-right font-medium text-ink">{formatINR(owed)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PayersOwe({ version, onOpen }: { version: number; onOpen: (id: string) => void }) {
  const [asOf, setAsOf] = useState(hospitalToday());
  const [data, setData] = useState<PayerOutstanding | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    staffApi.payerOutstanding(asOf).then((found) => { setData(found); setError(null); })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not be loaded."));
  }, [asOf, version]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm">
        <span className="text-ink-muted">As on</span>
        <Input type="date" className="h-9 w-44" max={hospitalToday()} value={asOf} onChange={(e) => setAsOf(e.target.value || hospitalToday())} />
      </div>
      {error && <p className="text-sm text-clay">{error}</p>}
      {data && (
        <>
          <Card>
            <CardHeader className="pb-2"><CardTitle>By payer — {formatINR(data.total_paise)} owed</CardTitle></CardHeader>
            <CardContent>
              {data.payers.length === 0 ? (
                <p className="text-sm text-ink-muted">No payer owes anything on claims put on bills.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] text-sm">
                    <thead className="text-left text-xs text-ink-muted">
                      <tr>
                        <th className="py-2 pr-3">Payer</th>
                        <th className="py-2 pr-3 text-right">Claims</th>
                        {data.buckets.map((b) => <th key={b} className="py-2 pr-3 text-right">{b}</th>)}
                        <th className="py-2 text-right">Owes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {data.payers.map((p) => (
                        <tr key={p.payer_name}>
                          <td className="py-2 pr-3">{p.payer_name}</td>
                          <td className="py-2 pr-3 text-right">{p.claims}</td>
                          {data.buckets.map((b) => (
                            <td key={b} className="py-2 pr-3 text-right">{Number(p[b]) ? formatINR(Number(p[b])) : "—"}</td>
                          ))}
                          <td className="py-2 text-right font-medium">{formatINR(p.outstanding_paise)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
          {data.items.length > 0 && (
            <Card>
              <CardHeader className="pb-2"><CardTitle>Claims waiting for payment</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] text-sm">
                    <thead className="text-left text-xs text-ink-muted">
                      <tr>
                        <th className="py-2 pr-3">Claim</th>
                        <th className="py-2 pr-3">Patient</th>
                        <th className="py-2 pr-3">Payer</th>
                        <th className="py-2 pr-3">On the bill since</th>
                        <th className="py-2 pr-3 text-right">Days</th>
                        <th className="py-2 text-right">Owes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {data.items.map((item) => (
                        <tr key={item.claim_id} className="cursor-pointer hover:bg-pine/5" onClick={() => onOpen(item.claim_id)}>
                          <td className="py-2 pr-3 font-mono text-xs">{item.claim_number}</td>
                          <td className="py-2 pr-3">{item.patient_name}</td>
                          <td className="py-2 pr-3">{item.payer_name}</td>
                          <td className="py-2 pr-3">{formatDate(item.booked_on)}</td>
                          <td className="py-2 pr-3 text-right">{item.age_days}</td>
                          <td className="py-2 text-right">{formatINR(item.outstanding_paise)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
