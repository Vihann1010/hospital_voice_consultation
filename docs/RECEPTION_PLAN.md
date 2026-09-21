# Reception module: Onito parity plan (v2)

Status: **DRAFT, awaiting approval. Nothing below is built yet.**
Base: `ocr-implementation` (30 migrations; most of the Onito replacement already exists).
v1 of this plan was written against `main` by mistake and overstated what was missing.

Source: 35 reference screenshots of the pilot hospital's Onito HIS reception login (kept
outside the repo, since they show real patient data). Findings below come from
`docs/STAFF_GUIDE.md`, the migrations, the models and code searches, **not from running the
app**. Rows marked *verify* must be checked in the running app before we build or skip them.

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
| Patient search, top bar | **Have** | F5 "Find a patient", UHID / name / phone |
| OPD registration and billing | **Have, verify details** | Counter: patient, consultant, visit type, charges with own rate / qty / discount / remark, payment modes, print. Referred-by exists in code (*verify it is on the counter*). Guardian exists (*verify*) |
| Empanelment (payer) on a bill | **Have** | Organisations master; agreed rates and free follow-up applied automatically, reason shown on the bill |
| Diagnostics registration | **Partial, verify** | Lab module registers tests and charges them; Onito's single Dept switch (OPD / Cons. / DIAG) on one billing screen has no equivalent found |
| OPD receipt / advance | **Have** | Patient wallet with numbered advance receipts |
| Refund, bill correction | **Have** | Refund by supervisor; receipt cancel; bill cancel with reason |
| Appointments | **Have** | Book, move, cancel, check-in |
| Invoice List report | **Have, verify columns** | CSV export exists. Onito columns to compare: gross, service disc., bill disc., cancelled, net payable, receipt, refund, balance |
| Daily Summary report | **Have** | "Daily closing" |
| Ledger report (receipts and refunds by mode) | **Verify** | Not found by name; may be covered by collection summary |
| Service master (Add Lab Service) | **Partial** | Have: code, name, category, rate, HSN, active. Missing: IPD rate, unit, medical type, result group, rate-editable / discount-allowed / consultant-selection flags, per-consultant rows, per-organisation rows with code |
| Consultant master | **Partial** | Have: OPD days and hours, slot length, free follow-up, fee code, registration no. Missing (*verify*): qualifications printed on prescriptions, display-in OPD / IPD / Diagnostics flags, sort order |
| Payer / organisation master | **Have, verify** | Organisations with rate card; confirm per-service rate and service code per organisation |
| IPD admitted list | **Have** | Ward board and admissions |
| IPD admission | **Partial** | Have: bed, consultant, advance with receipt, policy. Missing: "other consultant", brought-by name / mobile / address |
| IPD billing tabs (Summary, Add Services, Receipt, Discharge, Refund, Room Change) | **Have, different layout** | Case sheet with discharge, bed transfer, advance, refunds. Onito's single tabbed billing view is the difference |
| Provisional IPD bill, print | **Have** | Provisional bill exists |
| Customised bill, summary ledger, detailed ledger, admission slip | **Missing / verify** | No matches found for customised bill or admission slip |
| Discharge modes | **Partial** | Onito: Discharged, Expired, LAMA, DAMA, DOPR, Referred. Ours: routine, against medical advice, transferred out, absconded, death. Mapping needs your decision (question 2) |
| Patient files (5 categories) | **Have** | Patient files module. Categories to compare: Medical Record, Billing Refund, Consent, Photo, Govt ID |
| Move OPD / diagnostic bills onto an IPD bill ("Credit to IPD") | **Missing / verify** | Not found |
| Keyboard-first entry | **Have** | F2, F3, F5, F6, Alt+A, Ctrl+S, Ctrl+P, Esc, `?` help |

## Proposed work, in order

1. **Verify pass (no code).** Run the app with the pilot's roles and walk each *verify* row
   against its screenshot. Output: this table with every row resolved.
2. **Service master parity.** IPD rate, unit, flags, per-consultant and per-organisation rate
   rows (needs a migration and to feed the existing pricing engine).
3. **Consultant master parity.** Missing display flags, sort order, qualifications.
4. **Diagnostics dept on the counter.** The OPD / Cons. / DIAG switch, if the verify pass
   confirms it is missing.
5. **Reports parity.** Any Invoice List / Ledger column or report that is missing.
6. **IPD reception gaps.** Other consultant, brought-by, customised bill, ledgers, admission
   slip, discharge-mode mapping, "credit to IPD".
7. **Cutover.** Onito data import, parity checklist against the 35 screens, staff quick guide.

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
