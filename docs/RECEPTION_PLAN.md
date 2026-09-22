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
| Invoice List report | **Have, confirmed** | Columns: Date, Bill, Patient, UHID, Consultant, From, Visit, Gross, Discount, Net, Paid, Balance, Status. Close to Onito's, but no payer/empanelment column and no separate cancelled-amount column |
| Daily Summary report | **Have, confirmed** | "Daily closing" report exists in the picker |
| Ledger report | **Have, confirmed** | "Day-wise receipts and refunds" in the same report picker, alongside Cash ledger, Collection summary, Consultant-wise and Department-wise billing |
| Service master | **Partial, confirmed** | Add-service form: Code, Name, Kind, Department, Rate, GST %, HSN/SAC, Offered-at-counter. **Missing: IPD rate, unit, rate-editable / discount-allowed / consultant-selection flags, per-consultant rows, per-organisation rows.** (Result grouping for lab tests, e.g. biochemistry/clinical pathology, lives separately in the Lab test list, not here — matches Onito's medical-type idea reasonably well) |
| Consultant master | **Partial, confirmed** | Add-consultant form: Name, Department, Phone, Qualification (printed under signature), Registration number, Consultation fee, OPD days, OPD from/until, Minutes per appointment, Free follow-up days, Login, Notes, First-consultation-free, In-use. **Missing: sex, display-in-OPD/IPD/Diagnostics flags, sort order, "is primary".** |
| Payer / organisation master | **Partial, confirmed — real gap** | Add-payer form: Short code, Name, Kind (TPA etc.), Contact, Phone, Email, Address, **one flat Standard discount %**, Credit days, In-use. **No per-service rate table, no service codes per payer** — this is the opposite of v2's "Have, verify" and needs your answer to question 3 |
| IPD admitted list, ward board | **Have, confirmed** | Two views: a read-only Ward board on the clinical dashboard, and a working **Ward terminal** (`/ward`) with its own Admit action per bed |
| IPD admission | **Partial, updated** | Admit form: patient search/register, Department, Under doctor, **Paid by (payer, added item 2)**, Provisional diagnosis, Reason for admission, Allergies, Advance (₹) with receipt mode, Attendant name, Attendant mobile. **Still missing: "other consultant", policy number, attendant address.** |
| IPD billing tabs (Summary, Add Services, Receipt, Discharge, Refund, Room Change) | **Partial, confirmed** | A quick popover per bed (Charges tab: advance + add-a-charge; Discharge tab: 3-step wizard) plus a full case sheet (Overview, Doctor's notes, Nursing, Vitals, Medicines, Theatre, Consents, Lab, Files, Records file, Discharge). No standalone Receipt, Refund or Room Change tab was found in either — worth a closer look if the hospital uses those often |
| Customised bill, summary ledger, detailed ledger, admission slip | **Missing, confirmed** | Not found anywhere in the popover or case sheet |
| Discharge modes | **Missing, confirmed** | The discharge wizard (Raise final bill → Draft summary → Final diagnosis + Complete discharge) has **no mode selector at all** — not a mapping problem, the field doesn't exist. Onito's six modes (Discharged, Expired, LAMA, DAMA, DOPR, Referred) all need adding |
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
3. **Discharge modes.** Add a mode selector (all six Onito modes) to the discharge wizard.
4. **Service master parity.** IPD rate, unit, flags, per-consultant and per-organisation rate
   rows (needs a migration and to feed the existing pricing engine) — this is also #2's
   per-service payer rate table. **Scope note (found while building item 2):** a
   per-organisation rate table (`negotiated_rates`: organisation_id, service_item_id,
   rate_paise) already exists from migration `0014` — check whether the pricing engine
   (`app/billing/pricing.py`) already reads it before assuming this needs building from
   scratch. Per-consultant rates and the service-master admin UI to edit either table still
   need checking/building regardless.
5. **Consultant master parity.** Missing display flags, sort order, sex.
6. ~~Diagnostics dept on the counter~~ — dropped, keeping the separate Lab module (question 7).
7. **Reports parity.** Payer/empanelment column on Invoice List, cancelled-amount column.
8. **IPD reception gaps.** Other consultant, attendant address, customised bill, ledgers,
   admission slip, "credit to IPD", any Receipt/Refund/Room Change tabs the hospital needs.
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
