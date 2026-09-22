# Reception module: Onito parity plan (v3)

Status: **DRAFT, awaiting approval. Nothing below is built yet.**
Base: `ocr-implementation` (30 migrations; most of the Onito replacement already exists).
v1 of this plan was written against `main` by mistake and overstated what was missing.
v3 replaces every *verify* row from v2 with what was actually seen running the app
(2026-09-22, isolated local stack, admin login) against a fresh seed — patients, wards,
tariff and lab tests only, no consultants, payers or bills entered.

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
| Empanelment (payer) on a bill | **Missing, confirmed** | No payer/empanelment field anywhere on the counter or the admission form. The plan's v2 "Have" was wrong — the staff guide's "agreed rate applied automatically" must mean something else (worth asking, see question 6) |
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
| IPD admission | **Partial, confirmed** | Admit form: patient search/register, Department, Under doctor, Provisional diagnosis, Reason for admission, Allergies, Advance (₹) with receipt mode, Attendant name, Attendant mobile. **Missing: "other consultant", payer/policy number, attendant address.** |
| IPD billing tabs (Summary, Add Services, Receipt, Discharge, Refund, Room Change) | **Not re-tested this pass** | Not opened; case sheet exists per the staff guide with discharge, transfer, advance, refunds, in a different layout from Onito's tabs |
| Customised bill, summary ledger, detailed ledger, admission slip | **Not re-tested this pass** | Carried over from v2 as still unconfirmed |
| Discharge modes | **Not re-tested this pass** | Carried over from v2; still needs your answer to question 2 |
| Patient files (5 categories) | **Not re-tested this pass** | Carried over from v2 |
| Move OPD / diagnostic bills onto an IPD bill ("Credit to IPD") | **Not re-tested this pass** | Carried over from v2 |
| Keyboard-first entry | **Not re-tested this pass** | Carried over from v2 (F2/F3/F5/F6, Alt+A, Ctrl+S, Ctrl+P, Esc, `?`) |

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

1. **Finish the verify pass.** IPD billing tabs, discharge modes, patient files, "credit to
   IPD", keyboard shortcuts — the rows not re-tested this session.
2. **Payer on the bill.** Add empanelment/payer to OPD registration and the IPD admission
   form; per-service payer rates on the payer master (question 3 decides the size of this).
3. **Guardian and referred-by** on OPD registration.
4. **Service master parity.** IPD rate, unit, flags, per-consultant and per-organisation rate
   rows (needs a migration and to feed the existing pricing engine).
5. **Consultant master parity.** Missing display flags, sort order, sex.
6. **Diagnostics dept on the counter**, if question 7 confirms the hospital wants Onito's
   single Dept switch rather than the existing separate Lab flow.
7. **Reports parity.** Payer/empanelment column on Invoice List, cancelled-amount column.
8. **IPD reception gaps.** Other consultant, attendant address, customised bill, ledgers,
   admission slip, discharge-mode mapping.
9. **Two bugs above**, whenever convenient — neither blocks this plan.
10. **Cutover.** Onito data import, parity checklist against the 35 screens, staff quick guide.

## Questions for you

1. Are the pilot's hospital staff already using this branch's reception screens, or has nobody
   outside development seen them? It changes how much we can safely rearrange.
2. **Discharge modes:** Onito has LAMA, DAMA and DOPR as separate options. Do you want all six
   Onito modes kept exactly (staff and reports depend on them), or map onto ours?
3. **Service master:** is the per-consultant / per-organisation rate table on Onito's service
   form something the hospital actually uses, or would the existing organisation rate card do?
4. **Invoice numbering:** keep Onito's format (`2026OPD5915`, `2026RC7186`) and continue its
   counters after cutover, or start fresh?
5. **Roles:** Onito showed one reception login. Should reception be able to edit price list and
   consultants (Onito allowed it), or stay with admin / manager as now?
6. **Payer on the bill is a confirmed gap**, not something to verify further — there is
   genuinely no way to attach a payer/empanelment to a bill today. Should this be built as
   part of this plan, or is it already tracked elsewhere?
7. **Diagnostics**: the hospital's Onito flow puts diagnostics on the same registration screen
   as OPD (Dept: OPD/Cons./DIAG). This branch instead has a separate Lab module. Keep them
   separate (less rework, different mental model for reception) or build Onito's single
   switch (closer match, more rework)?
