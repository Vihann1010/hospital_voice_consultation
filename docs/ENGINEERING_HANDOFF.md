# Satya Hospital Platform — Engineering Handoff

Current state of the platform as of **15 September 2026**, for the engineer who
picks it up. It supersedes the role and module sections of
`DEVELOPER_HANDOFF.md`, which describes an earlier version.

Companion documents:
[STRUCTURE.md](STRUCTURE.md) (layout and where code goes) ·
[LOGGING.md](LOGGING.md) (logs and tracing) ·
[ROLES.txt](ROLES.txt) (generated permission matrix) ·
[API.md](API.md) · [DEPLOYMENT.md](DEPLOYMENT.md) ·
[PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) · [STAFF_GUIDE.md](STAFF_GUIDE.md)

---

## 1. What this is

A hospital information system replacing the Onito HIS at Satya Trauma &
Maternity Center, Kanpur, built on top of a voice-first patient intake product.
Delivered in five parts:

| Part | Scope | State |
|---|---|---|
| 1 | Platform: roles, audit, finance PIN, reports framework | done |
| 2 | OPD front office: registration, billing, payments, wallet, appointments, cash sessions | done |
| 3 | Clinical record: Visit Pad, inpatients, drug chart, theatre, consents/certificates, files, radiology, records bundle, leave, room charges | done |
| 4 | Laboratory, dietary | done — **Marg pharmacy import not started** (waiting for the data source) |
| 5 | Reconciliation reports, receipted advances, double-entry books, consultant payouts, TPA/insurance, consultant register | done — Tally, scheduled messaging, history import, cutover **not started** |

**Source:** `https://github.com/Vihann1010/hospital_voice_consultation`, branch
`feature/onito-replacement-parts-1-4`. `main` is the older product and must not
receive direct pushes; merge by pull request.

---

## 2. Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, Pydantic 2 |
| Database | PostgreSQL 16 |
| Frontend | Next.js 14 (app router), React 18, TypeScript, Tailwind; fonts bundled via `@fontsource` (no Google Fonts fetch at build) |
| AI / voice | Sarvam STT/TTS, provider-agnostic LLM gateway (`LLM_PROVIDER`) |
| Documents | ReportLab PDFs, Tesseract OCR |
| Runtime | Docker Compose; nginx with TLS in production |

---

## 3. Running it

### Containers (local)

| Container | Port | Notes |
|---|---|---|
| `satya-db` | 5432 | db `satya_hospital`, user `satya` |
| `satya-backend` | 8000 | **`backend/app` is mounted** into the container |
| `satya-frontend` | 3000 | production build baked into the image |

```bash
docker compose up -d --build
docker exec -w /app satya-backend alembic upgrade head
```

### Everyday operations

| You changed | Do |
|---|---|
| backend Python code | `docker restart satya-backend` (code is mounted) |
| `.env` | `docker compose up -d --force-recreate --no-deps backend` |
| frontend code | `docker compose build frontend && docker compose up -d --force-recreate --no-deps frontend` |
| a model | new Alembic migration, then `alembic upgrade head` in the container |
| a permission | `docker exec satya-backend python scripts/generate_roles_doc.py > docs/ROLES.txt` |

`backend/scripts` is mounted **read-only**; run scripts in place. The frontend
build fails on ESLint errors (for example an unescaped `'` in JSX) even when
`tsc` passes — run `npx next lint` before building.

### LAN / phone access
The QR upload flow is opened on phones, so `.env` must name the server's LAN
address: `CORS_ORIGINS` (include `http://<lan-ip>:3000`) and `PUBLIC_BASE_URL`
(`http://<lan-ip>:3000`), then recreate the backend. `frontend/lib/api.ts`
(`resolveApiUrl`) swaps a `localhost` API host for the page's host so the same
build works from another device.

### Configuration
All settings and defaults are in `backend/app/core/config.py` (there is no
`.env.example` — create one from that file). Settings added in Parts 3–5:

| Setting | Purpose |
|---|---|
| `BED_CHARGE_WORKER_ENABLED`, `BED_CHARGE_RUN_AT`, `BED_CHARGE_CHECK_S` | morning room-charge run |
| `BED_CHARGE_POST_FROM` | go-live date: no room charges before it (currently `2026-09-15`) |
| `BOOKS_POSTING_ENABLED`, `BOOKS_POSTING_INTERVAL_S` | books posting worker (600 s) |
| `DIET_MEAL_TIMES` | meal cut-off times for the kitchen sheet |
| `FINANCE_PIN` | four-digit PIN for money screens (single shared value — see §11) |
| `LOG_LEVEL`, `LOG_FORMAT` (`json`/`pretty`), `LOG_REQUESTS` | logging |

The API refuses to start in production with the shipped default secrets.

---

## 4. Architecture

```
browser ──HTTPS/WSS──► nginx ──► FastAPI (app/main.py)
                                 ├─ middleware: request id + request log, rate limit, security headers
                                 ├─ api/v1/routes/*   permission check → service → commit → audit
                                 ├─ services/*        operations, raise <Area>Error
                                 ├─ <domain>/rules.py pure rules (unit tested)
                                 ├─ workers           delivery retry · room charges · books posting
                                 └─ ws/*              voice intake, dictation (in-memory sessions)
                                        │
                              PostgreSQL + media volume (recordings, uploads, PDFs)
```

Full layout and the "adding a feature" recipe: [STRUCTURE.md](STRUCTURE.md).

**Background workers** (started in `main.py` lifespan, each guarded against
double runs):

| Worker | File | Does |
|---|---|---|
| delivery retry | `services/delivery_service.py` | retries WhatsApp/SMS sends |
| room charges | `ipd/room_charges.py` | posts daily bed/nursing charges; records a `JobRun` |
| books posting | `accounts/worker.py` | posts bills, receipts, advances and settlements to the books; `JobRun` "books_posting", Postgres advisory lock |

Run workers on one replica only. Voice sessions are held in memory: multiple
API replicas need sticky WebSocket routing.

---

## 5. Conventions that must be kept

- **Money is integer paise** end to end. UI converts with `rupeesToPaise` / `formatINR`.
- **Document numbers are gapless**, from `DocumentCounter` (scope, period) with `SELECT … FOR UPDATE`. Examples: invoices, receipts, `CLM/26-27/00001` claims, `SL|RC|PY|JV|CT/26-27/00001` vouchers, `CP/26-27/0001` payouts.
- **Nothing clinical or financial is deleted.** Cancel, refund, reverse or amend — with a reason, attributed to a user.
- **Signed documents are immutable.** Amend creates a new signed version; the original stays readable.
- **Every write that matters is audited** via `app/core/audit.record` with an `AuditAction` (new values need an `ALTER TYPE audit_action ADD VALUE` migration).
- **Permissions, not roles, in routes.** `require_permission(Permission.X)`; the role mapping lives only in `core/permissions.py`.
- **Finance endpoints also need** the `X-Finance-Unlock` header (a 30-minute token from `POST /finance/verify-pin`).
- **Sensitive outputs must not guess.** Where a report, reading or reconciliation cannot be sure, it says "Report unclear, please go through manually" or flags the item — never a fabricated or plugged value. This is a standing instruction from the hospital.

---

## 6. Modules added in Parts 3–5 (map)

| Area | Rules | Service | Routes | Frontend | Migration |
|---|---|---|---|---|---|
| Visit Pad | `pads/sections.py`, `pads/forms.py`, `pads/defaults.py` | `pad_service.py` | `/pads` | `components/pad` | ≤0023 |
| Laboratory | `lab/rules.py`, `lab/defaults.py` | `lab_service.py` | `/lab` | `(lab)`, `components/lab` | 0024 |
| Dietary | `diet/rules.py` | `diet_service.py` | `/diet` | `components/diet`, `ipd/diet-panel.tsx` | 0025 |
| Receipted advances | — | `reception_service.py`, `ipd_service.py` | `/ipd/admissions/{id}/advance` | `ipd/take-advance.tsx` | 0026 |
| Books & payouts | `accounts/chart.py`, `posting.py`, `payout.py` | `accounts_service.py`, `payout_service.py` | `/finance/accounts` | `components/accounts` | 0027 |
| TPA / insurance | `insurance/rules.py` | `insurance_service.py` | `/insurance` | `components/insurance` | 0028 |
| Consultant register | — | (in route) | `/masters/consultants` | `components/settings` | 0028 (audit) |
| Reports | `reports/ledger_rules.py`, `reports/sources.py` | report builders | `/reports/{key}` | `components/reports` | — |

### How the books work
Accounting entries are **derived**, never typed twice. `AccountsService.run_posting`
turns each source record (bill, receipt/refund, wallet entry, legacy advance,
claim settlement) into a voucher draft with pure functions in
`accounts/posting.py`, fingerprints it, and:
posts it if new · leaves it if unchanged · **reverses and re-posts** it dated on
the change if the source changed or was cancelled. A partial unique index allows
one live voucher per source, so re-running posting never double-posts. A draft
that does not balance is refused and listed as an exception — never plugged.

### How TPA claims work
Claim status flow and every amount check are in `insurance/rules.py`. The
payer's approved share is **booked to the bill as an insurance-mode payment**
(books: Dr insurance receivable, Cr patient debtors). Settlements record
received + TDS + disallowed and post Dr bank / TDS receivable / claim deductions,
Cr insurance receivable. Insurance-mode payments are excluded from every
"collected" figure. A booking struck at the counter is detected on the next read
of the claim and noted in its history.

---

## 7. Roles

Seven roles: admin, manager, doctor, supervisor, reception, nurse, lab. The
matrix is generated into [ROLES.txt](ROLES.txt). Screen links in
`components/dashboard/sidebar.tsx` carry a role list that must match the
permission the screen's API needs — a mismatch shows users a link that fails with
"Requires permission" (this happened with Finance and was fixed).

Landing page by role: nurse → `/ward`, lab → `/lab`, reception/supervisor →
`/reception`, everyone else → `/dashboard` (`homeFor` in `auth-provider.tsx`).

---

## 8. Logging and debugging

Every request logs one line (method, path, status, duration, user); refusals log
`http_error` with the reason; invalid forms log `validation_error` with field
names (never values). Every line carries `request_id` and `user_id`. Error
responses return `request_id`, the browser console prints it, and server errors
show it to staff as "(reference …)".

```bash
docker logs satya-backend 2>&1 | grep <request_id>
```

Details: [LOGGING.md](LOGGING.md). Never log request bodies or clinical text.

---

## 9. Testing

```bash
docker cp backend/tests/. satya-backend:/app/tests/
docker exec satya-backend pip install -q pytest pytest-asyncio   # lost on every container restart
docker exec satya-backend python -m pytest tests/unit -q -p no:warnings
cd frontend && npx tsc --noEmit && npx next lint
```

- **539 unit tests** pass (pure rules: billing, posting, payouts, claims, diet, lab, pads, logging, permissions…).
- **End-to-end checks** for books/payouts and TPA were run as throwaway scripts against the live database with a temporary patient and full cleanup. When writing such scripts, restore each document counter to **max(snapshot, highest number still in use)** — restoring a plain snapshot once left the journal voucher counter behind an existing number.
- No browser automation. Screens were verified by typecheck, lint, build and API calls, not by clicking through.

---

## 10. Data state on the hospital machine

- Test data exists from development (demo patients, `IP26-00002` still admitted; room charges resume from `BED_CHARGE_POST_FROM`).
- The books tie out: patients receivable = what bills owe; income = gross billed; cash = tills; patient advances = wallet balances.
- For the accountant: **Suspense ₹1,000** (an old wallet defect on RCP/26-27/000024), **advances not receipted ₹10,005** (advances typed before receipts existed), and RCP/26-27/000026 (₹500) posted as cash although no cash arrived.
- No consultant has payout terms (both 0%); no ledger opening balances are set.
- Organisations register holds only one corporate payer; TPAs must be added before claims can pick a payer (no screen yet — API only).
- No nurse account exists; lab tests need price codes and a reference-range review.

---

## 11. Open work, in priority order

### Safety and correctness
1. **Cascade deletes**: 29 relationships would delete clinical records if a patient row is deleted. Change to RESTRICT + soft delete.
2. **Audit trail** is best-effort, editable by the app's DB user, and has no viewer; patient-record opens are not all logged.
3. **Finance PIN** is one shared value in config; default seeded passwords live in config.
4. **LAN runs plain HTTP**; nothing is encrypted at rest; backups are same-host with 30-day retention.

### Missing screens (API exists, no UI)
Organisations/TPAs and rate cards · price list editing · amending a raised bill · wards and beds set-up · referring doctors · registration form fields · print set-up · audit viewer · financial-year selection.

### Remaining scope
- Marg pharmacy import (needs a Marg export sample, or a decision to read cash-memo photos with human confirmation).
- Tally sync (needs ledger mapping and the pharmacy double-count decision).
- Scheduled SMS/WhatsApp; Onito history import (needs database access); cutover.
- TPA: recovering a disallowed amount from the family is not built (write-off only).
- ABDM (M1–M3), security governance and NABH traceability are planned, not started — see the compliance roadmap artifact.

### Code health
Large files to split when next reworked: `services/pad_service.py`, `reception_service.py`, `ipd_service.py`, `frontend/lib/staffApi.ts`, `components/pad/visit-pad.tsx`, `components/lab/lab-request-view.tsx`. Create a root `.env.example`. Add CI gates for unit tests, lint and build.

---

## 12. First day

1. Read [STRUCTURE.md](STRUCTURE.md), then this file's §5 conventions.
2. Bring the stack up, run migrations, run the unit tests.
3. Read one full vertical slice: `insurance/rules.py` → `services/insurance_service.py` → `api/v1/routes/insurance.py` → `components/insurance/`.
4. Read `accounts/posting.py` and `services/accounts_service.py::run_posting` before touching anything that creates or changes a bill, receipt or advance — every such change reaches the books.
5. Trace one request in the logs using its `request_id`.
