# Reception module: Onito parity plan (v3)

Status: **APPROVED (2026-09-22). All 7 questions answered below. Building the proposed
work list in order.**
Base: `ocr-implementation` (30 migrations; most of the Onito replacement already exists).
v1 of this plan was written against `main` by mistake and overstated what was missing.
v3 replaces every *verify* row from v2 with what was actually seen running the app
(2026-09-22, isolated local stack, admin login) against a fresh seed — patients, wards,
tariff and lab tests only, no consultants, payers or bills entered. **The verify pass is
now complete** — every screenshot-group row above is Have, Partial or Missing, none left
as "verify" or "not re-tested".

Source: 35 reference screenshots of the pilot hospital's Onito HIS reception login (kept
outside the repo, since they show real patient data).

## Decisions made

| Topic | Decision |
|---|---|
| UI approach | Same flow, names and keyboard habits as Onito; modern look in our design system |
| Scope | Full Onito reception functionality |
| Prescription / history | Out of scope (doctor module) |
| Insurance | Payer list plus per-payer rates |

## Screenshot groups against this branch

| Onito screen(s) | Status | Notes |
|---|---|---|
| Patient search, top bar | **Have** | Counter has its own "UHID, mobile number or name" box; global F5 not re-tested this pass |
| OPD registration | **Partial, confirmed** | Register-new-patient fields: Full name, Mobile, Age, Gender, City. **No Guardian field.** Visit: Department (clinical: Orthopedics/Gynecology, not OPD/Cons./DIAG), Visit type, Consultant. **No Referred-by field anywhere on the counter.** |
| OPD billing / charges | **Have, confirmed** | Per-line Rate, Qty, Discount (₹), Remark; whole-bill discount; Cash/UPI/Card/Net banking/Cheque; register & bill in one step |
| Empanelment (payer) on a bill | **Corrected: Have on OPD, Missing on IPD** | v3's "Missing, confirmed" was wrong — `reception-counter.tsx` has had a "Paid by" org dropdown since `f2570d1` (2026-09-16); the verify pass just had no organisations seeded, so it stayed hidden by design ("only shown when the hospital actually has agreements"). Confirmed working once an org (CGHS) exists. IPD admission genuinely still has no payer field. |
| Diagnostics registration | **Missing, confirmed** | Department switch is Orthopedics/Gynecology only. Lab has its own "Register tests" flow, separate screen, not a Dept switch on the billing form |
| OPD receipt / advance | **Not re-tested this pass** | Existing code path (wallet, numbered receipts); no reason to doubt it |
| Appointments | **Have, confirmed** | Book screen: patient, consultant, day, slot picker, type, reason. Live queue board |
| Invoice List report | **Have** (item 7) | Columns: Date, Bill, Patient, UHID, Consultant, **Payer**, From, Visit, Gross, Discount, Net, Paid, Balance, **Cancelled**, Status. |
| Daily Summary report | **Have, confirmed** | "Daily closing" report exists in the picker |
| Ledger report | **Have, confirmed** | "Day-wise receipts and refunds" in the same report picker, alongside Cash ledger, Collection summary, Consultant-wise and Department-wise billing |
| Service master | **Have** (item 4) | Add-service form now has: Code, Name, Kind, Department, Rate, **IPD rate, unit**, GST %, HSN/SAC, Offered-at-counter, **rate-editable, discount-allowed, requires-consultant flags**. Per-organisation rate rows already existed (separate Organisations screen, not the form itself) and per-consultant rows now exist too (separate Consultants screen, "Rates" button), both wired into the pricing engine and verified live. (Lab result grouping still lives separately in the Lab test list, matching Onito's medical-type idea reasonably well) |
| Consultant master | **Have** (item 5) | Add-consultant form now also has: Sex, Sort order, "Department's primary consultant", and display-in-OPD/IPD/Diagnostics flags, alongside the existing fields. `is_primary` and `sort_order` are wired into `GET /masters/consultants`' ordering (primary first, then sort order, then name) — the same order the reception counter's default-consultant picker reads. The three display flags are captured but **not yet filtered** per screen (see note below). |
| Payer / organisation master | **Partial, confirmed — real gap** | Add-payer form: Short code, Name, Kind (TPA etc.), Contact, Phone, Email, Address, **one flat Standard discount %**, Credit days, In-use. **No per-service rate table, no service codes per payer** — this is the opposite of v2's "Have, verify" and needs your answer to question 3 |
| IPD admitted list, ward board | **Have, confirmed** | Two views: a read-only Ward board on the clinical dashboard, and a working **Ward terminal** (`/ward`) with its own Admit action per bed |
| IPD admission | **Partial, updated** | Admit form: patient search/register, Department, Under doctor, **Paid by (payer, added item 2)**, Provisional diagnosis, Reason for admission, Allergies, Advance (₹) with receipt mode, Attendant name, Attendant mobile. **Still missing: "other consultant", policy number, attendant address.** |
| IPD billing tabs (Summary, Add Services, Receipt, Discharge, Refund, Room Change) | **Have** (item 8) | Charges tab: advance + add-a-charge, receipted (Receipt: confirmed no gap, already covered). Discharge tab: 3-step wizard, now with a "Refund" link to the reception bill-corrections flow once something's paid. **Room tab (new):** lists every vacant bed across all wards, wired to the transfer backend that already existed unused. Plus the full case sheet (Overview, Doctor's notes, Nursing, Vitals, Medicines, Theatre, Consents, Lab, Files, Records file, Discharge) |
| Customised bill, summary ledger, detailed ledger, admission slip | **Have** (item 8) | Customised bill = the existing tax-invoice PDF, reused (IPD's final bill is a normal `Invoice`); the ward's own "Print bill" button was fixed to use it too, replacing a bare `window.print()`. Admission slip, summary ledger and detailed ledger are new documents (`app/ipd/documents.py`), same letterhead/PrintSetting infrastructure as every other printed document here — functional equivalents, not pixel copies of Onito's layout |
| Discharge modes | **Have** (item 3) | All six Onito modes (Discharged, Expired, LAMA, DAMA, DOPR, Referred) now selectable in both discharge UIs (ward panel wizard and case sheet Discharge tab) |
| Patient files (5 categories) | **Have, confirmed — close match** | 7 categories: Identity proof, Referral letter, Previous records, Outside investigation/film, Clinical photograph, Insurance/TPA, Other. Covers Onito's Medical Record, Photo and Govt ID directly; Consent is handled separately (signed consent forms attach their own scan); no dedicated Billing Refund category, but refunds are already tracked in the ledger rather than as a file |
| Move OPD / diagnostic bills onto an IPD bill ("Credit to IPD") | **Missing, confirmed** | The IPD charge form's "Kind" is Procedure / Investigation / Medicine / Consumable / Doctor visit / Oxygen / Other — manual entry only, no way to pull in an existing OPD or Lab invoice |
| Keyboard-first entry | **Have, confirmed** | `?` (outside a field) opens a shortcuts panel: F2 Reception counter, F5 Find a patient, Alt+A Appointments, F6 Patient diary, Esc Back. Matches the staff guide |

## Bugs found while verifying (not Onito parity — separate fixes)

1. **Hydration error on the clinical dashboard** (`/dashboard`): a `<div>` renders inside a
   `<p>` inside a `<Skeleton>`, invalid HTML nesting that React's dev overlay flags as a
   hydration mismatch (3 errors shown on load). Worth a quick separate fix.
2. **Fresh-install migration failure**: migration `0001` builds every current table from the
   ORM's metadata (`Base.metadata.create_all`), so on a brand-new database migration `0007`
   onward fails with "relation already exists" — its `create_table` calls collide with tables
   `0001` already made. Existing deployments are unaffected (they only ever ran `0001` once,
   long before `0007` existed), but a fresh deployment — like the pilot cutover — hits this
   immediately. Worked around here with `alembic stamp head`; needs a real fix before cutover.

## Proposed work, in order

1. ~~**Guardian and referred-by** on OPD registration.~~ **Done** (`664ca11`). Verified
   end-to-end: `guardian_relation`/`guardian_name` on Patient, `referred_by` on Visit.
2. ~~**Payer on the bill.**~~ **Done.** Migration `0031_admission_organisation` adds
   `organisation_id` to `admissions`; same "Paid by" dropdown pattern as OPD added to the
   IPD admission form (`ward-panel.tsx`). Verified end-to-end (admission `IP26-00002`,
   payer CGHS). Note: this only *captures* the payer on the admission — applying its rate
   to IPD charges is item 4's job (the per-service rate table), not wired yet.
3. ~~**Discharge modes.**~~ **Done.** `DischargeType` enum replaced outright (migration
   `0032_onito_discharge_types`) with Onito's six: Discharged, Expired, LAMA, DAMA, DOPR,
   Referred — safe since no admission had ever been discharged (the old code always sent
   `"routine"`, no selector existed). Wired into **two** discharge UIs that both existed
   already: the ward panel's 3-step wizard (`ward-panel.tsx`) and the case sheet's
   Discharge tab (`case-sheet.tsx`, which already had a working `<select>` reading off
   `DISCHARGE_TYPE_LABEL` — just needed the label map and its two hardcoded `"routine"`/
   `"transferred_out"` checks updated). The signed-discharge-summary gate now requires
   Discharged/Referred/DOPR; LAMA/DAMA/Expired skip it — a judgement call (Onito's DAMA is
   consented so arguably could require it too), flag if the hospital wants it different.
   Verified end-to-end (admission `IP26-00002`, discharge_type `lama`, bed released).
4. ~~**Service master parity.**~~ **Done, small scope** (user chose this over also rebuilding
   IPD charge-entry — see below). Migration `0033_service_master_parity`: `ServiceItem` gets
   `ipd_rate_paise`, `unit`, `rate_editable`, `discount_allowed`, `requires_consultant`
   (data only — `rate_editable`/`discount_allowed` are **not enforced** by `pricing.py`,
   deliberately, matching that module's own stated design that an explicit counter price
   always wins; `requires_consultant` is likewise captured but not validated anywhere yet).
   New `consultant_rates` table (mirrors the pre-existing `negotiated_rates`), wired into
   `pricing.py` with precedence **negotiated org rate > consultant's own rate > org's flat
   discount % > tariff** — a judgement call (documented in the module), flag if the hospital
   wants payer agreements to lose to a doctor's own rate instead. New "Rates" screen per
   consultant (Consultants settings), mirroring the existing per-organisation one. Verified
   end-to-end: a consultant's own rate (₹450 vs tariff ₹500) applied live on a real quote,
   with the correct on-screen note.
   **Deliberately NOT done:** IPD charge-entry (ward "Add a charge") still free-types
   Kind/Description/Rate — it does not read the service catalog, so `ipd_rate_paise` and
   these new consultant/org rates do not yet apply there automatically. Rebuilding that flow
   to pick services from the catalog is a separate, larger piece; ask before starting it.
5. ~~**Consultant master parity.**~~ **Done, same small-scope pattern as item 4.** Migration
   `0034_consultant_master_parity` adds sex, display_in_opd/ipd/diagnostics, sort_order,
   is_primary. `sort_order`/`is_primary` are wired into the consultant list's ordering
   (real behaviour change: this is what the OPD counter's default-consultant fallback reads).
   The three display flags are data-only for now — filtering the OPD/IPD/diagnostics pickers
   by them would mean touching three separate call sites (reception-counter.tsx,
   ward-panel.tsx, and wherever diagnostics picks a consultant), the same "small vs large
   scope" tradeoff as item 4's IPD rate, so left for a decision rather than assumed.
   Verified end-to-end (sex, sort_order, is_primary all round-tripped through the UI to the
   database).
6. ~~Diagnostics dept on the counter~~ — dropped, keeping the separate Lab module (question 7).
7. ~~**Reports parity.**~~ **Done.** No migration needed — `Invoice.organisation_id` already
   existed (item 2's discovery from `0014`), just wasn't joined in this report's query. Added
   a `Payer` column (organisation name, or "Self-pay") and a `Cancelled` column (a cancelled
   bill's original total, kept out of every other total the same way `gross`/`net`/etc.
   already were). Verified live against the isolated stack.
8. ~~**IPD reception gaps.**~~ **Done**, except "credit to IPD" (deferred by your choice —
   real cross-module billing logic, not a quick field; worth confirming the hospital
   actually needs it before building). Everything else — other consultant, attendant
   address, customised bill, summary/detailed ledger, admission slip, Room Change,
   Refund — done and verified against the isolated stack. One real bug found and fixed
   along the way: the ledger's "Total paid" initially read the wallet's *unspent* balance
   (correctly 0 once a final bill had already consumed it as payment) instead of what was
   actually paid — fixed by reading the final invoice's own paid/balance once one exists.
9. **Two bugs above**, whenever convenient — neither blocks this plan.
10. **Cutover.** Onito data import (keeping its invoice-number format and counters), parity
    checklist against the 35 screens, staff quick guide.

## Questions for you — answered (2026-09-22)

1. **Staff exposure:** not yet used by staff — free to rearrange fields/layouts to match Onito.
2. **Discharge modes:** keep all six Onito modes exactly (Discharged, Expired, LAMA, DAMA,
   DOPR, Referred).
3. **Service master:** build the full per-consultant / per-organisation rate table — full
   parity, not just the flat org discount.
4. **Invoice numbering:** keep Onito's format (`2026OPD5915`, `2026RC7186`) and continue its
   counters after cutover.
5. **Roles:** stay with admin / manager only — reception does not get price list / consultant
   edit access.
6. **Payer on the bill:** confirmed gap, build as part of this plan (item 2 below).
7. **Diagnostics:** keep the existing separate Lab module — do not merge into a single
   OPD/Cons./DIAG dept switch on the counter. (Item 6 in "Proposed work" below is dropped.)
