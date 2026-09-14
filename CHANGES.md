# Changes on top of v2.7

## 1. The transcript now scrolls itself

`frontend/app/(patient)/consultation/[id]/page.tsx`

There *was* already a `scrollTo` call, but it could never work: the transcript
section had no bounded height, so `overflow-y-auto` never engaged. The section
simply grew and the whole page scrolled instead, which is why the patient had
to scroll by hand.

The panel now has a bounded height (`clamp(320px, 60vh, 620px)`) so the inner
container genuinely scrolls, and it follows new lines as they arrive.

Two details worth knowing:

- **It stops following if the patient scrolls up.** Reading back over an
  earlier answer should not be interrupted by being yanked to the bottom
  mid-sentence. Scrolling back within ~80px of the bottom resumes following.
- **The jump is instant, not smooth.** The assistant's reply arrives word by
  word, so this fires many times per second; smooth scrolling queues
  animations faster than they finish and visibly lags behind the text.

## 2. Patients can upload previous reports after the intake

New: `backend/app/api/v1/routes/patient_uploads.py`,
`frontend/components/patient/previous-reports-upload.tsx`

When the call ends, the transcript panel is replaced by an invitation to
photograph or upload any earlier reports the patient has brought. It is the
right moment — they are holding their file of old X-rays and blood tests while
they wait to be called, and a photo taken then is on the doctor's screen
before the consultation rather than handed across the desk halfway through it.

- **Authentication** is the consultation session token the patient already
  holds. There is no patient login and this does not create one: the token
  grants exactly one capability — attaching a file to one consultation — and
  expires with the visit.
- **Uploads go through the existing pipeline**, so content is validated by
  magic bytes rather than filename, and files are put through text extraction
  and reference-range analysis. The doctor sees values, not just an attachment.
- **On a phone, "Take a photo" opens the camera directly**, which is how most
  patients will actually do this.
- Capped at 10 files per visit.

On the doctor's side, the Investigations tab now shows a highlighted **Reports
the patient brought** panel above the request list, with each file openable.
`uploaded_by_id` was already nullable, so a patient upload needed no schema
change.

## 3. Hindi no longer prints as black boxes

`backend/app/prescriptions/pdf.py`, `backend/Dockerfile`

ReportLab's built-in Helvetica has no Devanagari glyphs, so Hindi general
instructions rendered as boxes. The renderer now registers a Devanagari-capable
family (Noto Sans Devanagari if present, otherwise FreeSans or DejaVu) and uses
it throughout, and the Docker image installs `fonts-freefont-ttf` and
`fonts-indic`.

I rendered a prescription with Hindi in the chief complaint, a medicine
instruction, the general instructions and the follow-up, rasterised it and
checked it by eye: matras and conjuncts position correctly.

If no suitable font is found, the renderer logs `no_devanagari_font_found` and
falls back to Helvetica — an English sheet rather than no sheet. The health
endpoint reports `"devanagari": true/false` so this is visible before a patient
is handed the paper.

## 4. Follow-up is a dropdown, and sets medicine duration

`frontend/lib/prescriptionTypes.ts`,
`frontend/components/prescriptions/prescription-composer.tsx`,
`frontend/components/prescriptions/medicine-row.tsx`

Follow-up is now chosen from **After 3 / 5 / 7 / 10 / 14 days**, and choosing
one sets every medicine's duration to the interval **plus one day** — so the
patient does not run out the morning they are due back.

Two rules keep this from doing damage:

- **A row the doctor has already given a duration is left alone.** A
  three-month calcium course is not cut to eight days because the review is
  next week.
- **Typing a duration takes ownership of it.** Changing the follow-up interval
  afterwards will not overwrite what the doctor typed.

---

# Something you should know about this baseline

The uploaded v2.7 has only **part** of the speech-safety fix applied:

| File | Status in the upload |
|---|---|
| `app/core/config.py` | applied |
| `tests/unit/test_speech_safety.py` | applied |
| `app/ai/streaming_json.py` | **missing** |
| `app/ai/pipeline/conversation_ai.py` | **missing** |
| `app/ai/orchestrator.py` | **missing** |

Two consequences:

**`HALF_DUPLEX_ENABLED` is a dead setting.** It sits in config but nothing in
the codebase reads it — the microphone gating lives in `orchestrator.py`, which
was not applied. Turning it on or off currently does nothing.

**The extractor hardening was missing**, which is why `test_speech_safety.py`
was failing. Without it, a model reply that is not valid JSON is read to the
patient verbatim — including field names and backticks, the
`` : ["pain_location"] `conversation_complete`: `` bubble you saw. I have
applied `streaming_json.py` and the matching `conversation_ai.py` change here,
because they govern *what gets spoken* rather than turn-taking and so cannot
disturb what is currently working for you.

**I did not apply `orchestrator.py`**, because that one changes turn-taking and
you have said the current behaviour works. If echo ever returns, that is the
file to add — and `HALF_DUPLEX_ENABLED` starts working the moment you do.

---

# Reception moved out of the clinical dashboard

## What changed

Reception is now its own page at `/reception`, in its own route group with its
own shell. It is no longer in the doctor's sidebar.

**New**
- `frontend/app/(reception)/layout.tsx`
- `frontend/app/(reception)/reception/page.tsx`
- `frontend/components/reception/reception-shell.tsx`

**Removed**
- `frontend/app/(dashboard)/reception/` — the old route

**Edited**
- `components/dashboard/sidebar.tsx` — Reception entry removed
- `components/dashboard/auth-provider.tsx` — accepts `allow` / `fallbackPath`
- `app/(dashboard)/layout.tsx` — clinical shell is now admin and doctor only
- `app/login/page.tsx` — lands each role on their own screen
- `middleware.ts` — `/reception` and `/finance` added to the matcher

## Why it is a different shell, not just a different URL

The front desk runs one screen all day on a fixed machine. The clinical
sidebar is six links to consultations and prescriptions that a clerk cannot
open, so the reception terminal drops navigation entirely and gives the counter
the full width.

Today's queue sits beside the counter rather than on another page, because
"what token are we on" is asked constantly and should not cost a click. It
refreshes every 20 seconds, and a failed refresh says so — an empty queue and
a broken request otherwise look identical, and the difference matters at a
counter.

## Who lands where

| Role | After signing in | Clinical dashboard | Reception |
|---|---|:--:|:--:|
| Staff | `/reception` | redirected to `/reception` | yes |
| Doctor | `/dashboard` | yes | yes |
| Admin | `/dashboard` | yes | yes |

Doctors and admins keep access to the counter — someone covering the desk at
lunch should not have to sign in as somebody else — and get a "Clinical
dashboard" button in the reception header to get back. Staff are not shown
that button, because it would only lead to a redirect.

An explicit `?next=` still wins over the role default, so the middleware can
return someone to the page they were originally trying to reach.

## Two things fixed while in here

**`/reception` and `/finance` had no edge guard.** They were missing from the
middleware matcher, so an unauthenticated visit rendered an empty shell instead
of redirecting to the login page. Nothing leaked — the API refused every
request — but a clerk whose session had expired got a blank screen with no
explanation rather than a login prompt.

**Role gating is now explicit in the shell.** Previously any signed-in user
could load the clinical dashboard and simply find every panel empty or
erroring. This is convenience rather than security: the API enforces
permissions on every request, and that has not changed.

---

# Three terminals, and the reception → intake handover

## The three URLs

| URL | Who | What |
|---|---|---|
| `/reception` | Staff, doctor, admin | Register, bill, collect, cash drawer |
| `/intake` | Staff, doctor, admin | Queue of registered patients → start voice intake |
| `/dashboard` | Doctor, admin | Clinical: consultations, prescriptions, finance |

Each has its own shell and its own route group. Signing in lands staff on
`/reception` and clinicians on `/dashboard`; an explicit `?next=` still wins.

## The handover — no re-entering details

Previously `/consultations/start` created a patient from a typed-in form. Used
after reception had already registered someone, that produced **a second
patient record** for the same person, with their history split across both.

Now:

1. Reception registers and bills → a `Visit` with a token.
2. `/intake` lists everyone registered today who has not started
   (`GET /reception/intake-queue`).
3. Tapping a patient calls `POST /consultations/start-from-visit` with only
   the visit id. Patient, department and demographics come from the record.
4. The visit flips to `in_consultation` and links to the consultation, so
   reception can see who has gone in.

**Verified against live PostgreSQL:** three patients registered, all three
appear in the queue, department filter works, starting one reuses the existing
patient record, that patient leaves the queue, a second terminal attempting the
same visit is refused with 400, reception sees the status change, and the
database still holds exactly three patients — no duplicates anywhere in the
flow.

The endpoint is staff-only, unlike the public `/start`: it trusts a visit id
the counter created, so it must not be callable by anyone who can guess one.

The session token is written to `sessionStorage` before navigating rather than
passed in the URL, where it would persist in browser history and server logs.

## Cash drawer moved to reception

`components/finance/cash-counter.tsx` — extracted from the finance dashboard
and placed on the reception terminal, where the cashier who holds the drawer
actually sits. Hospital-wide revenue stays on `/finance`, matching the
permission model: `FINANCE_READ` is admin and doctor only.

The component degrades properly for a clerk without that permission — the
expected-cash figure comes from the collections summary, and if that call is
refused the open/close still works without it.

## Also

`/intake` added to the middleware matcher, alongside `/reception` and
`/finance` from the previous change.

---

# IPD integrated (build fix)

The IPD module was copied in without Step 2 of its integration guide, so
`ward-board.tsx` called `staffApi.wardBoard()` and friends, which did not
exist. `npm run build` failed at the type-check stage.

Now applied in full and verified:

**Backend** — `app/ipd/`, `models/ipd.py`, `services/ipd_service.py`,
`schemas/ipd_schemas.py`, `api/v1/routes/ipd.py`, `ai/ipd_documentation.py`,
migration `0004_ipd`, `scripts/seed_wards.py`, `tests/unit/test_ipd.py`.
Wired: enums appended, models registered, `get_ipd_service` in deps, router
included.

**Frontend** — `lib/ipdTypes.ts`, `components/ipd/ward-board.tsx`,
`app/(dashboard)/ipd/page.tsx`. Wired: eleven IPD methods added to
`lib/staffApi.ts`, "Ward board" added to the sidebar, `/ipd` added to the
middleware matcher.

Verified: `npm run build` completes, all 15 routes compile, 0 type errors,
217 backend tests pass.

After deploying, run the migration and seed the wards:

```bash
docker compose -f docker-compose.prod.yml run --rm migrate
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed_wards
```
---

# IPD ward panel added

## New

```
frontend/components/ward/ward-shell.tsx
frontend/components/ward/ward-panel.tsx
frontend/app/(ward)/layout.tsx
frontend/app/(ward)/ward/page.tsx
```

## Modified — grafted, not replaced

```
backend/app/services/ipd_service.py      + finalise_billing()
backend/app/api/v1/routes/ipd.py         + 3 routes
frontend/lib/staffApi.ts                 + 4 methods
frontend/middleware.ts                   + /ward in the matcher
```

Every one of these was edited in place rather than overwritten, so the finance
PIN work (`verifyFinancePin`, `finance_unlock`, the `/reception/patients`
screen) is untouched. A previous handover replaced `staffApi.ts` wholesale and
deleted `verifyFinancePin`, which is what broke that build.

## The gap this closes

`Admission.final_invoice_id` existed and nothing ever wrote to it. Charges
accrued against a stay, the running total was right, and the patient was
discharged with **no bill ever raised** — so every rupee of inpatient revenue
was invisible to the finance screens.

`POST /ipd/admissions/{id}/invoice` now converts accrued charges into a
numbered invoice in the same sequence as OPD.

Two decisions worth knowing:

- **Charges are grouped by category.** A three-week stay accrues twenty-one bed
  rows; a family handed a fifty-line bill for one repeated item cannot check
  it. The bill reads "Bed charges (21 days)"; the detail stays on the admission.
- **The advance is applied directly, not through `record_payment`.** It was
  taken at admission, often days earlier at another counter — routing it
  through today's cash session would make tonight's drawer look over by the
  whole deposit.

## The panel — `/ward`

The bed is the object you tap; there is no separate admissions page.

- **Vacant bed → admit.** Search existing patients by UHID, mobile or name, or
  register new. Ward registration uses the same UHID allocator as reception, so
  an emergency admission bypassing OPD still gets a real hospital number.
- **Occupied bed → bedside sheet.** Running bill by category, plus charge entry.
- **Discharge in three steps:** raise bill → draft summary → release bed.
  Deliberately separate — one button would let a patient leave with an unsigned
  summary or an unpaid balance. The bed cannot be released until the bill is
  raised, because charges cannot be added once the admission closes.

NEWS2 alerts (≥5) sit in a banner above the grid; a live census sits in the
header.

## Verified

- 217 unit tests pass.
- Production build compiles; 17 routes including `/ward`, `/reception/patients`
  and `/finance`. 0 type errors.
- All four migrations apply from empty; both seeds run.
- Live run: register → admit → charge → accrue → invoice (advance applied,
  balance correct) → discharge → bed released → **IPD revenue visible in
  finance behind the PIN gate**.
- Finance PIN confirmed still working: 403 without, 200 with.

## Access

`/ward` allows admin, doctor and staff. `/dashboard` allows admin and doctor
only, so an IPD incharge signing in as staff has no route into consultations,
prescriptions or revenue.

**Caveat:** ward incharge and reception clerk are both `staff`, so either can
open the other's terminal by URL. Separating them needs a fourth role — an enum
value, a Postgres ALTER TYPE, a permissions entry.

## Not built

Insurance pre-auth and claims (data model and endpoints exist, no interface),
operation theatre, diet orders, blood bank, nursing care plans, appointments,
consultant payouts, lab as a walk-in billing counter.

Recommended insurance split: **pre-auth in the ward panel** (part of the
admission decision), **claims tracking on a separate desk** (different person,
weeks later, needs a view across patients rather than a bedside view).
