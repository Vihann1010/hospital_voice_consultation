# API reference

Base URL: `https://<host>/api/v1`
Interactive docs: `/docs` (disabled in production unless `DEBUG=true`)

## Authentication

All clinical endpoints require a bearer token.

```bash
curl -X POST https://host/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ak.agarwal@satyahospital.in","password":"..."}'
# → {"access_token":"eyJ...","token_type":"bearer"}

curl https://host/api/v1/consultations \
  -H 'Authorization: Bearer eyJ...'
```

Patients never log in. Intake issues a short-lived, single-consultation token
scoped to one WebSocket session.

### Roles

| Permission | admin | doctor | staff |
|---|:--:|:--:|:--:|
| Read patients, consultations, reports, prescriptions | ✅ | ✅ | ✅ |
| Upload reports | ✅ | ✅ | ✅ |
| Order investigations | ✅ | ✅ | ❌ |
| Create and send prescriptions | ✅ | ✅ | ❌ |
| Review / sign off consultations | ✅ | ✅ | ❌ |
| Use the AI copilot | ✅ | ✅ | ❌ |
| Read audit logs, administer the system | ✅ | ❌ | ❌ |

The live matrix is available to admins at `/api/v1/health/permissions`, and any
account can read its own at `/api/v1/auth/me/permissions`.

---

## Conventions

**Errors** carry a `request_id` that matches the `X-Request-ID` response header
and the server logs:

```json
{ "detail": "Prescription not found", "request_id": "9f3c2a71b40de85c" }
```

**Rate limits** are returned as headers, with `Retry-After` on a 429:

```
X-RateLimit-Limit: 240
X-RateLimit-Remaining: 236
```

| Scope | Limit |
|---|---|
| `POST /auth/login` | 10 / minute |
| `POST /consultations/start` | 20 / minute |
| Report uploads | 30 / minute |
| Public signed documents | 60 / minute |
| Everything else | 240 / minute |

---

## Endpoints

### Health

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health/live` | — | Liveness; touches no dependency |
| GET | `/health/ready` | — | Readiness; 503 until startup completes |
| GET | `/health` | — | Operator summary: dependencies, capabilities, usage |
| GET | `/metrics` | internal | Prometheus scrape target |

### Authentication

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/login` | — | Staff sign-in; both outcomes audited |
| GET | `/auth/me` | staff | Current account |
| GET | `/auth/me/permissions` | staff | What this account may do |

### Consultations

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/consultations/start` | — | Patient intake; returns a session token |
| GET | `/consultations` | staff | Filter by `status`, `department`, `reviewed`, `q` |
| GET | `/consultations/stats` | staff | Queue counts |
| GET | `/consultations/{id}` | staff | Full record; **audited** |
| POST | `/consultations/{id}/review` | doctor | Sign-off; **audited** |
| GET | `/consultations/{id}/recording` | staff | Mixed audio (range requests supported) |
| GET | `/consultations/{id}/copilot` | doctor | AI decision support |
| POST | `/consultations/{id}/copilot/decisions` | doctor | Record accept / dismiss |

### Patients

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/patients?q=` | staff | Search by name or phone |
| GET | `/patients/{id}` | staff | Standing history plus visit timeline |

### Investigations

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/investigations/catalog` | staff | 101 tests, 11 categories, 12 panels |
| GET | `/investigations/workspace` | staff | Favourites, recent, templates, OCR capability |
| POST | `/investigations/favorites` | staff | Star / unstar |
| POST | `/investigations/templates` | doctor | Save a template |
| POST | `/investigations/orders` | doctor | Generate a request slip |
| POST | `/investigations/reports` | staff | Upload (multipart); validated by magic bytes |
| GET | `/investigations/reports/{id}` | staff | Report with analysis |
| GET | `/investigations/reports/{id}/versions` | staff | Full version chain |

### Prescriptions

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/prescriptions/formulary?q=` | staff | Medicine autocomplete |
| POST | `/prescriptions/dictation` | doctor | Speech → structured, editable rows |
| POST | `/prescriptions/safety-check` | doctor | Duplicate, allergy, interaction, pregnancy |
| POST | `/prescriptions` | doctor | Issue and render the PDF; **audited** |
| GET | `/prescriptions/{id}/pdf` | staff | A4 sheet |
| POST | `/prescriptions/{id}/send/whatsapp` | doctor | Deliver to the patient; **audited** |
| GET | `/prescriptions/{id}/deliveries` | staff | Delivery tracking |
| POST | `/prescriptions/deliveries/{id}/retry` | doctor | Manual retry |

### Public (signed, no bearer token)

| Method | Path | Purpose |
|---|---|---|
| GET | `/public/prescriptions/{id}/pdf?token=` | Expiring signed link, for messaging providers |
| GET | `/public/prescriptions/verify/{number}` | QR target; authenticity only, no clinical detail |

### WebSockets

| Path | Auth | Purpose |
|---|---|---|
| `/ws/consultations/{id}?token=` | consultation token | Patient voice intake |
| `/ws/dictation?token=` | staff access token | Doctor dictation |

Both stream 16 kHz PCM16 audio as binary frames and receive JSON events.

---

## Worked example: prescription from dictation

```bash
TOKEN=$(curl -sX POST $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"ak.agarwal@satyahospital.in","password":"..."}' | jq -r .access_token)

# 1. Structure the dictation (nothing is prescribed yet)
curl -sX POST $API/prescriptions/dictation -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"transcript":"Tablet Paracetamol 650 mg SOS. Tablet Pantoprazole 40 mg before breakfast.","patient_id":"..."}'

# 2. Check safety against this patient's allergies and current medicines
curl -sX POST $API/prescriptions/safety-check -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"patient_id":"...","medicines":[{"name":"Paracetamol","formulary_code":"PARA"}]}'

# 3. Issue. Serious alerts must appear in acknowledged_alerts or this returns 400.
curl -sX POST $API/prescriptions -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{...}'

# 4. Send to the patient's registered WhatsApp number
curl -sX POST $API/prescriptions/$RX_ID/send/whatsapp -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{}'
```
