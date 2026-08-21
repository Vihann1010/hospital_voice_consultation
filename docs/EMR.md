# EMR deployment and data migration

This covers bringing the reception, billing and finance module live, and moving
patient records out of the software the hospital uses today.

---

## Part 1 — Upgrading an existing installation

### 1. Back up first

Not optional. This migration adds columns to `patients`, and while it is
written to be safe, a restore path costs ten minutes now and saves a very bad
afternoon later.

```bash
./deploy/scripts/backup.sh
ls -la /var/backups/satya/          # confirm a dump was actually written
```

### 2. Apply the schema change

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm migrate
```

Migration `0003_emr_reception_billing` adds nine new tables and eight nullable
columns on `patients`. Nothing existing is altered or dropped, so consultations,
prescriptions and investigations are untouched.

### 3. Issue UHIDs to existing patients

Patients registered before this upgrade have no UHID. Assign them, oldest
first, so the hospital's earliest patients hold the earliest numbers:

```bash
docker compose -f docker-compose.prod.yml exec backend python -m scripts.backfill_uhids --dry-run
docker compose -f docker-compose.prod.yml exec backend python -m scripts.backfill_uhids
```

Keep the output. It is the record of which patient received which number.

### 4. Load the price list

```bash
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed_tariff
```

**The seeded rates are placeholders.** Set the hospital's real rates before
billing anybody — either by editing `scripts/seed_tariff.py` and re-running it
(existing codes are repriced, not duplicated), or through
`PUT /api/v1/finance/services/{code}`.

Repricing never alters an invoice already raised: bills store the rate that
applied at the time.

### 5. Verify

```bash
curl -fsS https://your-domain/api/v1/health | jq '.status, .capabilities'
```

Then, in the interface: open **Reception**, search for a known patient, and
confirm their UHID appears.

---

## Part 2 — Migrating from the current software

### The shape of the job

Almost every Indian hospital system — Medisoft, a Tally-based package, a local
HMS, or a clerk's Excel workbook — can export CSV. That is the only interchange
format worth relying on; reverse-engineering somebody's database schema is
slower and far more error-prone.

**Migrate patients only.** Historical bills, old prescriptions and past
consultations should stay in the old system, kept read-only for reference. The
temptation to move everything is strong and it is a mistake: financial history
carries its own numbering, its own tax treatment and its own audit trail, none
of which will reconcile against this system's sequences. Keep the old software
installed on one machine and let staff look things up there when they need to.

### 1. Export from the old system

Ask for a CSV of the patient master with these columns. Names are matched
case-insensitively and extra columns are ignored, so an export with forty
columns is fine.

| Column | Required | Notes |
|---|:--:|---|
| `legacy_id` | **yes** | The patient's ID in the old system. This is the matching key — without it, a re-run duplicates everybody. Also accepted as `id` or `patient_id` |
| `name` | **yes** | Also accepted as `patient_name` |
| `phone` | **yes** | Also `mobile`, `contact`. `+91`, spaces, dashes and brackets are all handled |
| `age` | one of | Integer |
| `date_of_birth` | one of | `YYYY-MM-DD`, `DD/MM/YYYY` or `DD-MM-YYYY`. Preferred — age is derived from it, so it does not go stale |
| `gender` | no | `m`/`f`/`male`/`female`/`other`. Anything unrecognised becomes "other" |
| `uhid` | no | The old hospital number |
| `address`, `city`, `blood_group` | no | |
| `emergency_contact_name`, `emergency_contact_phone` | no | |

### 2. Dry run on a sample

Never import blind. Start with a hundred rows:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.import_legacy --file /data/media/import/patients.csv --dry-run --limit 100
```

You get a report: how many would be created, how many updated, and every row
that cannot be imported with the reason. Nothing is written.

Rows are **rejected rather than guessed at**. A missing name, an unreadable
age, a phone number that is not a phone number — each is listed for a human to
fix. A plausible-looking default silently imported is the kind of error nobody
finds for a year.

### 3. Fix and repeat

Correct the rejected rows in the CSV, dry-run again. Repeat until the rejection
list is either empty or consists only of rows you have consciously decided to
abandon.

### 4. Import

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.import_legacy --file /data/media/import/patients.csv
```

**Re-running is safe.** Rows are matched on `legacy_id`, so an import that
fails halfway can simply be run again — existing records are updated, missing
ones created. If your export lacks a stable ID, stop and get one; without it,
the second attempt doubles the patient list.

### 5. What happens to old hospital numbers

- If the old number happens to fit this system's format, it is kept.
- Otherwise a fresh UHID is issued, and the old number remains searchable
  through `legacy_id`.

Either way nothing is lost, and staff can find a patient by the number written
on their old paper file.

### 6. Reconcile

```sql
-- Should equal the row count of your CSV, minus rejections
SELECT count(*) FROM patients WHERE legacy_id IS NOT NULL;

-- Should be zero
SELECT count(*) FROM patients WHERE uhid IS NULL;

-- Spot-check a few against the old system by name and phone
SELECT uhid, legacy_id, name, phone_number FROM patients
WHERE legacy_id IS NOT NULL ORDER BY created_at DESC LIMIT 20;
```

Sit with whoever ran the old system and check ten records by hand. It takes
fifteen minutes and it is the only step that actually proves the migration.

---

## Part 3 — The counter workflow

Once live, reception works like this:

1. **Search** by UHID, mobile number or name. An exact UHID match wins outright,
   so a patient handing over an old prescription is found in one keystroke.
2. **Register** if new — UHID is issued automatically.
3. **Department and visit type** default the consultation fee, so the common
   case needs no thought.
4. **Add charges** from the price list.
5. **Discount**, with a reason if applied.
6. **Collect** — cash, UPI, card, net banking.
7. **Register & bill** — one button, one transaction. Either everything is
   recorded or nothing is; a visit with no bill is exactly the inconsistency
   that gets untangled by hand at closing time.
8. Print the bill, hand over the token, send the patient to voice intake.

### Cash reconciliation

Open a counter at the start of a shift with the opening float, and close it at
the end by counting the drawer. Any difference is recorded with the session
rather than absorbed quietly.

Only cash is counted. Card and UPI settle through the bank and are reconciled
against statements, not against the drawer.

---

## Part 4 — Honest status

Built and tested to the same standard as the rest of the system:

- **Money arithmetic** — integer paise throughout, half-up rounding in exactly
  one place, Indian digit grouping. 46 tests, including the cases where a
  discount does not divide evenly across lines.
- **Invoice totals** — line discounts, apportioned invoice discounts, mixed
  GST rates, and the guards that reject an impossible bill.
- **Identifiers** — UHIDs avoid every character pair confused when handwritten
  or dictated, financial years turn over correctly in April.
- **Import parsing** — messy phone formats, four date formats, and rejection
  rather than guessing.

Scaffolded, and honestly so:

- **Insurance and cashless.** The data model, claim states and workflow are
  complete and usable for tracking. What is *not* here is transmission to any
  particular TPA: every payer has its own portal, form and occasionally an API,
  and building against them needs your actual contracts. Claims are recorded
  and tracked here; submission happens through the payer's channel.
- **Accounting.** This is a collections and reconciliation system, not a
  general ledger. It answers what was billed, what was collected, in what form,
  and whether the drawer matches. It does not do double-entry, trial balances
  or statutory returns — export to Tally or whatever the hospital's accountant
  uses.

Verified against a live PostgreSQL 16 under concurrency:

- **Gapless invoice numbering under contention.** 30 simultaneous counter
  transactions, then a full 100-patient day at 10 concurrent terminals: no
  duplicate or skipped invoice, receipt, visit or UHID numbers.
- **A full OPD day.** 100 registrations, bills and payments through the real
  HTTP API in 4.4 seconds. Billed equals collected equals the sum by payment
  mode equals the sum by department — the ledger reconciles exactly.
- **Financial loopholes.** Double payment, over-refund, double refund,
  cancelling a paid invoice, discount larger than the bill, negative quantity
  and negative rate are each rejected.
- **Concurrent payment on one invoice.** Five cashiers collecting the same
  bill simultaneously: exactly one succeeds, four are refused, and the ledger
  matches the receipts issued.
- **Migrations.** All three apply cleanly to an empty database, producing 23
  tables with the UHID columns present.
- **The legacy importer.** Rejects bad rows with specific reasons, and a
  re-run updates rather than duplicates.

### Bugs this testing found, and fixed

Four real defects surfaced only under load or against a real database:

1. **Lost update on payment.** Five simultaneous payments were all accepted:
   five receipts printed, ₹2,500 taken, ₹500 recorded — the drawer would have
   been ₹2,000 over with nothing to explain it. Fixed by locking the invoice
   row `FOR UPDATE` before touching its balance.
2. **Counter contention broke registration.** When two cashiers raced to
   create the same numbering row, the recovery called `session.rollback()`,
   which expires every object in the session — including the authenticated
   user — so the next attribute access died with `MissingGreenlet`. Nine of a
   hundred registrations failed. Fixed with a SAVEPOINT, so only the failed
   insert is undone.
3. **Every standalone script crashed on first use**, including the migration
   importer needed on day one: importing models individually leaves
   SQLAlchemy unable to resolve relationships declared by name. Fixed by
   importing the model registry.
4. **Passwords silently truncated at 72 bytes**, so a long passphrase and its
   first 72 characters opened the same account. Now rejected at the boundary,
   counted in bytes so a Hindi passphrase is measured correctly.

### Still not verified

- **IPD.** This module covers OPD only — registration, visit, billing and
  collection for an outpatient. Inpatient admission, bed and ward management,
  daily charge accrual, discharge summaries and final settlement are **not
  built**. A hospital running an IPD department needs that as a separate
  piece of work; nothing here should be taken as covering it.
- **Sustained multi-day load.** The tests above run a single day's volume.
  Index behaviour and query plans at a year of accumulated data have not been
  measured.
