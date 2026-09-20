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
import { AnimatePresence, motion } from "framer-motion";
import {
  Banknote, Check, Loader2, Plus, Printer, Search, Trash2, UserPlus, Wallet, X,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { getToken } from "@/lib/auth";
import type {
  Organisation, PatientCard, PaymentMode, Quote, RegisterAndBillResult,
  ServiceItem, VisitType,
} from "@/lib/types/emr";
import type { Consultant } from "@/lib/types/appointments";
import {
  PAYMENT_MODES, VISIT_TYPES, formatINR, paiseToRupees, rupeesToPaise,
} from "@/lib/types/emr";
import {
  PaymentModeFields,
  cleanModeDetails,
} from "@/components/finance/payment-mode-fields";
import { WalletPanel } from "@/components/finance/wallet-panel";
import { DEPARTMENTS, type Department, type Gender } from "@/lib/types/core";
import { DEPARTMENT_CODE, DEPARTMENT_FULL_LABEL } from "@/lib/format";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/components/dashboard/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface BillLine {
  key: string;
  service: ServiceItem;
  quantity: number;
  /** What is being charged, in rupees, as typed. */
  rateRupees: string;
  /**
   * Whether the clerk changed the rate. Only an edited rate is sent as an
   * explicit price: an untouched line must stay open to the consultant's free
   * follow-up and the payer's agreed rate, and sending the tariff figure back
   * would stamp "price set at the counter" on every line and silence them.
   */
  rateEdited: boolean;
  /** A discount on this line alone, in rupees, as typed. */
  discountRupees: string;
  /** Why this charge reads as it does. Printed on the bill. */
  remark: string;
}

let lineKey = 0;

/** A fresh line at the tariff rate, with nothing written against it yet. */
function makeLine(service: ServiceItem): BillLine {
  return {
    key: `line-${++lineKey}`,
    service,
    quantity: 1,
    rateRupees: paiseToRupees(service.rate_paise),
    rateEdited: false,
    discountRupees: "",
    remark: "",
  };
}

const lineRate = (line: BillLine) =>
  line.rateEdited ? rupeesToPaise(line.rateRupees || "0") : line.service.rate_paise;
const lineGross = (line: BillLine) => lineRate(line) * line.quantity;
/** Never more than the line itself; the server refuses that too. */
const lineDiscount = (line: BillLine) =>
  Math.min(rupeesToPaise(line.discountRupees || "0"), lineGross(line));

export function ReceptionCounter() {
  const toast = useToast();
  const { user } = useAuth();
  // Returning a balance is money leaving the hospital, so the button only
  // appears for the roles that hold refund authority. The API enforces it
  // regardless; this just avoids offering an action that would 403.
  const canRefund = user?.role === "admin" || user?.role === "supervisor";

  const [services, setServices] = useState<ServiceItem[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PatientCard[] | null>(null);
  const [selected, setSelected] = useState<PatientCard | null>(null);
  const [registering, setRegistering] = useState(false);
  const [registeringOnly, setRegisteringOnly] = useState(false);

  // New patient fields
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<Gender>("female");
  const [phone, setPhone] = useState("");
  const [city, setCity] = useState("");

  // Visit
  const [department, setDepartment] = useState<Department>("orthopedics");
  const [visitType, setVisitType] = useState<VisitType>("new");
  // The counter used to send no doctor at all, which left every visit with a
  // blank doctor name on the queue board and meant the consultant's own
  // pricing rules — free follow-up, first consultation — could never fire.
  const [consultants, setConsultants] = useState<Consultant[]>([]);
  const [consultantId, setConsultantId] = useState("");
  const [organisations, setOrganisations] = useState<Organisation[]>([]);
  const [organisationId, setOrganisationId] = useState("");
  // What the server says this bill comes to, and why. Fetched rather than
  // computed here so the figure on screen is the figure that will be
  // charged.
  const [quote, setQuote] = useState<Quote | null>(null);

  // Bill
  const [lines, setLines] = useState<BillLine[]>([]);
  const [discountRupees, setDiscountRupees] = useState("");
  const [discountReason, setDiscountReason] = useState("");

  // Payment
  const [collectNow, setCollectNow] = useState(true);
  const [mode, setMode] = useState<PaymentMode>("cash");
  const [modeDetails, setModeDetails] = useState<Record<string, string>>({});
  // The selected patient's credit, so the counter can offer to spend it
  // rather than taking cash from somebody who has already paid.
  const [walletPaise, setWalletPaise] = useState(0);
  const [settling, setSettling] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [printing, setPrinting] = useState(false);
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
    const code = `OPD-${DEPARTMENT_CODE[department] ?? "GEN"}-${suffix}`;
    const consultation = services.find((item) => item.code === code);
    if (!consultation) return;

    setLines((current) => {
      const withoutConsultation = current.filter(
        (line) => line.service.category !== "consultation"
      );
      return [makeLine(consultation), ...withoutConsultation];
    });
  }, [services, department, visitType]);

  // The discount on the bill as a whole, on top of anything taken off a
  // single line.
  const billDiscountPaise = rupeesToPaise(discountRupees || "0");
  const grossPaise = useMemo(
    () => lines.reduce((sum, line) => sum + lineGross(line), 0),
    [lines]
  );
  const lineDiscountPaise = useMemo(
    () => lines.reduce((sum, line) => sum + lineDiscount(line), 0),
    [lines]
  );
  const afterLinesPaise = Math.max(grossPaise - lineDiscountPaise, 0);
  const discountPaise = lineDiscountPaise + Math.min(billDiscountPaise, afterLinesPaise);
  // Tax follows the discounted value, matching the server's arithmetic: the
  // line's own discount first, then its share of the bill discount.
  const taxPaise = useMemo(() => {
    if (afterLinesPaise === 0) return 0;
    return lines.reduce((sum, line) => {
      const net = lineGross(line) - lineDiscount(line);
      const share = Math.round((billDiscountPaise * net) / afterLinesPaise);
      return sum + Math.round(((net - share) * line.service.tax_percent) / 100);
    }, 0);
  }, [lines, billDiscountPaise, afterLinesPaise]);
  const totalPaise = Math.max(grossPaise - discountPaise, 0) + taxPaise;
  /**
   * The lines as the server wants them. An edited rate is sent explicitly, an
   * untouched one is left for the pricing rules to decide.
   */
  const billItems = useCallback(
    () =>
      lines.map((line) => ({
        service_item_id: line.service.id,
        quantity: line.quantity,
        ...(line.rateEdited ? { unit_rate_paise: lineRate(line) } : {}),
        ...(lineDiscount(line) > 0 ? { discount_paise: lineDiscount(line) } : {}),
        ...(line.remark.trim() ? { remark: line.remark.trim() } : {}),
      })),
    [lines]
  );

  const canSubmit =
    lines.length > 0 &&
    totalPaise >= 0 &&
    grossPaise > 0 &&
    billDiscountPaise <= afterLinesPaise &&
    (selected !== null || (name.trim() && age && phone.trim().length >= 10));

  const reset = useCallback(() => {
    setDone(null); setSelected(null); setQuery(""); setResults(null);
    setRegistering(false); setName(""); setAge(""); setPhone(""); setCity("");
    setLines([]); setDiscountRupees(""); setDiscountReason("");
    setModeDetails({}); setWalletPaise(0); setQuote(null);
    setOrganisationId(""); setError(null);
  }, []);

  // The wallet panel only exists while a patient is selected, so the
  // completed-sale screen reads the balance itself rather than trusting
  // whatever the panel last reported.
  useEffect(() => {
    if (!done) return;
    let active = true;
    void staffApi
      .wallet(done.patient.id)
      .then((wallet) => active && setWalletPaise(wallet.balance_paise))
      .catch(() => active && setWalletPaise(0));
    return () => {
      active = false;
    };
  }, [done]);

  useEffect(() => {
    void (async () => {
      try {
        const [people, orgs] = await Promise.all([
          staffApi.consultants({ active_only: true }),
          staffApi.organisations(true),
        ]);
        setConsultants(people);
        setOrganisations(orgs);
      } catch {
        // A counter that cannot reach the registers can still take money at
        // tariff rates; it must not refuse to open.
        setConsultants([]);
        setOrganisations([]);
      }
    })();
  }, []);

  const departmentConsultants = useMemo(
    () => consultants.filter((item) => item.department === department),
    [consultants, department]
  );

  // Follow the department unless the clerk has picked somebody in it.
  useEffect(() => {
    setConsultantId((current) =>
      departmentConsultants.some((item) => item.id === current)
        ? current
        : departmentConsultants[0]?.id ?? ""
    );
  }, [departmentConsultants]);

  const chosenConsultant = consultants.find((item) => item.id === consultantId);

  // Ask the server what this comes to whenever the bill changes. Debounced,
  // because it changes on every keystroke in the quantity box.
  useEffect(() => {
    if (lines.length === 0) {
      setQuote(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        setQuote(
          await staffApi.quoteBill({
            patient_id: selected?.id ?? null,
            consultant_id: consultantId || null,
            doctor_name: chosenConsultant?.full_name ?? null,
            organisation_id: organisationId || null,
            items: billItems(),
            invoice_discount_paise: billDiscountPaise,
          })
        );
      } catch {
        // Falls back to the locally computed total, which is right whenever
        // no rule applies — the common case.
        setQuote(null);
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [lines, billItems, selected, consultantId, chosenConsultant, organisationId,
      billDiscountPaise]);

  const canRegister = Boolean(name.trim() && age && phone.trim().length >= 10);


  /** Issue a UHID and nothing else. */
  async function registerOnly() {
    setRegisteringOnly(true);
    setError(null);
    try {
      const patient = await staffApi.registerPatient({
        name: name.trim(),
        age: Number(age),
        gender,
        phone_number: phone.trim(),
        city: city.trim() || null,
      });
      // Selected rather than cleared: the commonest next step is to bill the
      // person standing there, and making the clerk search for the record
      // they just created would be a pointless round trip.
      setSelected(patient);
      setRegistering(false);
      setName(""); setAge(""); setPhone(""); setCity("");
      toast.success(`${patient.uhid} registered`, "No visit opened and no bill raised.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not register the patient.";
      setError(message);
      toast.error("Registration failed", message);
    } finally {
      setRegisteringOnly(false);
    }
  }

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        department,
        visit_type: visitType,
        doctor_name: chosenConsultant?.full_name ?? "",
        organisation_id: organisationId || null,
        items: billItems(),
        invoice_discount_paise: billDiscountPaise,
        discount_reason:
          billDiscountPaise > 0 ? discountReason || "Counter discount" : null,
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
      // Collect what the server quoted, not what was computed locally: if a
      // rule zeroed a line, taking the local figure would collect money the
      // bill does not ask for.
      const payable = quote?.total_paise ?? totalPaise;
      if (collectNow && payable > 0) {
        payload.payment = {
          amount_paise: payable,
          mode,
          mode_details: cleanModeDetails(modeDetails),
        };
      }

      const result = await staffApi.registerAndBill(payload);
      setDone(result);
      window.dispatchEvent(new Event("reception-payment-recorded"));
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

  /** Spend the patient's credit against the bill just raised.
   *
   *  The counter tells the clerk they can do this, so it has to be one
   *  button away rather than a note about a screen somewhere else. Capped
   *  at whichever is smaller — the credit or what is still owed — because
   *  overpaying a bill from a wallet is refused by the API and there is no
   *  sense offering it.
   */
  async function settleFromWallet() {
    if (!done) return;
    const owed = done.invoice.total_paise - done.invoice.paid_paise;
    const spend = Math.min(owed, walletPaise);
    if (spend <= 0) return;
    setSettling(true);
    try {
      const payment = await staffApi.payFromWallet(done.invoice.id, spend);
      const invoice = await staffApi.invoice(done.invoice.id);
      setDone({ ...done, invoice, payment });
      const wallet = await staffApi.wallet(done.patient.id);
      setWalletPaise(wallet.balance_paise);
      window.dispatchEvent(new Event("reception-payment-recorded"));
      toast.success(
        `${formatINR(spend)} settled from the wallet`,
        `Receipt ${payment.receipt_number} · ${formatINR(wallet.balance_paise)} left on account`
      );
    } catch (err) {
      toast.error(
        "Could not settle from the wallet",
        err instanceof Error ? err.message : undefined
      );
    } finally {
      setSettling(false);
    }
  }

  /** Send a PDF straight to the printer through a hidden frame.
   *  Shared by the bill and the receipt: both are handed to the patient at
   *  the same moment, and duplicating the plumbing would mean fixing any
   *  printing bug twice. */
  async function printPdf(url: string, label: string) {
    setPrinting(true);
    try {
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${getToken() ?? ""}` },
      });
      if (!response.ok) throw new Error(`The ${label} PDF is not available yet.`);
      const blobUrl = URL.createObjectURL(await response.blob());
      const frame = document.createElement("iframe");
      frame.style.position = "fixed";
      frame.style.width = "0";
      frame.style.height = "0";
      frame.style.border = "0";
      frame.src = blobUrl;
      frame.onload = () => {
        frame.contentWindow?.focus();
        frame.contentWindow?.print();
        setTimeout(() => {
          frame.remove();
          URL.revokeObjectURL(blobUrl);
        }, 60000);
      };
      document.body.appendChild(frame);
    } catch (err) {
      toast.error(`Could not print the ${label}`, err instanceof Error ? err.message : undefined);
    } finally {
      setPrinting(false);
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

            {done.invoice.total_paise > done.invoice.paid_paise && walletPaise > 0 && (
              <button
                type="button"
                disabled={settling}
                onClick={() => void settleFromWallet()}
                className="mt-3 flex w-full items-center gap-2 rounded-xl border
                           border-marigold-deep/30 bg-marigold/10 px-4 py-2.5 text-left
                           text-sm text-marigold-deep transition hover:bg-marigold/20
                           disabled:opacity-60"
              >
                <Wallet className="h-4 w-4 shrink-0" />
                <span>
                  {settling ? "Settling…" : "Settle from wallet"} —{" "}
                  {formatINR(
                    Math.min(done.invoice.total_paise - done.invoice.paid_paise, walletPaise)
                  )}
                </span>
                <span className="ml-auto text-[11px]">
                  {formatINR(walletPaise)} on account
                </span>
              </button>
            )}

            <div className="mt-5 flex flex-wrap gap-2">
              <Button onClick={() => void printPdf(staffApi.invoicePdfUrl(done.invoice.id), "bill")} variant="outline" disabled={printing}>
                <Printer /> {printing ? "Preparing bill..." : "Print bill"}
              </Button>
              {done.payment && (
                <Button
                  variant="outline"
                  onClick={() =>
                    void printPdf(staffApi.receiptPdfUrl(done.payment!.id), "receipt")
                  }
                >
                  <Printer /> Print receipt
                </Button>
              )}
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
    <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
      <div className="space-y-5">
        {/* Patient */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Patient</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {selected ? (
              <>
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
              {/* Shown the moment a patient is chosen. Taking cash from
                  somebody who already has credit on account is the
                  expensive mistake here, and it is only avoidable if the
                  balance is in front of the clerk before they ask. */}
              <WalletPanel
                patientId={selected.id}
                canWithdraw={canRefund}
                onChanged={setWalletPaise}
                className="mt-3"
              />
              </>
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
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="ghost" size="sm" onClick={() => setRegistering(false)}>
                    Search for an existing patient instead
                  </Button>
                  {/* Registration and attendance are not the same act. Somebody
                      who rings for a card, or is being registered so an
                      appointment can be booked, must not take a token in
                      today's queue or appear on the doctor's list. */}
                  <Button
                    variant="outline"
                    size="sm"
                    className="ml-auto"
                    disabled={registeringOnly || !canRegister}
                    onClick={() => void registerOnly()}
                  >
                    {registeringOnly ? <Loader2 className="animate-spin" /> : <UserPlus />}
                    Register only — no bill or token
                  </Button>
                </div>
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
                {DEPARTMENTS.map((d) => (
                  <option key={d} value={d}>{DEPARTMENT_FULL_LABEL[d] ?? d}</option>
                ))}
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
            <div>
              <label className="field-label" htmlFor="rc-consultant">Consultant</label>
              <select id="rc-consultant" value={consultantId} className="field-input"
                      onChange={(e) => setConsultantId(e.target.value)}>
                {departmentConsultants.length === 0 && <option value="">—</option>}
                {departmentConsultants.map((item) => (
                  <option key={item.id} value={item.id}>{item.full_name}</option>
                ))}
              </select>
            </div>
            <div>
              {/* Only shown when the hospital actually has agreements. Most
                  patients pay for themselves, and an empty dropdown on every
                  registration is a field to skip past all day. */}
              {organisations.length > 0 && (
                <>
                  <label className="field-label" htmlFor="rc-org">Paid by</label>
                  <select id="rc-org" value={organisationId} className="field-input"
                          onChange={(e) => setOrganisationId(e.target.value)}>
                    <option value="">Patient (self-pay)</option>
                    {organisations.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </>
              )}
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
              {lines.map((line) => {
                const gross = lineGross(line);
                const discount = lineDiscount(line);
                const typedDiscount = rupeesToPaise(line.discountRupees || "0");
                const edit = (patch: Partial<BillLine>) =>
                  setLines((current) =>
                    current.map((item) =>
                      item.key === line.key ? { ...item, ...patch } : item
                    )
                  );
                return (
                  <div key={line.key} className="rounded-lg bg-mint/60 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <p className="min-w-0 flex-1 truncate text-sm text-ink">
                        {line.service.name}
                      </p>
                      <span className="tabular w-24 text-right text-sm font-medium text-ink">
                        {formatINR(Math.max(gross - discount, 0))}
                      </span>
                      <button
                        onClick={() => setLines((c) => c.filter((i) => i.key !== line.key))}
                        className="rounded p-1 text-ink-faint hover:text-clay"
                        aria-label={`Remove ${line.service.name}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    {/* Rate, quantity and a discount on this charge alone. The
                        rate is editable because the counter is regularly told
                        to charge something other than the list price, and a
                        clerk who cannot do it here does it on paper. */}
                    <div className="mt-2 flex flex-wrap items-end gap-2">
                      <div>
                        <label className="text-[11px] text-ink-faint"
                               htmlFor={`${line.key}-rate`}>
                          Rate (&#8377;)
                        </label>
                        <input
                          id={`${line.key}-rate`} inputMode="decimal"
                          value={line.rateRupees}
                          onChange={(e) =>
                            edit({ rateRupees: e.target.value, rateEdited: true })
                          }
                          className="block w-20 rounded border border-border px-2 py-1 text-right text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-ink-faint"
                               htmlFor={`${line.key}-qty`}>
                          Qty
                        </label>
                        <input
                          id={`${line.key}-qty`} type="number" min={1} max={99}
                          value={line.quantity}
                          onChange={(e) =>
                            edit({ quantity: Math.max(1, Number(e.target.value) || 1) })
                          }
                          className="block w-14 rounded border border-border px-2 py-1 text-center text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-ink-faint"
                               htmlFor={`${line.key}-disc`}>
                          Discount (&#8377;)
                        </label>
                        <input
                          id={`${line.key}-disc`} inputMode="decimal"
                          value={line.discountRupees} placeholder="0"
                          onChange={(e) => edit({ discountRupees: e.target.value })}
                          className="block w-20 rounded border border-border px-2 py-1 text-right text-sm"
                        />
                      </div>
                      <div className="min-w-[8rem] flex-1">
                        <label className="text-[11px] text-ink-faint"
                               htmlFor={`${line.key}-remark`}>
                          Remark
                        </label>
                        <input
                          id={`${line.key}-remark`} value={line.remark} maxLength={255}
                          onChange={(e) => edit({ remark: e.target.value })}
                          placeholder="Why this charge, or why the discount"
                          className="block w-full rounded border border-border px-2 py-1 text-sm"
                        />
                      </div>
                    </div>
                    {line.rateEdited && lineRate(line) !== line.service.rate_paise && (
                      <p className="mt-1 text-[11px] text-marigold-deep">
                        List price {formatINR(line.service.rate_paise)} &mdash; charged at
                        the counter{line.remark.trim() ? "" : ". Say why in the remark."}
                      </p>
                    )}
                    {typedDiscount > gross && (
                      <p className="mt-1 text-[11px] text-clay">
                        The discount is larger than this charge; only{" "}
                        {formatINR(gross)} can come off it.
                      </p>
                    )}
                  </div>
                );
              })}
            </div>

            <select
              value=""
              className="field-input"
              onChange={(e) => {
                const service = services.find((item) => item.id === e.target.value);
                if (service) {
                  setLines((current) => [...current, makeLine(service)]);
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
            {/* Every figure from one source. Mixing the locally computed
                subtotal with the server's total showed "₹500 / ₹0" for a free
                follow-up — implying a discount that appears on no line. */}
            <dl className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <dt className="text-ink-muted">Subtotal</dt>
                <dd className="tabular text-ink">
                  {formatINR(quote?.gross_paise ?? grossPaise)}
                </dd>
              </div>
              {(quote?.discount_paise ?? discountPaise) > 0 && (
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Discount</dt>
                  <dd className="tabular text-clay">
                    −{formatINR(quote?.discount_paise ?? discountPaise)}
                  </dd>
                </div>
              )}
              {(quote?.tax_paise ?? taxPaise) > 0 && (
                <div className="flex justify-between">
                  <dt className="text-ink-muted">GST</dt>
                  <dd className="tabular text-ink">
                    {formatINR(quote?.tax_paise ?? taxPaise)}
                  </dd>
                </div>
              )}
            </dl>
            <div className="mt-3 flex items-baseline justify-between border-t border-border pt-3">
              <span className="font-display font-semibold text-pine">Total</span>
              <span className="tabular font-display text-2xl font-semibold text-pine">
                {formatINR(quote?.total_paise ?? totalPaise)}
              </span>
            </div>

            {/* Why a line came out as it did. A zero the clerk cannot explain
                to the patient in front of them is worse than no rule. */}
            {quote && quote.notes.length > 0 && (
              <ul className="mt-2 space-y-1">
                {quote.notes.map((note) => (
                  <li
                    key={note}
                    className="rounded-md bg-marigold/10 px-2 py-1 text-[11px] text-marigold-deep"
                  >
                    {note}
                  </li>
                ))}
              </ul>
            )}

            <div className="mt-4 space-y-2">
              <label className="field-label" htmlFor="rc-disc">
                Discount on the whole bill (₹)
              </label>
              <Input id="rc-disc" value={discountRupees} inputMode="decimal"
                     onChange={(e) => setDiscountRupees(e.target.value)} placeholder="0" />
              {billDiscountPaise > afterLinesPaise && (
                <p className="text-xs text-clay">
                  The discount is larger than what is left on the bill.
                </p>
              )}
              {billDiscountPaise > 0 && (
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

            {collectNow && walletPaise > 0 && (
              <p className="rounded-md bg-marigold/10 px-2.5 py-1.5 text-[11px] text-marigold-deep">
                This patient has {formatINR(walletPaise)} on account. Bill them first, then
                settle it from the wallet on the bill.
              </p>
            )}

            {collectNow && (
              <>
                <div className="grid grid-cols-3 gap-1.5">
                  {PAYMENT_MODES.filter(
                    (m) => m.value !== "insurance" && m.value !== "waiver" &&
                           m.value !== "wallet"
                  )
                    .map((option) => (
                      <button
                        key={option.value}
                        onClick={() => { setMode(option.value); setModeDetails({}); }}
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
                {/* Rendered from the server's own rules rather than a
                    guess here, so the counter always asks for exactly what
                    the API will insist on. */}
                <PaymentModeFields
                  mode={mode}
                  values={modeDetails}
                  onChange={setModeDetails}
                />
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
              Register &amp; bill{" "}
              {(quote?.total_paise ?? totalPaise) > 0
                ? formatINR(quote?.total_paise ?? totalPaise)
                : ""}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
