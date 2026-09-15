# Satya Hospital AI Platform
## Full-stack developer handoff

**Repository:** `hospital_voice_consultation-main`  
**Frontend:** Next.js 14, React 18, TypeScript, Tailwind CSS  
**Backend:** FastAPI, SQLAlchemy 2 async, asyncpg, Alembic  
**Data and infrastructure:** PostgreSQL 16, Redis or in-process fallback, Docker, Nginx  
**AI and documents:** Sarvam STT/TTS/LLM, provider gateway, Tesseract OCR, ReportLab PDFs

This document is an engineering orientation guide. The existing [README](../README.md), [API reference](API.md), [deployment guide](DEPLOYMENT.md), [EMR notes](EMR.md), and [production checklist](PRODUCTION_CHECKLIST.md) remain the authoritative detailed references.

## 1. What the product does

Satya Hospital is a voice-first patient intake and clinical support platform for Orthopedics and Gynecology. A patient speaks in Hindi, English, or Hinglish; the system records the conversation, extracts structured medical facts, detects emergency signals, and prepares a record for clinician review.

The platform also supports:

- Reception registration, visits, billing, payments, and cash sessions.
- A reception-to-intake handoff that reuses the same patient and visit records.
- Doctor and admin clinical dashboards with queues, history, transcripts, recordings, and AI copilot suggestions.
- Investigation catalog, orders, report uploads, OCR, and arithmetic reference-range analysis.
- Voice-dictated prescriptions, safety checks, A4 PDF generation, QR verification, and WhatsApp delivery tracking.
- Role-based access control, audit logging, rate limiting, health probes, metrics, and structured JSON logs.

AI output is advisory. A doctor must make the clinical decision and sign off the consultation or prescription.

## 2. Start here

### Local development

Prerequisites: Docker Desktop, Python 3.12, Node.js/npm, and a Sarvam API key for real voice flows.

```powershell
# From repository root
Copy-Item .env.example .env       # See configuration note below
docker compose up --build

# Or run services separately
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

cd ..\frontend
npm install
npm run dev
```

Local URLs:

- Patient intake: `http://localhost:3000`
- Staff login: `http://localhost:3000/login`
- API docs: `http://localhost:8000/docs`
- Liveness: `http://localhost:8000/api/v1/health/live`
- Readiness: `http://localhost:8000/api/v1/health/ready`

Microphone capture works on `localhost`; any non-local deployment requires HTTPS/WSS.

### Important configuration note

The current workspace does **not** contain the `.env.example` referenced by the README and deployment docs. Until it is restored or created, use `backend/app/core/config.py` as the complete settings inventory and copy the required production values from `docs/DEPLOYMENT.md`. Never use the shipped default secrets in production: the API intentionally refuses to start with them.

At minimum configure `POSTGRES_*`, `JWT_SECRET_KEY`, the seeded account passwords, `SARVAM_API_KEY`, `CORS_ORIGINS`, `PUBLIC_BASE_URL`, and `PUBLIC_WS_URL`. Configure WhatsApp or Twilio only when that delivery provider is enabled.

## 3. Runtime architecture

```text
Patient browser                 Staff/doctor browser
  Next.js patient UI              Next.js role-based UI
          | HTTPS / WSS                    | HTTPS
          +----------------+---------------+
                           v
                         Nginx
                           |
                         FastAPI
       +-------------------+--------------------+
       |                   |                    |
   Services          AI gateway/session     Clinical modules
       |                   |                    |
       +-------------------+--------------------+
               PostgreSQL + media volume
               Redis/cache fallback
               Sarvam or configured AI provider
```

Backend startup in `app/main.py` is deliberate:

1. Validate production configuration.
2. Verify required tables exist; schema creation is not performed at boot.
3. Seed configured default accounts on first boot.
4. Check cache and messaging-provider configuration.
5. Start the delivery retry worker and mark readiness.

Shutdown stops readiness, drains workers/sessions, closes providers, and disposes the database engine.

## 4. Repository map

### Backend

- `backend/app/main.py`: FastAPI application, middleware, startup/shutdown, exception handling.
- `backend/app/core/`: settings, security, permissions, audit, cache, rate limits, uploads, logging, metrics.
- `backend/app/db/`: async engine, sessions, base model metadata.
- `backend/app/models/`: SQLAlchemy entities and enums.
- `backend/app/schemas/`: request/response contracts.
- `backend/app/repositories/`: database access patterns.
- `backend/app/services/`: business workflows and transaction boundaries.
- `backend/app/ai/`: LLM gateway, prompts, session management, extraction, emergency screening, STT/TTS, streaming JSON.
- `backend/app/ai/pipeline/`: conversation and clinical processing stages.
- `backend/app/investigations/`: catalog, reference ranges, OCR, report parsing.
- `backend/app/prescriptions/`: formulary, dictation parser, medication rules, PDF generation.
- `backend/app/messaging/`: console, WhatsApp Cloud, and Twilio providers plus retries.
- `backend/app/api/v1/routes/`: REST route modules.
- `backend/app/ws/`: consultation and doctor dictation WebSockets.
- `backend/alembic/versions/`: ordered schema migrations. Add a migration for every schema change.
- `backend/scripts/`: seed, import, backfill, and operational scripts.

### Frontend

- `frontend/app/(patient)/`: public intake and live consultation pages.
- `frontend/app/(reception)/`: reception shell and counter workflows.
- `frontend/app/(intake)/`: registered-patient queue and consultation start handoff.
- `frontend/app/(dashboard)/`: clinical dashboard for doctors/admins.
- `frontend/app/(ward)/`: ward/IPD workflows.
- `frontend/components/`: feature components grouped by domain.
- `frontend/lib/api.ts`: public API base URL and patient consultation start contract.
- `frontend/lib/staffApi.ts`: authenticated staff API client.
- `frontend/lib/hooks/useConsultation.ts`: patient WebSocket, microphone recording, PCM playback, transcript state, and session lifecycle.
- `frontend/lib/hooks/useDictation.ts`: doctor dictation WebSocket lifecycle.
- `frontend/lib/audio/`: AudioWorklet recorder and PCM player.
- `frontend/middleware.ts`: cookie-based route guard. This is UX protection only; backend authorization is authoritative.

## 5. Main user workflows

### Reception -> intake -> consultation

1. Reception searches an existing patient or registers a new one.
2. `POST /api/v1/reception/register-and-bill` atomically creates/reuses the patient, opens a visit, creates an invoice, and optionally records payment.
3. Intake reads `GET /api/v1/reception/intake-queue`.
4. Staff starts the selected visit with `POST /api/v1/consultations/start-from-visit`.
5. The response contains `consultation_id`, `session_token`, and `ws_path`. Store the session token in `sessionStorage`, not the URL.
6. The patient page connects to `/api/v1/ws/consultations/{id}?token=...` and streams 16 kHz PCM16 audio.
7. The completed consultation appears in the clinical queues for review.

Do not use the public `/consultations/start` for patients already registered at reception; it creates a new patient flow and can split history.

### Patient voice session

`useConsultation.ts` owns the browser session. It receives JSON events such as `session_ready`, `final_transcript`, `assistant_start`, `assistant_delta`, `assistant_end`, `interrupted`, and `session_ended`; audio responses arrive as binary PCM frames.

The backend orchestrates STT, turn handling, LLM response generation, TTS, transcript persistence, medical JSON extraction, and emergency detection. The current client-side barge-in behavior relies on server-side recognized speech rather than noisy local energy VAD. `HALF_DUPLEX_ENABLED` exists in configuration; verify the corresponding server turn-taking path before changing speech behavior.

### Clinical review

Doctors/admins use dashboard consultation routes to inspect the queue, patient history, consultation detail, transcript, recording, AI copilot, investigations, and prescriptions. A clinician explicitly records copilot accept/dismiss decisions and separately signs off the consultation. The AI cannot mark its own output as reviewed.

### Reports and investigations

Reports enter through validated multipart upload. The upload pipeline checks file content using magic bytes, extracts text/OCR where possible, and compares laboratory values arithmetically. A reference range printed on the report takes precedence; incompatible units become `not compared`, never a guessed result.

### Prescriptions

1. Doctor dictates or edits structured medicine rows.
2. Run the safety check against allergies, current medicines, interactions, duplicates, pregnancy concerns, and substitutions.
3. Serious alerts must be acknowledged before issue.
4. `POST /prescriptions` persists and renders the A4 PDF.
5. Delivery uses the configured provider and a retry worker; the delivery table is the source of tracking state.

## 6. API and authorization model

API base path is `/api/v1`. The complete route table and examples are in [API.md](API.md). Major route modules are `auth`, `consultations`, `patients`, `patient_uploads`, `investigations`, `prescriptions`, `reception`, `finance`, `ipd`, `health`, and `public_documents`.

Patients do not have staff accounts. A patient receives a short-lived token scoped to one consultation/WebSocket session. Staff authenticate with bearer JWTs.

| Capability | Admin | Doctor | Staff |
|---|---:|---:|---:|
| Read patients, consultations, reports, prescriptions | Yes | Yes | Yes |
| Upload reports | Yes | Yes | Yes |
| Order investigations | Yes | Yes | No |
| Create/send prescriptions | Yes | Yes | No |
| Review/sign off consultations | Yes | Yes | No |
| AI copilot | Yes | Yes | No |
| Audit logs/system administration | Yes | No | No |

Every backend endpoint must enforce authorization through dependencies and department scoping. Frontend middleware does not replace API checks.

Errors include a `request_id`; rate-limited responses include `Retry-After` and rate-limit headers. Preserve these contracts when adding API or UI behavior.

## 7. Database and media rules

PostgreSQL is the system of record. Use async SQLAlchemy sessions and the existing service/repository boundaries. Keep monetary amounts in paise and use the existing money helpers. Keep medical and audit writes transactional where the workflow requires consistency.

Run migrations explicitly:

```powershell
cd backend
alembic upgrade head
alembic revision --autogenerate -m "describe change"
```

Do not call `create_all` or edit an existing migration after it has been applied. Review autogenerated migrations manually.

The `MEDIA_ROOT` volume contains consultation recordings, uploaded reports, signatures, and prescription PDFs. Database backups alone are incomplete. Follow the backup/restore process in [DEPLOYMENT.md](DEPLOYMENT.md), and define retention before go-live.

## 8. Testing and quality gates

```powershell
cd backend
pytest -m unit
pytest -m integration
ruff check app tests

cd ..\frontend
npm run build
npm run lint
```

Unit tests target deterministic, high-risk logic without I/O: emergency phrases, reference-range parsing, medication rules, dictation, upload validation, permissions, and audio arithmetic. Integration tests require live PostgreSQL and roll back each test transaction. Real Sarvam, OCR, and WhatsApp flows are manual release checks because they require external credentials and real browser/device behavior.

When changing a clinical rule, add or update a focused unit test first. When changing a schema or API contract, add the migration and integration coverage. When changing voice behavior, manually test microphone permissions, Hindi/Hinglish, interruption, reconnect/restart, and session end.

## 9. Safe extension pattern

1. Identify the owning domain module and existing service/route/component pattern.
2. Update schemas/types before wiring UI behavior.
3. Put business rules in a backend service or deterministic domain module, not only in React.
4. Add authorization, department scoping, audit events, and rate limits where applicable.
5. Add an Alembic migration for persistent data.
6. Add focused tests and update `docs/API.md` or `docs/EMR.md` when contracts change.
7. Run the narrow test first, then the relevant full backend/frontend checks.

Avoid putting clinical decisions in prompts alone. Deterministic checks must remain authoritative over model suggestions.

## 10. Production and operational constraints

Production uses `docker-compose.prod.yml`: migration runner, PostgreSQL, backend, frontend, and Nginx TLS termination. Run migrations before the API. The production API docs are disabled unless explicitly enabled with debug settings.

The current design is primarily single-node:

- Cache and rate limits fall back to process-local state.
- Voice sessions are held in memory and require sticky WebSocket routing when scaling API replicas.
- Run the delivery retry worker on only one replica, or move it to a dedicated worker.
- Nginx must support WebSocket upgrade and HTTPS/WSS.
- Monitor readiness, database health, media disk usage, OCR memory use, delivery failures, and AI provider latency.

## 11. Known risks and first tasks

These are the highest-value items for the incoming developer:

1. Restore or create the missing root `.env.example` and keep it synchronized with `Settings` and deployment documentation.
2. Validate the configured half-duplex/echo-rejection path end to end before changing it; speech regressions are user-visible and difficult to diagnose.
3. Complete clinical review of emergency phrases, drug interactions, formulary substitutions, and laboratory ranges before real-patient use.
4. Add browser/device release checks for microphone permissions, HTTPS, WebSocket reconnects, Hindi TTS, report camera upload, and prescription PDF glyphs.
5. Review default seeded credentials and ensure all production secrets, TLS certificates, media backups, and retention policies are operational.
6. Establish CI gates for backend unit tests, integration tests with PostgreSQL, Ruff, frontend lint, and production build.
7. Audit route/API documentation whenever new reception, finance, IPD, investigation, or prescription behavior is added.

## 12. Useful first reading order

1. This handoff.
2. [README](../README.md) for product scope and terminology.
3. [API.md](API.md) for route/auth contracts.
4. `backend/app/main.py`, `backend/app/core/config.py`, and `backend/app/api/v1/router.py` for runtime wiring.
5. `backend/app/api/v1/routes/reception.py` and `consultations.py` for the primary handoff workflow.
6. `frontend/lib/hooks/useConsultation.ts` and `frontend/lib/api.ts` for the browser voice contract.
7. [EMR.md](EMR.md), [DEPLOYMENT.md](DEPLOYMENT.md), and [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) before operational or clinical changes.

## Disclaimer

This software supports intake and clinical decision support. It does not independently diagnose, prescribe, or make clinical decisions. All clinical decisions must be made and verified by a qualified treating doctor.
