# Reception module: Onito parity plan

Status: **DRAFT, awaiting approval. Nothing below is built yet.**
Source: 35 reference screenshots of the pilot hospital's Onito HIS reception login
(`Resources/Onito References and Screenshots/Reception Module`, kept outside the repo;
they show real patient data and must not be copied into code or docs).

## Decisions made

| Topic | Decision |
|---|---|
| UI approach | Same flow, field names and keyboard shortcuts as Onito; modern look in our design system |
| Scope | Full Onito reception functionality, built in phases |
| Prescription / patient history | Out of scope (doctor module). Reception keeps only what it needs |
| Insurance | Payer list plus per-payer service rates, as in Onito's "Organization" section |

## Onito screen inventory (what we must match)

1. **OPD home menu**: OPD Consultation, OPD Registration, New Patient Registration, Receipt,
   Print OPD Documents, Refund, OPD Appointment, Reports, Settings.
2. **OPD / Diagnostics registration and billing** (one screen, Dept switch OPD / Cons. / DIAG):
   patient banner (name, age/sex, UHID, guardian, city), consultant, referred-by,
   empanelment (payer), service lines (service, done-by consultant, rate, qty, discount % or ₹,
   total, remark), receipt lines (amount, mode, remark, several allowed), invoice-level discount,
   Submit / Cancel, "recent OPD bills" side panel.
3. **OPD Receipt**: advance payment against a patient (date, amount, mode, remark).
4. **Reports**: Invoice List (dept, category, user, cancelled, credit-to-IPD, date range; Excel, Print,
   search, totals); Ledger (receipts and refunds, filter by payment mode); Daily Summary
   (per dept: cash, UPI, total, billed, pending).
5. **Settings, service master**: name, display name, code, rate, IPD rate, unit, medical type,
   result group, group, active, rate editable, discount allowed, consultant selection
   allowed / mandatory; per-consultant rows (invoice name, rate, % share); per-organisation
   rows (invoice name, rate, code).
6. **Settings, consultant master** (76 entries): name, display name, specialization, sex,
   qualifications, default appointment length, free follow-up days, active, primary,
   display in OPD / IPD / Diagnostics, sort order, record format.
7. **IPD**: admitted-patients list; New Admission (date, bed, consultant, other consultant,
   remark, brought-by details, payer, policy no.); IPD Billing tabs: Summary (provisional bill,
   receipts, room history, print bill / customised bill / summary ledger / detailed ledger /
   admission slip), Add Services, Receipt, Discharge (modes: Discharged, Expired, LAMA, DAMA,
   DOPR, Referred), Refund (purpose: excess payment return), Room Change, Patient Files
   (Medical Record, Billing Refund, Consent, Photo, Govt ID); IPD Case Sheet; Bed Layout.
8. **Cross-cutting**: global "UHID / Name / Mobile" search in the top bar, keyboard-first entry
   (Enter submits, Ctrl+P print, Ctrl+R reset, Ctrl+arrows switch tabs), document numbering
   (`2026OPD5915`, `2026OPDIV5914`, `2026RC7186`, `2026IPD318`).

## Preliminary gap read (to be verified per feature before each phase)

| Area | Have | Missing |
|---|---|---|
| Patient registration, UHID | Registration, search, UHID | Guardian field, global top-bar search |
| OPD billing | Register-and-bill, invoice, PDF, payments, refund, cancel | Payer, referred-by, per-line consultant and discount %, several receipts, recent-bills panel, Dept switch, advance receipt |
| Diagnostics billing | Investigation service category | Separate flow and dept |
| Reports | `finance/collections`, `finance/outstanding` | Invoice List, Ledger, Daily Summary, Excel and Print |
| Masters | `PUT finance/services/{code}` | Service master UI, per-consultant and per-payer rates, consultant master, payer master |
| IPD | Backend: wards, beds, admission, transfer, charges, bill, discharge. UI: ward board | Reception UI for admit, billing tabs, discharge, room change, patient files, admitted list |
| Insurance | Policies and claims (backend) | Payer on bill, per-payer rates |

## Proposed phases (each ends in something demonstrable)

- **P0 Foundations**: reception shell and navigation matching Onito's menus, global patient search,
  patient banner component, keyboard-shortcut primitives, shared table with Excel / Print.
- **P1 Masters and data model**: payer (organisation) master, consultant master, service master
  extensions (IPD rate, flags, per-consultant and per-payer rates, share %), with migrations and UI.
  Billing depends on these, so they come first.
- **P2 OPD and Diagnostics billing**: unified billing screen, payer, referred-by, line-level
  consultant and discount, multiple receipts, advance receipt, refund, recent bills, print documents.
- **P3 Reports**: Invoice List, Ledger, Daily Summary, with Excel and Print.
- **P4 IPD reception**: admitted list, admission, IPD billing tabs, discharge, room change, patient files,
  bed layout.
- **P5 Cutover readiness**: Onito data import (patients, open IPD balances), parity checklist
  against these 35 screens, staff quick-guide.

## Open questions (need your answer before the phase that depends on them)

1. **OPD Appointment** (booking): in scope for reception? (P2)
2. **Print OPD Documents**: which documents (OPD slip, registration card, receipt)? Please share one
   sample of each if possible. (P2)
3. **IPD Case Sheet**: clinical, so doctor and nursing module, or does reception need it? (P4)
4. **Bed Layout**: a visual bed map? The existing ward board may already cover it. (P4)
5. **"Credit to IPD"** filter and IPD Billing's Diagnostic Charges / OPD Charges buttons: bills raised
   at OPD or Diagnostics and moved onto an IPD bill. Confirm this is how it works. (P2 / P4)
6. **Invoice numbering**: keep Onito's format (`2026OPD5915` / `2026OPDIV5914` / `2026RC7186`)
   and continue its counters after cutover, or start fresh? (P2 / P5)
7. **Roles**: is reception one role, or do we need reception vs. cashier vs. admin (masters and
   discounts often need approval)? (P1)
8. **Cutover**: which Onito data must move over (patients only, or open IPD bills too)? (P5)
