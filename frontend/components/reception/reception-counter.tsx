"use client";

/**
 * The reception counter.
 *
 * Built around what actually happens at the desk: a patient arrives, is found
 * or registered, is billed, pays, and is sent in with a token. That is one
 * continuous action, so it is one screen and — importantly — one transaction
 * on the server. A visit with no bill, or a bill with no payment recorded, is
 * exactly the mess that gets reconciled by hand at closing time.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  Banknote, Check, Loader2, Plus, Printer, Search, Stethoscope, Trash2, UserPlus, X,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type {
  PatientCard, PaymentMode, RegisterAndBillResult, ServiceItem, VisitType,
} from "@/lib/emrTypes";
import { PAYMENT_MODES, VISIT_TYPES, formatINR, rupeesToPaise } from "@/lib/emrTypes";
import type { Department, Gender } from "@/lib/types";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface BillLine {
  key: string;
  service: ServiceItem;
  quantity: number;
}

let lineKey = 0;

export function ReceptionCounter() {
  const router = useRouter();
  const toast = useToast();

  const [services, setServices] = useState<ServiceItem[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PatientCard[] | null>(null);
  const [selected, setSelected] = useState<PatientCard | null>(null);
  const [registering, setRegistering] = useState(false);

  // New patient fields
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<Gender>("female");
  const [phone, setPhone] = useState("");
  const [city, setCity] = useState("");

  // Visit
  const [department, setDepartment] = useState<Department>("orthopedics");
  const [visitType, setVisitType] = useState<VisitType>("new");

  // Bill
  const [lines, setLines] = useState<BillLine[]>([]);
  const [discountRupees, setDiscountRupees] = useState("");
  const [discountReason, setDiscountReason] = useState("");

  // Payment
  const [collectNow, setCollectNow] = useState(true);
  const [mode, setMode] = useState<PaymentMode>("cash");
  const [reference, setReference] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<RegisterAndBillResult | null>(null);

  useEffect(() => {
    staffApi.serviceItems().then(setServices).catch(() => setServices([]));
  }, []);

  // Search as they type; an exact UHID returns a single hit.
  useEffect(() => {
    if (query.trim().length < 2) {
      setResults(null);
      return;
    }
    const timer = setTimeout(() => {
      staffApi
        .searchCounterPatients(query.trim())
        .then(setResults)
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  // Default the consultation fee to the department and visit type chosen, so
  // the common case needs no thought at the counter.
  useEffect(() => {
    if (services.length === 0) return;
    const suffix = visitType === "new" ? "NEW" : "FUP";
    const code = `OPD-${department === "orthopedics" ? "ORT" : "GYN"}-${suffix}`;
    const consultation = services.find((item) => item.code === code);
    if (!consultation) return;

    setLines((current) => {
      const withoutConsultation = current.filter(
        (line) => line.service.category !== "consultation"
      );
      return [
        { key: `line-${++lineKey}`, service: consultation, quantity: 1 },
        ...withoutConsultation,
      ];
    });
  }, [services, department, visitType]);

  const discountPaise = rupeesToPaise(discountRupees || "0");
  const grossPaise = useMemo(
    () => lines.reduce((sum, line) => sum + line.service.rate_paise * line.quantity, 0),
    [lines]
  );
  // Tax follows the discounted value, matching the server's arithmetic.
  const taxPaise = useMemo(() => {
    if (grossPaise === 0) return 0;
    return lines.reduce((sum, line) => {
      const lineGross = line.service.rate_paise * line.quantity;
      const share = Math.round((discountPaise * lineGross) / grossPaise);
      const taxable = lineGross - share;
      return sum + Math.round((taxable * line.service.tax_percent) / 100);
    }, 0);
  }, [lines, discountPaise, grossPaise]);
  const totalPaise = Math.max(grossPaise - discountPaise, 0) + taxPaise;

  const canSubmit =
    lines.length > 0 &&
    totalPaise >= 0 &&
    discountPaise <= grossPaise &&
    (selected !== null || (name.trim() && age && phone.trim().length >= 10));

  const reset = useCallback(() => {
    setDone(null); setSelected(null); setQuery(""); setResults(null);
    setRegistering(false); setName(""); setAge(""); setPhone(""); setCity("");
    setLines([]); setDiscountRupees(""); setDiscountReason("");
    setReference(""); setError(null);
  }, []);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        department,
        visit_type: visitType,
        items: lines.map((line) => ({
          service_item_id: line.service.id,
          quantity: line.quantity,
        })),
        invoice_discount_paise: discountPaise,
        discount_reason: discountPaise > 0 ? discountReason || "Counter discount" : null,
      };
      if (selected) {
        payload.patient_id = selected.id;
      } else {
        payload.new_patient = {
          name: name.trim(),
          age: Number(age),
          gender,
          phone_number: phone.trim(),
          city: city.trim() || null,
        };
      }
      if (collectNow && totalPaise > 0) {
        payload.payment = {
          amount_paise: totalPaise,
          mode,
          reference: reference.trim() || null,
        };
      }

      const result = await staffApi.registerAndBill(payload);
      setDone(result);
      toast.success(
        `${result.patient.uhid} · Token ${result.visit.token_number}`,
        `${result.invoice.invoice_number} — ${formatINR(result.invoice.total_paise)}`
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not complete registration.";
      setError(message);
      toast.error("Registration failed", message);
    } finally {
      setSubmitting(false);
    }
  }

  // ---------------------------------------------------------------- done
  if (done) {
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <Card className="border-pine/20">
          <CardContent className="p-6">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-pine text-mint">
                <Check className="h-5 w-5" />
              </span>
              <div>
                <p className="font-display text-lg font-semibold text-pine">
                  {done.patient.name} registered
                </p>
                <p className="text-sm text-ink-muted">
                  {done.patient.uhid} · {done.visit.visit_number}
                </p>
              </div>
              <div className="ml-auto text-right">
                <p className="text-[11px] uppercase tracking-wide text-ink-faint">Token</p>
                <p className="tabular font-display text-3xl font-semibold text-marigold-deep">
                  {done.visit.token_number}
                </p>
              </div>
            </div>

            <div className="mt-5 rounded-xl bg-mint p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-ink-muted">{done.invoice.invoice_number}</span>
                <span className="tabular font-display text-xl font-semibold text-pine">
                  {formatINR(done.invoice.total_paise)}
                </span>
              </div>
              <p className="mt-1 text-xs text-ink-faint">
                {done.payment
                  ? `Paid by ${done.payment.mode} · receipt ${done.payment.receipt_number}`
                  : `Unpaid — balance ${formatINR(done.invoice.total_paise - done.invoice.paid_paise)}`}
              </p>
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              <Button onClick={() => window.print()} variant="outline">
                <Printer /> Print bill
              </Button>
              <Button
                onClick={() =>
                  router.push(`/?visit=${done.visit.id}&patient=${done.patient.id}`)
                }
              >
                <Stethoscope /> Start voice consultation
              </Button>
              <Button variant="ghost" onClick={reset}>
                Next patient
              </Button>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    );
  }

  // -------------------------------------------------------------- counter
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
      <div className="space-y-5">
        {/* Patient */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Patient</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {selected ? (
              <div className="flex items-center gap-3 rounded-lg bg-mint px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-pine">{selected.name}</p>
                  <p className="text-xs text-ink-muted">
                    {selected.uhid} · {selected.age} yrs · {selected.gender} ·{" "}
                    {selected.phone_number}
                  </p>
                </div>
                <button
                  onClick={() => setSelected(null)}
                  className="rounded p-1 text-ink-faint hover:text-clay"
                  aria-label="Choose a different patient"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : registering ? (
              <div className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="field-label" htmlFor="rc-name">Full name</label>
                    <Input id="rc-name" value={name}
                           onChange={(e) => setName(e.target.value)} autoFocus />
                  </div>
                  <div>
                    <label className="field-label" htmlFor="rc-phone">Mobile number</label>
                    <Input id="rc-phone" value={phone} inputMode="numeric"
                           onChange={(e) => setPhone(e.target.value)} />
                  </div>
                  <div>
                    <label className="field-label" htmlFor="rc-age">Age</label>
                    <Input id="rc-age" value={age} inputMode="numeric"
                           onChange={(e) => setAge(e.target.value)} />
                  </div>
                  <div>
                    <label className="field-label" htmlFor="rc-gender">Gender</label>
                    <select id="rc-gender" value={gender} className="field-input"
                            onChange={(e) => setGender(e.target.value as Gender)}>
                      <option value="female">Female</option>
                      <option value="male">Male</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="field-label" htmlFor="rc-city">City (optional)</label>
                  <Input id="rc-city" value={city}
                         onChange={(e) => setCity(e.target.value)} />
                </div>
                <Button variant="ghost" size="sm" onClick={() => setRegistering(false)}>
                  Search for an existing patient instead
                </Button>
              </div>
            ) : (
              <>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
                  <Input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="UHID, mobile number or name"
                    className="pl-9"
                    autoFocus
                  />
                </div>

                <AnimatePresence>
                  {results !== null && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                      {results.length === 0 ? (
                        <p className="py-2 text-sm text-ink-muted">
                          No match. Register this patient as new.
                        </p>
                      ) : (
                        <ul className="divide-y divide-border rounded-lg border border-border">
                          {results.map((patient) => (
                            <li key={patient.id}>
                              <button
                                onClick={() => { setSelected(patient); setResults(null); setQuery(""); }}
                                className="w-full px-4 py-2.5 text-left transition hover:bg-mint"
                              >
                                <p className="text-sm font-medium text-ink">{patient.name}</p>
                                <p className="text-xs text-ink-faint">
                                  {patient.uhid} · {patient.age} yrs · {patient.phone_number}
                                </p>
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>

                <Button variant="outline" size="sm" onClick={() => setRegistering(true)}>
                  <UserPlus /> Register new patient
                </Button>
              </>
            )}
          </CardContent>
        </Card>

        {/* Visit */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Visit</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="field-label" htmlFor="rc-dept">Department</label>
              <select id="rc-dept" value={department} className="field-input"
                      onChange={(e) => setDepartment(e.target.value as Department)}>
                <option value="orthopedics">Trauma &amp; Orthopedics</option>
                <option value="gynecology">Maternity &amp; Gynecology</option>
              </select>
            </div>
            <div>
              <label className="field-label" htmlFor="rc-type">Visit type</label>
              <select id="rc-type" value={visitType} className="field-input"
                      onChange={(e) => setVisitType(e.target.value as VisitType)}>
                {VISIT_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
          </CardContent>
        </Card>

        {/* Charges */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Charges</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              {lines.map((line) => (
                <div key={line.key} className="flex items-center gap-2 rounded-lg bg-mint/60 px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-ink">{line.service.name}</p>
                    <p className="text-xs text-ink-faint">
                      {formatINR(line.service.rate_paise)} each
                    </p>
                  </div>
                  <input
                    type="number" min={1} max={99} value={line.quantity}
                    onChange={(e) =>
                      setLines((current) =>
                        current.map((item) =>
                          item.key === line.key
                            ? { ...item, quantity: Math.max(1, Number(e.target.value) || 1) }
                            : item
                        )
                      )
                    }
                    className="w-14 rounded border border-border px-2 py-1 text-center text-sm"
                    aria-label={`Quantity for ${line.service.name}`}
                  />
                  <span className="tabular w-24 text-right text-sm font-medium text-ink">
                    {formatINR(line.service.rate_paise * line.quantity)}
                  </span>
                  <button
                    onClick={() => setLines((c) => c.filter((i) => i.key !== line.key))}
                    className="rounded p-1 text-ink-faint hover:text-clay"
                    aria-label={`Remove ${line.service.name}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>

            <select
              value=""
              className="field-input"
              onChange={(e) => {
                const service = services.find((item) => item.id === e.target.value);
                if (service) {
                  setLines((current) => [
                    ...current,
                    { key: `line-${++lineKey}`, service, quantity: 1 },
                  ]);
                }
                e.target.value = "";
              }}
            >
              <option value="">+ Add a charge…</option>
              {services
                .filter((item) => !item.department || item.department === department)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} — {formatINR(item.rate_paise)}
                  </option>
                ))}
            </select>
          </CardContent>
        </Card>
      </div>

      {/* Total and payment */}
      <div className="space-y-4 lg:sticky lg:top-6 lg:self-start">
        <Card>
          <CardContent className="p-5">
            <dl className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <dt className="text-ink-muted">Subtotal</dt>
                <dd className="tabular text-ink">{formatINR(grossPaise)}</dd>
              </div>
              {discountPaise > 0 && (
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Discount</dt>
                  <dd className="tabular text-clay">−{formatINR(discountPaise)}</dd>
                </div>
              )}
              {taxPaise > 0 && (
                <div className="flex justify-between">
                  <dt className="text-ink-muted">GST</dt>
                  <dd className="tabular text-ink">{formatINR(taxPaise)}</dd>
                </div>
              )}
            </dl>
            <div className="mt-3 flex items-baseline justify-between border-t border-border pt-3">
              <span className="font-display font-semibold text-pine">Total</span>
              <span className="tabular font-display text-2xl font-semibold text-pine">
                {formatINR(totalPaise)}
              </span>
            </div>

            <div className="mt-4 space-y-2">
              <label className="field-label" htmlFor="rc-disc">Discount (₹)</label>
              <Input id="rc-disc" value={discountRupees} inputMode="decimal"
                     onChange={(e) => setDiscountRupees(e.target.value)} placeholder="0" />
              {discountPaise > grossPaise && (
                <p className="text-xs text-clay">
                  The discount is larger than the bill.
                </p>
              )}
              {discountPaise > 0 && (
                <Input value={discountReason}
                       onChange={(e) => setDiscountReason(e.target.value)}
                       placeholder="Reason for discount" />
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
            <Banknote className="h-4 w-4 text-pine" />
            <CardTitle>Payment</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" checked={collectNow}
                     onChange={(e) => setCollectNow(e.target.checked)} />
              Collect now
            </label>

            {collectNow && (
              <>
                <div className="grid grid-cols-3 gap-1.5">
                  {PAYMENT_MODES.filter((m) => m.value !== "insurance" && m.value !== "waiver")
                    .map((option) => (
                      <button
                        key={option.value}
                        onClick={() => setMode(option.value)}
                        className={cn(
                          "rounded-lg border px-2 py-2 text-xs font-medium transition",
                          mode === option.value
                            ? "border-pine bg-pine text-mint"
                            : "border-border text-ink-muted hover:bg-mint"
                        )}
                      >
                        {option.label}
                      </button>
                    ))}
                </div>
                {mode !== "cash" && (
                  <Input value={reference} onChange={(e) => setReference(e.target.value)}
                         placeholder="Reference / last 4 digits" />
                )}
              </>
            )}

            {error && (
              <p role="alert" className="rounded-md bg-clay/10 px-3 py-2 text-xs text-clay">
                {error}
              </p>
            )}

            <Button className="w-full" size="lg" disabled={!canSubmit || submitting}
                    onClick={submit}>
              {submitting ? <Loader2 className="animate-spin" /> : <Plus />}
              Register &amp; bill {totalPaise > 0 ? formatINR(totalPaise) : ""}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
