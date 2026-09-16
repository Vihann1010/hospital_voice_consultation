# Satya Hospital — Staff Guide

How to use the Satya system day to day, by role. Keep this next to the counter,
the ward station and the lab bench.

> **The system supports your work; it does not decide for you.** Anything marked
> as AI (intake summary, red flags, suggested diagnoses and tests) is a
> suggestion. The treating doctor makes every clinical decision.

---

## 1. Signing in

1. Open the Satya address given to you by the IT person (for example
   `http://<hospital-server>:3000/login`).
2. Enter your email and password. Never share your login — every action is
   recorded against your name.
3. You land on the screen for your role:

| Role | Opens on | Used for |
|---|---|---|
| Reception, Supervisor | **Reception terminal** | registration, billing, payments, appointments |
| Doctor | **Clinical dashboard** | consultations, Visit Pad, prescriptions, ward, lab verification |
| Nurse | **Ward terminal** | beds, observations, medicines, nursing notes, diet |
| Lab | **Laboratory terminal** | samples, results |
| Manager | **Clinical dashboard** | money, reports, settings |
| Admin | **Clinical dashboard** | everything, including staff accounts |

**Session expired?** You are sent back to sign in, and then returned to the page you were on.

**What your role can and cannot do** is listed in `docs/ROLES.txt`. If a button
says "Requires permission", ask a supervisor or admin — do not share logins.

### Keyboard shortcuts

| Key | Does |
|---|---|
| F2 | Reception counter |
| F3 | Ward board |
| F5 | Find a patient |
| F6 | Patient diary (what a patient has been billed and paid) |
| Alt + A | Appointments |
| Ctrl + S | Save the Visit Pad now |
| Ctrl + P | Print the Visit Pad |
| Esc | Back one step |

Press **?** on any screen to see the shortcuts available there. If you are typing in a box, press **Ctrl + /** instead.

---

## 2. Reception and Supervisor

The reception terminal has: **Counter**, **Patients**, **Appointments**,
**Bills**, **Diary**, **Reports** and **Lab**.

### Register a patient and raise the bill
1. On the **Counter**, search the patient by name, phone or UHID.
   If they are new, fill in the **Patient** section. A UHID is issued automatically.
2. In **Visit**, choose the consultant and the visit type.
3. In **Charges**, add the services. The fee comes from the price list.
   A free follow-up or an organisation's agreed rate is applied automatically and shown on the bill with the reason.
   Each charge has its own **Rate**, **Qty**, **Discount** and **Remark**:
   - Change the **Rate** when the doctor has said to charge something else. The line then says "charged at the counter"; leave it alone and the automatic rules keep working.
   - **Discount** on a line comes off that charge only. The box lower down still discounts the whole bill.
   - **Remark** is printed on the bill under the charge — say why the rate was changed or why the discount was given, so the patient and the auditor read the same explanation.
4. In **Payment**, choose the mode and fill in what it asks for:
   - Card: last 4 digits
   - UPI / bank transfer: the reference number
   - Cheque: number, bank and date
   - Waiver: who approved it and why
5. Save. The bill and receipt can be printed straight away.

### Appointments
Book, move or cancel from **Appointments** (Alt + A). When the patient arrives, check them in — this puts them in the day's queue.

### Advances (deposits)
Take an advance from the patient's wallet or, for an admitted patient, from the admission.
Every advance gets a **receipt number**. It is used automatically against the final bill.

### Correcting mistakes
- **Wrong receipt entered** (wrong amount, mode or patient): cancel the receipt with a reason — only while your cash shift is still open.
- **Money actually returned** to the patient: this is a **refund**, done by a supervisor.
- **Bill raised by mistake**: a supervisor cancels it with a reason. A bill that has been paid must be refunded first.
- Nothing is ever deleted — cancelled bills and receipts stay visible as cancelled.

### Cash shift
Open your cash shift at the start of duty with the float in the drawer, and close it at the end with the counted cash. Any difference (over or short) is recorded.

### Insurance and TPA patients
Open **Insurance claims** (from the clinical dashboard).
1. **New claim**: find the patient, add their policy (insurer, TPA, policy number, validity), choose the admission or bill.
2. Move the claim step by step: pre-authorisation requested → approved → claim submitted → approved or partially approved. Each step asks for what the TPA gave you (amount, reference, or their query).
3. Once approved, press **Put on bill**. The family is then asked to pay only the remaining amount.
4. The accounts team records the TPA's payment later.

---

## 3. Doctors

The clinical dashboard menu: **Overview**, **Waiting patients**, **Current consultations**,
**Completed**, **Patient search**, **Ward board**, **Theatre**, **Diet sheet**,
**Radiology**, **Laboratory**, **Insurance claims**, **Reports**, **Settings**.

### Seeing an OPD patient
Open the patient from **Waiting patients**. The consultation has these tabs:

| Tab | What is there |
|---|---|
| Record | What the patient said at voice intake, red flags, and the **vitals** typed at intake |
| Visit Pad | Your clinical note: complaints, history, vitals, examination, diagnosis, advice, follow-up |
| Certificates | Medical leave, fitness and other certificates |
| Prescription | Write or dictate medicines; run the safety check before issuing |
| Reports brought | Reports the patient uploaded or brought, with the reading of values |
| Lab results | Results from the hospital laboratory |
| Transcript | The full intake conversation |

**Visit Pad**
- It saves automatically as you type (Ctrl + S saves at once).
- AI sections (intake summary, red flags, differentials, suggested tests) are drafts — edit or clear them.
- Vitals typed by the nurse at intake are filled in for you, exactly as typed. Your own readings are never overwritten.
- **Sign** the pad when complete. A signed document cannot be edited; to correct it, choose **Amend**, give a reason, and sign the new version. The original stays readable.

**Prescription**
- Dictate or type the medicines, then run the **safety check** (allergies, interactions, duplicates, pregnancy).
- A serious alert must be acknowledged before the prescription can be issued.
- The prescription can be printed or sent to the patient on WhatsApp (when enabled).

**Mark as seen** when you have reviewed a completed consultation.

### Inpatients
Open **Ward board**, choose the bed. The case sheet tabs: **Overview**, **Doctor's notes**,
**Nursing**, **Vitals**, **Medicines**, **Theatre**, **Consents & certificates**, **Lab**,
**Files**, **Records file**, **Discharge**.

- **Admit**: from the ward board, choose a free bed, the patient and the advance (with its payment mode — it gets a receipt).
- **Doctor's notes**: one admission note, then a progress note each day.
- **Medicines**: order medicines on the drug chart. Nurses record each dose given.
- **Diet**: order the patient's diet; the kitchen sees it on the diet sheet.
- **Theatre**: book the operation. The pre-operative checklist must confirm identity, consent and site marking before the patient can go to theatre.
- **Discharge**: initiate discharge, write and sign the discharge summary, raise the final bill (the advance is applied automatically), then complete discharge.
- **Leave**: a patient going home for a short period is marked on leave and marked back on return.

### Laboratory — verifying results
Results typed by the lab reach the patient only after **a doctor verifies them**. Open **Laboratory**, check the values and verify. A verified result can be reopened for correction with a reason.

### Radiology
**Radiology** lists imaging studies ordered. Write the report against the order and sign it.

---

## 4. Nurses

The ward terminal has: **Beds**, **Theatre**, **Diet**, **Lab**.

### Observations (vitals)
Open the patient's bed → **Vitals** → **Record observations**.
- Enter respiratory rate, SpO2, blood pressure, pulse and temperature **in °C**, the level of consciousness (AVPU), and whether the patient is on oxygen.
- Whole numbers for SpO2, pulse and BP. Temperature between 25 and 45 °C.
- Press **Save observations**. The **early warning score (NEWS2)** is calculated at once. A high score is flagged for escalation — inform the doctor immediately.
- If the save is refused, the reason is shown under the form (for example "SpO2 must be 100 or less"). Correct the value and save again.

### Vitals at OPD intake
On the intake screen, type BP (systolic and diastolic), pulse, SpO2, temperature, respiration, height, weight and sugar, and save. The doctor sees them on the consultation and in the Visit Pad.

### Medicines
Open **Medicines** (drug chart). Record each scheduled dose as given, with the time. As-needed doses are recorded when given.

### Nursing documents
- **Nursing assessment** on arrival (fall risk, skin, lines, diet, vitals on admission), then **nursing notes** each shift.
- Sign each document. Corrections are made by amending with a reason, never by editing a signed document.

### Diet
**Diet** shows each patient's current diet order. Only a doctor or nurse can order or stop a diet.

### Sending samples to the lab
From the patient's **Lab** tab, register the tests. For an admitted patient the charge goes to the stay's bill.

### Theatre
The **pre-operative checklist** (identity confirmed, consent signed, site marked) must be completed before the patient is shifted. Record theatre times as they happen: wheel-in, anaesthesia start, incision, closure, wheel-out.

---

## 5. Laboratory

The lab terminal has: **Worklist**, **Test list**, **Reports**.

1. **Worklist** shows every registered request.
2. Mark the sample **collected**.
3. Enter the results. Values outside the reference range are flagged; critical values are marked.
4. The request waits for a **doctor to verify**. Only verified results are released and printed.
5. **Test list** holds tests, parameters, units and reference ranges. Changing a range means a doctor must review it before that test can be verified again.

---

## 6. Manager and Accounts

Menu items for you: **Finance**, **Accounts**, **Insurance claims**, **Reports**, **Settings**.

### Finance PIN
**Finance** and **Accounts** ask for the four-digit **finance PIN** once per browser session.

### Finance
The day's billed amount, collections by payment mode, refunds and outstanding bills.
Insurance amounts put on a bill are **not** counted as cash collected — that money arrives later from the TPA.

### Accounts (double-entry books)
Tabs: **Books**, **Ledgers**, **Day book**, **Consultant payouts**.

- **Books**: bills, receipts, refunds and advances are posted automatically every 10 minutes. Press **Post new entries** to post straight away. The trial balance must show balanced.
- **Ledgers**: every ledger's balance and statement. Add ledgers (for example rent, salaries) here.
- **Day book**: every voucher. Enter manual vouchers for expenses. A wrong voucher is **reversed** with a reason, never edited.
- **Consultant payouts**:
  1. Set each consultant's share % and which services it applies to.
  2. Preview a period — only fully paid bills count.
  3. **Approve**: the counted bills are locked and can no longer be changed.
  4. **Pay**: by bank transfer, UPI, cash or cheque, with TDS if deducted.
  5. A payout can be cancelled only before it is paid. A refund on a bill already paid out is recovered in the next payout.

### TPA settlements
In **Insurance claims**, open a claim that is on the bill and record what the TPA sent: amount received, **TDS** deducted, and any amount **disallowed** (with the reason). When these add up to the amount on the bill, the claim is marked **settled**. **Payers owe** shows what each TPA still owes, by age.

### Reports
**Reports** lists only the reports your role may run: collection summary, daily closing, invoice list, consultant-wise and department-wise billing, patient list, wallet report, inpatient balances and ledger, trial balance, day book, consultant payouts, TPA claims, TPA outstanding, lab and theatre registers. Every report can be exported as CSV.

### Settings
Open **Settings** for:

| Screen | Who | Used for |
|---|---|---|
| Consultants | Admin, Manager | doctors, OPD days and hours, slot length, free follow-up, fee code, registration number |
| Operation list | Admin, Manager | operations, prices, theatre rooms |
| Room charges | Admin, Manager | the daily room-charge run and its history |
| Diet list | Admin, Manager | diets the ward can order |
| Pad layouts | Admin, Doctor | sections of the Visit Pad (a doctor for themselves; admin for a department or the hospital) |
| Staff accounts | Admin | create logins, change roles, reset passwords |

A consultant's payout share is set only in **Accounts → Consultant payouts**.

---

## 7. Rules everyone follows

- **Never share your login.** Everything is recorded against the person signed in.
- **Nothing is deleted.** Bills, receipts, documents and vouchers are cancelled, reversed or amended — always with a reason.
- **Signed means final.** Correct a signed document by amending it.
- **Money screens need the finance PIN.** Do not write it down near the counter.
- **If the system refuses something, read the message** — it says what to do first.

## 8. When something goes wrong

1. Read the message on screen. Most refusals explain themselves (a missing field, a step to do first, a permission you do not hold).
2. If the message ends with **(reference …)**, write that reference down — it lets the technical team find exactly what happened.
3. Tell the IT person: your name, the patient (UHID), the screen, what you pressed, the time, and the reference if shown.
4. If the system is unavailable, use the agreed **paper forms** and enter the records once it is back.
