Satya Hospital AI Platform

A voice-first patient intake and clinical support system built for Satya Hospital, Kanpur.

The system is currently designed for the Orthopedics and Gynecology departments. It collects the patient's history through a voice conversation and prepares a structured record for the doctor before the consultation.

Patients can speak in Hindi, English, or Hinglish. Doctors can then review the history, risk assessment, suggested differentials and investigations, uploaded reports, and other consultation details from the clinical dashboard. Prescriptions can also be created and sent to the patient through WhatsApp.

Clinical safety: Every AI output is advisory. The treating doctor remains the final authority on every clinical decision. Safety-critical checks are enforced in code, not only in the UI.



Highlights

️ Continuous voice consultation with no push-to-talk

🇮🇳 Hindi, English and Hinglish conversations

Structured symptom extraction and clinical summarization

Two-layer emergency detection

‍️ Doctor dashboard with queues, patient history and consultation timelines

AI copilot for red flags, differentials, investigations and follow-up questions

Investigation catalog with report upload and OCR

Arithmetic-based laboratory range comparison

Voice-dictated prescriptions with safety checks

A4 prescription PDFs with QR verification and prescription IDs

WhatsApp prescription delivery with retry tracking

RBAC, audit logging and rate limiting

Prometheus metrics and structured JSON logging

Provider-agnostic AI architecture



Quick Start

Prerequisites

Docker and Docker Compose

A Sarvam API key

A JWT secret

Run with Docker

cp .env.example .env

Set at least:

SARVAM_API_KEY=your_key_here
JWT_SECRET_KEY=your_secret_here

Then start the application:

docker compose up --build

Local development

Backend

cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

Frontend

cd frontend
npm install
npm run dev



Local URLs

Service

URL

Patient intake

http://localhost:3000

Clinical console

http://localhost:3000/login

API documentation

http://localhost:8000/docs

Health check

http://localhost:8000/api/v1/health

Microphone requirement: voice capture requires a secure context. localhost works directly; other hosts require HTTPS.



How It Works

1. Patient voice intake

The patient starts a consultation and speaks naturally with the assistant.

Audio is streamed to Sarvam STT, responses are generated through the AI layer, and completed sentences are sent to TTS as soon as they are ready.

The system supports interruption through two layers:

Browser-side voice detection stops playback immediately.

The server cancels the in-flight generation.

This keeps the conversation responsive without relying on the model to decide when the patient has finished speaking.

2. Clinical processing

The consultation passes through an eight-stage clinical pipeline:

Conversation AI

Symptom extraction

Medical JSON generation

Risk detection

Clinical summary

Differential suggestions

Investigation suggestions

Patient education

Emergency detection operates in two layers:

Deterministic phrase matching across English, Hinglish and Devanagari

LLM reasoning over the structured clinical record

3. Doctor dashboard

Doctors can access:

Waiting, live and completed consultation queues

Patient search

Longitudinal patient history

Consultation summary

Clinical history

Transcript

Timeline

Recorded consultation audio

AI copilot recommendations

Investigation ordering

Prescription creation

AI copilot suggestions are individually labelled and dismissible, with clinician decisions stored separately.

4. Investigations

The platform includes a 101-test catalog across 11 categories, along with:

Favourite tests

Recently used tests

Investigation templates

12 common panels

PDF report uploads

Photo/scan uploads

OCR extraction

Laboratory values are compared against reference ranges arithmetically, not by an AI model.

The reference range printed on the patient's report takes precedence over the built-in table. If units cannot be reconciled, the result is marked "not compared" instead of being guessed.

5. Prescriptions

Doctors can dictate prescriptions naturally, for example:

Tablet Paracetamol 650 mg SOS.
Tablet Pantoprazole 40 mg before breakfast.

The parser extracts:

Form

Drug

Strength

Frequency

Timing

Duration

The doctor can edit the resulting prescription before issuing it.

Rule-based checks detect:

Drug substitutions

Duplicate medicines

Allergies

Drug interactions

Pregnancy-related medication concerns

The final prescription is generated as an A4 PDF with:

Hospital letterhead

Prescription ID

QR verification

Doctor signature

The PDF can then be delivered to the patient through WhatsApp with tracked and retried delivery.



️ Architecture

                         ┌──────────────────┐
       Patient ─────────▶│     Next.js      │◀──────── Doctor
       Voice             │    App Router    │        Dashboard
                         └────────┬─────────┘
                                  │ HTTPS / WSS
                         ┌────────▼─────────┐
                         │      Nginx       │
                         │ TLS / Rate Limit │
                         │ WebSocket Upgrade│
                         └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐
                         │     FastAPI      │
                         │ RBAC / Audit     │
                         │ Rate Limiting    │
                         │ Metrics          │
                         └────────┬─────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
       ┌──────▼──────┐     ┌──────▼──────┐     ┌─────▼──────┐
       │   Services  │     │ AI Gateway  │     │ Clinical   │
       │ Consultation│     │  Pipeline   │     │ Modules    │
       │ Investigation│    │ Session     │     │ Labs / Rx  │
       │ Prescription│     │ Memory      │     │ OCR / PDF  │
       │ Delivery    │     │ Screening   │     │ Safety     │
       └──────┬──────┘     └──────┬──────┘     └─────┬──────┘
              │                   │                   │
              └─────────────┬─────┴───────────────────┘
                            │
              ┌─────────────┼──────────────┐
              │             │              │
       ┌──────▼──────┐ ┌────▼─────┐ ┌─────▼────────┐
       │ PostgreSQL  │ │  Redis   │ │  Sarvam AI   │
       │     16      │ │ Cache /  │ │ STT / TTS /  │
       │ + Media     │ │ Limits   │ │     LLM      │
       └─────────────┘ └──────────┘ └──────────────┘



Tech Stack

Layer

Technology

Frontend

Next.js 14 App Router, TypeScript, Tailwind CSS, shadcn/ui, Framer Motion

Backend

FastAPI, SQLAlchemy 2 Async, asyncpg

Database

PostgreSQL 16

Migrations

Alembic

Cache

Redis with in-process fallback

Voice

Sarvam streaming STT/TTS over WebSockets, AudioWorklet

AI

Provider-agnostic gateway supporting Sarvam, OpenAI, Anthropic, Groq and vLLM

Documents

ReportLab, pypdf, Tesseract

Infrastructure

Docker, Nginx

Monitoring

Prometheus metrics, JSON logging

CI/CD

GitHub Actions



Clinical Safety

The platform is designed around a simple principle:

AI prepares and suggests. The treating doctor decides.

Safety mechanisms include:

AI-generated content is explicitly labelled

Deterministic rule checks are separated from model inference

Abnormal laboratory values are calculated arithmetically

Duplicate and allergy conflicts use rule-based checks

Emergency red flags use deterministic phrase matching

Serious safety warnings must be acknowledged before prescription issuance

The AI cannot mark its own suggestions as reviewed

Clinical sign-off requires a doctor

Front-desk staff have no clinical authority

Patient-record access and clinical actions are audited

Before production use, doctors must review the emergency phrase list, drug interaction table and laboratory reference ranges against local clinical practice.



Repository Structure

backend/
├── app/
│   ├── core/             # Config, security, cache, audit, metrics
│   ├── db/               # Async database engine and sessions
│   ├── models/           # SQLAlchemy models
│   ├── repositories/     # Data access layer
│   ├── services/         # Core business services
│   ├── ai/               # AI gateway and clinical pipeline
│   ├── investigations/   # Catalog, ranges, OCR and report parsing
│   ├── prescriptions/    # Formulary, dictation, safety and PDF
│   ├── messaging/        # WhatsApp, Twilio and console delivery
│   ├── api/              # Versioned API routes and RBAC
│   └── ws/               # Patient and doctor WebSockets
├── alembic/              # Database migrations
├── tests/                # Unit and integration tests
└── scripts/              # Demo data and utility scripts

frontend/
├── app/
│   ├── (patient)/        # Patient intake and live consultation
│   └── (dashboard)/      # Doctor dashboard
├── components/           # UI and clinical components
└── lib/                  # API clients, audio and types

deploy/
├── nginx/                # Reverse proxy and TLS
└── scripts/              # Backup, restore and migration scripts

docs/
├── API.md
├── DEPLOYMENT.md
├── EMR.md
└── PRODUCTION_CHECKLIST.md



Testing

Unit tests

cd backend
pytest -m unit

Integration tests

docker compose up -d db
pytest -m integration

Linting

ruff check app tests

The testing strategy and rationale for external AI calls are documented in:

backend/tests/README.md



Documentation

Document

Description

docs/EMR.md

Reception, billing and patient-data migration

docs/API.md

API endpoints, roles, rate limits and examples

docs/DEPLOYMENT.md

Server setup, TLS, migrations, backups and scaling

docs/PRODUCTION_CHECKLIST.md

Go-live checklist and known limitations

backend/tests/README.md

Testing strategy
Production
For production deployment, review:
docs/DEPLOYMENT.md
docs/PRODUCTION_CHECKLIST.md
The production checklist includes the blocking clinical-safety items that must be reviewed before go-live.

️Disclaimer
This software is intended for patient intake and clinical decision support.
It does not independently diagnose, prescribe, or make clinical decisions. All clinical decisions must be made and verified by a qualified treating doctor.

Project Status
The project currently covers patient voice intake, clinical processing, doctor workflows, investigations, prescriptions, messaging, auditing and deployment support.
Before using the system with real patients, complete the clinical validation and go-live checklist.
