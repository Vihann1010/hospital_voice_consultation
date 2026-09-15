# Project structure

Where things live, and where new code goes. Keep to this and the project stays
easy to find your way around.

```
hospital_voice_consultation-main/
├── backend/                FastAPI + SQLAlchemy (async) + Alembic
├── frontend/               Next.js 14 (app router) + Tailwind
├── deploy/                 nginx config, backup and restore scripts
├── docs/                   this file, logging, roles, API, deployment, change history
├── docker-compose.yml      local stack: db, backend, frontend
└── docker-compose.prod.yml production stack with nginx and TLS
```

## Backend — `backend/`

```
app/
├── main.py            app start-up, middleware, error handlers
├── core/              config, logging, security, permissions, audit, middleware
├── db/                engine, session, base model
├── models/            SQLAlchemy tables, one file per area (emr, ipd, lab, accounts…)
├── schemas/           Pydantic request/response models shared by several routes
├── repositories/      reusable queries for the busiest tables
├── services/          business operations: <area>_service.py
├── api/
│   ├── deps.py        sessions, current user, permission guards
│   └── v1/
│       ├── router.py  every route module is registered here
│       └── routes/    HTTP layer only: <area>.py
├── reports/           report definitions (one file per area) + runner
├── <domain>/          pure rules for one area, no database:
│                      accounts, billing, diet, insurance, investigations, ipd,
│                      lab, mrd, pads, prescriptions, theatre
├── ai/                voice intake pipeline, LLM providers, prompts
├── messaging/         WhatsApp / SMS providers
├── printing/          shared PDF layout
└── ws/                WebSocket endpoints (voice intake, dictation)
alembic/versions/      database migrations, numbered 0001_… upward
scripts/               seeders, imports, docs generators (run inside the container)
tests/unit/            fast tests of pure rules — no database
tests/integration/     tests against a running database
```

**Layers, and what each may do**

| Layer | Does | Does not |
|---|---|---|
| `api/v1/routes/<area>.py` | parse the request, check the permission, call a service, commit, write the audit entry | hold business rules or build SQL beyond simple lookups |
| `services/<area>_service.py` | the operation: loads, checks rules, writes, raises `<Area>Error` with a sentence for staff | know about HTTP |
| `<domain>/rules.py` | pure decisions on plain values, fully unit-tested | touch the database |
| `models/` | tables and columns, with the reason for non-obvious columns | contain behaviour |

**Adding a feature to an area** (for example, insurance):

1. Rules → `app/insurance/rules.py`, tests → `tests/unit/test_claim_rules.py`
2. Tables → `app/models/insurance.py`, register in `app/models/registry.py`, migration `alembic/versions/00NN_<name>.py`
3. Operation → `app/services/insurance_service.py`
4. Endpoints → `app/api/v1/routes/insurance.py`, registered in `app/api/v1/router.py`
5. Permission → `app/core/permissions.py`, then regenerate `docs/ROLES.txt`
6. Report (if any) → `app/reports/insurance.py`, imported in `app/reports/__init__.py`

Money is integer paise everywhere. Document numbers come from `DocumentCounter`.
Nothing clinical or financial is deleted: it is cancelled, reversed or superseded with a reason.

## Frontend — `frontend/`

```
app/                   routes, grouped by terminal:
│   (dashboard)/       doctors, admin, manager
│   (reception)/       front desk      (ward)/  nurses      (lab)/  laboratory
│   (patient)/ (intake)/  patient-facing voice intake
components/<area>/     screens and panels for one area; components/ui/ shared primitives
lib/
├── staffApi.ts        every call to the backend, in one typed client
├── api.ts, auth.ts    base URL resolution and the staff token
├── format.ts, utils.ts
├── types/<area>.ts    response and request types, mirroring the backend (core.ts = shared)
├── hooks/             React hooks with their own lifecycle (voice intake, dictation)
└── audio/             microphone capture and PCM playback
```

**Adding a screen:** page in `app/(<terminal>)/<path>/page.tsx` (thin: header + one
component), the component in `components/<area>/`, types in `lib/types/<area>.ts`,
calls in `lib/staffApi.ts`, and the sidebar link in `components/dashboard/sidebar.tsx`
with the roles that hold the permission the screen's API needs.

## Known large files

These work, but are the first candidates if an area is reworked: split by
sub-feature rather than growing further.

- `backend/app/services/pad_service.py`, `reception_service.py`, `ipd_service.py` (1,300–1,500 lines)
- `frontend/lib/staffApi.ts` (1,200+ lines), `components/pad/visit-pad.tsx`, `components/lab/lab-request-view.tsx`
