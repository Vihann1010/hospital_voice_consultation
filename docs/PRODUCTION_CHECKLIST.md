# Production readiness checklist

Work through this before the first real patient. Items marked **blocking** must
be done; the rest are strongly recommended.

---

## Security

- [ ] **blocking** `JWT_SECRET_KEY` replaced with 64 random hex characters
      (`openssl rand -hex 32`). The API refuses to start in production otherwise.
- [ ] **blocking** All seeded account passwords changed from `ChangeMe@123`
- [ ] **blocking** `POSTGRES_PASSWORD` changed from the default
- [ ] **blocking** `.env` has mode `600` and is owned by the deploy user
- [ ] **blocking** `CORS_ORIGINS` set to the exact hospital domain, never `*`
- [ ] **blocking** `DEBUG=false` and `APP_ENV=production`
- [ ] TLS certificate installed and HTTPS verified end to end
- [ ] HTTP redirects to HTTPS (`curl -I http://your-domain` returns 301)
- [ ] Postgres is not published to the host — only `expose`, never `ports`
- [ ] `/api/v1/metrics` reachable only from internal networks
- [ ] Server SSH hardened: key-only authentication, no root login
- [ ] Host firewall permits only 80, 443 and SSH

## Verify the security posture

```bash
# API docs should be hidden in production
curl -s -o /dev/null -w '%{http_code}' https://your-domain/docs        # expect 404

# Security headers present
curl -sI https://your-domain/api/v1/health/live | grep -iE 'strict-transport|x-frame|x-content'

# Rate limiting active on login
for i in $(seq 1 15); do
  curl -s -o /dev/null -w '%{http_code} ' -X POST https://your-domain/api/v1/auth/login \
    -H 'Content-Type: application/json' -d '{"email":"a@b.c","password":"x"}'
done                                                                   # expect 429 near the end

# Anonymous access refused
curl -s -o /dev/null -w '%{http_code}' https://your-domain/api/v1/patients   # expect 401/403
```

---

## Data

- [ ] **blocking** `alembic upgrade head` applied; `/api/v1/health` returns `ok`
- [ ] **blocking** Automated backups scheduled (`deploy/scripts/backup.sh`)
- [ ] **blocking** A restore tested on a staging host — an untested backup is a hypothesis
- [ ] Media volume (`satya_media`) included in backups, not just Postgres
- [ ] Disk monitoring with alerting; recordings grow roughly 2 MB per minute
- [ ] Data retention policy agreed and documented
- [ ] Demo data purged (`python -m scripts.seed_demo_data --purge`)

---

## AI configuration

- [ ] **blocking** `SARVAM_API_KEY` set and verified with a real test consultation
- [ ] `LLM_PROVIDER` and models chosen; `LLM_FAST_MODEL` set to a cheaper tier
- [ ] `LLM_INPUT_COST_PER_MTOK` / `LLM_OUTPUT_COST_PER_MTOK` set so spend is tracked
- [ ] A test consultation reviewed end to end by a clinician for tone and accuracy
- [ ] Both doctors briefed that **every AI output is advisory** and they remain
      the final authority

## Clinical safety sign-off

- [ ] **blocking** A doctor has reviewed the emergency red-flag phrases in
      `app/ai/emergency.py` for local language and idiom
- [ ] **blocking** A doctor has reviewed the drug interaction table in
      `app/prescriptions/formulary.py`
- [ ] **blocking** A doctor has reviewed the reference ranges in
      `app/investigations/reference_ranges.py` against the labs actually used
- [ ] Formulary reviewed for the hospital's actual stock
- [ ] Prescription PDF printed and approved by both consultants
- [ ] Signature images uploaded for each doctor

---

## Messaging

- [ ] `MESSAGING_PROVIDER` set (`console` sends nothing — the safe default)
- [ ] WhatsApp Business number verified and templates approved, or Twilio configured
- [ ] A test prescription delivered to a staff member's own phone
- [ ] `PUBLIC_BASE_URL` publicly reachable if using Twilio (it fetches media over HTTP)

---

## Operations

- [ ] Health checks wired into monitoring (`/api/v1/health/ready`)
- [ ] Log aggregation configured; logs are JSON, one object per line
- [ ] Rate-limit behavior reviewed if running more than one API replica; each
      replica has its own in-process cache
- [ ] Someone is on call and knows how to read `docker compose logs`
- [ ] Runbook shared with the IT desk: restart, restore, check delivery failures

---

## Staff readiness

- [ ] Front-desk staff trained on the patient intake tablet
- [ ] Doctors trained on the dashboard, copilot and dictation
- [ ] Everyone understands the AI never decides — it prepares and suggests
- [ ] A fallback agreed for when the system is unavailable (paper intake)

---

## Known limitations to communicate

Be honest with the hospital about these before go-live:

1. **Voice intake needs a quiet room and a decent microphone.** Recognition
   quality falls sharply in a noisy corridor.
2. **OCR of handwritten reports is unreliable.** Typed and printed lab reports
   extract well; handwriting often will not, and the file is stored with a clear
   "no readable text" message rather than a wrong guess.
3. **Drug interaction checking is not exhaustive.** The rule table covers common,
   clinically important pairs. It is not a substitute for a licensed interaction
   database at high prescribing volume.
4. **The copilot can be wrong.** It is labelled as advisory everywhere it appears
   and every suggestion is dismissible, but staff must be trained to treat it as
   a prompt to think, not an answer.
5. **Single-node voice sessions.** WebSocket state lives in memory, so multiple
   API replicas need sticky routing.
