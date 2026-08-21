# Satya Hospital AI Platform

Voice-first patient intake and a clinical console for **Satya Hospital, Kanpur** —
Orthopedics (Dr. A K Agarwal) and Gynecology (Dr. Manisha Agarwal).

A patient registers, taps **Start consultation**, and has a natural spoken
conversation in Hindi, English or a mix of both. By the time they reach the
consulting room the doctor already has a structured history, a risk assessment,
suggested differentials and investigations, and a copilot that points at what
deserves attention. The doctor orders tests by voice or search, uploads the
reports that come back, dictates a prescription, and sends it to the patient's
WhatsApp — without typing a page of notes.

**Every AI output in this system is advisory. The treating doctor is the final
authority on every clinical decision.** That is enforced in the code, not just
written in the interface: safety warnings must be acknowledged before a
prescription can be issued, abnormal lab values are decided arithmetically
rather than by a model, and each AI suggestion is stored separately from the
clinician's ruling on it.

---

## Quick start

```bash
cp .env.example .env          # set SARVAM_API_KEY and JWT_SECRET_KEY at minimum
docker compose up --build     # development
```

- Patient intake: http://localhost:3000
- Clinical console: http://localhost:3000/login
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

For production, follow **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** and work
through **[docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md)**.

> Microphone capture requires a secure context. `localhost` works; any other
> host needs HTTPS or voice intake will not start.

---

## What it does

### Patient voice intake
Continuous conversation with no push-to-talk. Audio streams to Sarvam STT, the
reply streams from the LLM, and completed sentences go to TTS the moment they
close — so the assistant starts speaking before it has finished thinking.
Interruption works on two independent layers: the browser's voice detector
flushes playback instantly, and the server cancels the in-flight generation. The
platform, not the model, decides when enough has been collected.

### Clinical pipeline
Eight services turn the conversation into a record: conversation AI, symptom
extraction, medical JSON, risk detection, clinical summary, differentials,
investigation suggestions and patient education. Emergency detection runs in two
layers — deterministic phrase matching in English, Hinglish and Devanagari that
fires instantly, then LLM reasoning over the structured record for combinations
patterns cannot see.

### Doctor dashboard
Waiting, live and completed queues; patient search and longitudinal history;
consultation detail with summary, history, transcript, timeline and the recorded
audio. The copilot surfaces red flags, differentials, investigations, follow-up
questions, referrals, and medication alerts — each labelled, each dismissible,
each decision attributed.

### Investigations
A 101-test catalog across 11 categories with favourites, recent, templates and
12 common panels. Reports upload as PDF, photo or scan; text is extracted (OCR
for scans) and **values are compared against reference ranges arithmetically**,
never by a model. The range printed on the report wins over the built-in table,
and when units cannot be reconciled the result is marked "not compared" rather
than guessed. Versions supersede rather than overwrite.

### Prescriptions
Dictate naturally — *"Tablet Paracetamol 650 mg SOS. Tablet Pantoprazole 40 mg
before breakfast."* — and the parser separates form, drug, strength, frequency,
timing and duration into an editable form. Substitutions are surfaced, not
silent. Duplicate, allergy, interaction and pregnancy checks are rule-based and
instant. The result is an A4 sheet with letterhead, QR verification, prescription
ID and signature, deliverable to WhatsApp with tracked, retried delivery.

---

## Architecture

```
                    ┌──────────────┐
   patient ────────▶│   Next.js    │◀──────── doctor
   (voice)          │  App Router  │        (dashboard)
                    └──────┬───────┘
                           │ HTTPS / WSS
                    ┌──────▼───────┐
                    │    Nginx     │  TLS, rate limits, WebSocket upgrade
                    └──────┬───────┘
                    ┌──────▼───────┐
                    │   FastAPI    │  RBAC, audit, rate limiting, metrics
                    ├──────────────┤
                    │  services    │  consultation, investigation,
                    │  repositories│  prescription, copilot, delivery
                    ├──────────────┤
                    │  ai/         │  provider-agnostic gateway + pipeline
                    │  investigations/  catalog, ranges, OCR, parsing
                    │  prescriptions/   formulary, dictation, safety, PDF
                    │  messaging/  │  WhatsApp Cloud | Twilio | console
                    └──┬────────┬──┘
                       │        │
              ┌────────▼──┐  ┌──▼──────┐   ┌──────────────┐
              │ PostgreSQL│  │  Redis  │   │  Sarvam AI   │
              │  + media  │  │ cache,  │   │ STT/TTS/LLM  │
              │  volume   │  │ limits  │   └──────────────┘
              └───────────┘  └─────────┘
```

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 App Router, TypeScript (strict), Tailwind, shadcn/ui, Framer Motion |
| Backend | FastAPI, SQLAlchemy 2 async, asyncpg, repository pattern, dependency injection |
| Database | PostgreSQL 16, Alembic migrations |
| Cache | Redis, with an in-process fallback for single-node deployments |
| Voice | Sarvam streaming STT and TTS over WebSockets, AudioWorklet capture |
| AI | Provider-agnostic gateway: Sarvam, OpenAI, Anthropic, Groq, vLLM |
| Documents | ReportLab (A4 prescriptions), pypdf + Tesseract (report extraction) |
| Ops | Docker, Nginx, Prometheus metrics, JSON logging, GitHub Actions |

### Design principles

**Deterministic where it matters.** Anything a model could get subtly and
dangerously wrong is computed instead. Abnormal lab values come from arithmetic.
Duplicate medicines and allergy conflicts come from an ingredient map. Emergency
red flags come from phrase matching. Language models write narrative and ask
questions — they do not decide whether a number is out of range.

**Provider independence.** The LLM, the messaging channel and the cache are each
behind an interface with more than one implementation. Switching vendors is a
configuration change.

**Additive schema.** Every phase added tables rather than altering them, so the
platform could grow through five phases without a destructive migration.

---

## Repository layout

```
backend/
  app/
    core/           config, logging, security, cache, rate limiting,
                    permissions, audit, uploads, middleware, metrics
    db/             async engine, session, declarative base
    models/         User, Patient, Consultation, Investigation,
                    Prescription, MessageDelivery, AuditLog
    repositories/   data access, one per aggregate
    services/       consultation, patient, copilot, investigation,
                    prescription, delivery
    ai/             provider gateway, 8-stage pipeline, session memory,
                    emergency screening, recording
    investigations/ catalog, reference ranges, OCR, report parsing
    prescriptions/  formulary, dictation parser, safety rules, PDF
    messaging/      WhatsApp Cloud, Twilio, console
    api/            DI, RBAC, versioned routes
    ws/             patient intake and doctor dictation sockets
  alembic/          migrations
  tests/            unit (no I/O) and integration (real PostgreSQL)
  scripts/          demo data seeding
frontend/
  app/(patient)/    intake and live consultation
  app/(dashboard)/  queues, patients, consultation detail
  components/       ui primitives, dashboard, investigations, prescriptions
  lib/              API clients, audio capture and playback, types
deploy/
  nginx/            reverse proxy with TLS and WebSocket support
  scripts/          backup, restore, migration entrypoint
docs/               API reference, deployment guide, production checklist
```

---

## Development

```bash
# Backend
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Tests
cd backend
pytest -m unit                              # fast, no services needed
docker compose up -d db && pytest -m integration
ruff check app tests
```

See **[backend/tests/README.md](backend/tests/README.md)** for the testing
strategy and why external AI calls are deliberately not mocked.

---

## Documentation

| Document | Contents |
|---|---|
| [docs/EMR.md](docs/EMR.md) | Reception and billing, and migrating patient data off the current software |
| [docs/API.md](docs/API.md) | Every endpoint, roles, rate limits, worked examples |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Server setup, TLS, migrations, backups, scaling |
| [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md) | Pre-go-live checklist and known limitations |
| [backend/tests/README.md](backend/tests/README.md) | Testing strategy |

---

## Clinical safety

This platform prepares and suggests. It does not diagnose, prescribe or decide.

- Every AI-generated element in the interface carries an explicit label
- Deterministic rule checks are labelled differently from model inference, so a
  doctor can always tell arithmetic from judgement
- Serious safety warnings must be acknowledged before a prescription is issued —
  enforced by the API, not only the UI
- The AI never marks its own work as reviewed; sign-off requires a clinician
- Front-desk staff can read records and upload reports but hold no clinical
  authority of any kind
- Every access to a patient record and every clinical action is audited

Before go-live, a doctor must review the emergency phrase list, the drug
interaction table and the laboratory reference ranges against local practice.
These are in the production checklist as blocking items.
#   h o s p i t a l _ v o i c e _ c o n s u l t a t i o n  
 