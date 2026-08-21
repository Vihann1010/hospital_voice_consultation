# Deployment guide — Satya Hospital AI Platform

Target: a single Ubuntu 22.04+ host with Docker, serving the hospital over
HTTPS. Everything below assumes you are `cd`'d into the project root.

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Docker Engine 24+ and Compose v2 | `docker --version && docker compose version` |
| 4 GB RAM minimum, 8 GB recommended | OCR and PDF rendering are memory-hungry |
| 50 GB disk | Recordings and reports accumulate; see retention below |
| A domain name pointing at the host | Required for TLS |
| Sarvam AI API key | Speech recognition, speech synthesis and the LLM |
| WhatsApp Business or Twilio credentials | Optional; delivery is disabled by default |

---

## 2. Configure

```bash
cp .env.example .env
```

Generate real secrets — **the API refuses to start in production with the
shipped defaults**:

```bash
# JWT signing key
openssl rand -hex 32

# Database and account passwords
openssl rand -base64 24
```

Fill in at minimum:

```ini
APP_ENV=production
DEBUG=false

JWT_SECRET_KEY=<64 hex characters from above>
POSTGRES_PASSWORD=<strong password>
ADMIN_PASSWORD=<strong password>
DR_AK_AGARWAL_PASSWORD=<strong password>
DR_MANISHA_AGARWAL_PASSWORD=<strong password>

SARVAM_API_KEY=<your key>

CORS_ORIGINS=https://satyahospital.example
PUBLIC_BASE_URL=https://satyahospital.example
PUBLIC_WS_URL=wss://satyahospital.example
NGINX_SERVER_NAME=satyahospital.example
```

Then lock the file down:

```bash
chmod 600 .env
```

`.env` is git-ignored and CI fails if it is ever committed.

---

## 3. TLS certificates

```bash
mkdir -p deploy/certs

sudo apt install certbot
sudo certbot certonly --standalone -d satyahospital.example

sudo cp /etc/letsencrypt/live/satyahospital.example/fullchain.pem deploy/certs/
sudo cp /etc/letsencrypt/live/satyahospital.example/privkey.pem  deploy/certs/
sudo chown $USER deploy/certs/*.pem && chmod 600 deploy/certs/privkey.pem
```

Renewal (certbot renews automatically; this copies and reloads):

```bash
sudo crontab -e
0 3 * * 1 cp /etc/letsencrypt/live/satyahospital.example/*.pem /opt/satya/deploy/certs/ \
          && docker compose -f /opt/satya/docker-compose.prod.yml exec nginx nginx -s reload
```

> Microphone access requires a secure context. Without valid TLS the patient
> voice intake and doctor dictation will not work anywhere except `localhost`.

---

## 4. Migrate and start

Migrations run first — the API deliberately refuses to boot against an
unmigrated database rather than silently creating tables.

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm migrate
docker compose -f docker-compose.prod.yml up -d
```

**Upgrading an existing deployment** that was created by the old `create_all`
path — adopt the baseline instead of re-creating tables:

```bash
docker compose -f docker-compose.prod.yml run --rm backend alembic stamp 0001_initial
docker compose -f docker-compose.prod.yml run --rm migrate    # applies 0002 onward
```

Verify:

```bash
curl -fsS https://satyahospital.example/api/v1/health | jq
docker compose -f docker-compose.prod.yml ps
```

`status` should be `ok`, and `dependencies.cache.distributed` should be `true`
(Redis is wired up).

---

## 5. Demonstration data (optional)

Useful for training staff before real patients are entered:

```bash
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed_demo_data
# and to remove it again
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed_demo_data --purge
```

Demo patients use phone numbers beginning `99000`, so the purge removes exactly
what it created.

---

## 6. Seeded accounts

Created on first boot from `.env`. **Change these passwords immediately.**

| Account | Role | Department |
|---|---|---|
| `admin@satyahospital.in` | admin | — |
| `ak.agarwal@satyahospital.in` | doctor | Orthopedics |
| `manisha.agarwal@satyahospital.in` | doctor | Gynecology |

Front-desk staff accounts are created by an administrator; the `staff` role can
read records and upload reports but holds **no clinical authority** — it cannot
prescribe, order investigations, sign off consultations or use the copilot.

---

## 7. Backups

Postgres alone is not sufficient: recordings, reports and prescription PDFs are
part of the medical record and live on the media volume.

```bash
sudo crontab -e
0 2 * * * cd /opt/satya && ./deploy/scripts/backup.sh >> /var/log/satya-backup.log 2>&1
```

Restore:

```bash
./deploy/scripts/restore.sh /var/backups/satya/20260728-020000
```

Test a restore into a staging host at least once per quarter. A backup that has
never been restored is a hypothesis, not a backup.

---

## 8. Operations

```bash
# Logs (structured JSON, one object per line)
docker compose -f docker-compose.prod.yml logs -f backend

# Only errors
docker compose -f docker-compose.prod.yml logs backend | jq 'select(.level=="ERROR")'

# Metrics (Prometheus format, internal networks only)
curl -s http://localhost:8000/api/v1/metrics

# Rolling restart with no dropped connections
docker compose -f docker-compose.prod.yml up -d --no-deps --build backend
```

Health probes:

| Endpoint | Purpose |
|---|---|
| `/api/v1/health/live` | Process alive. Touches no dependency, so a slow database never causes a restart loop |
| `/api/v1/health/ready` | Can serve traffic. Returns 503 during startup and shutdown |
| `/api/v1/health` | Full operator summary: dependencies, capabilities, usage |

---

## 9. Scaling beyond one node

The design is ready for it, with two things to know:

1. **Set `REDIS_URL`.** Rate limits, caches and coordination move to Redis and
   become cluster-wide. Without it each replica limits independently.
2. **Run the delivery retry worker once.** It currently starts in every API
   process. For multiple replicas, either run one replica with
   `MESSAGING_SWEEP_INTERVAL_S` set and the others with it disabled, or move the
   sweep to a dedicated container. The delivery table already holds all state
   such a worker needs.

Voice sessions are held in memory per node, so WebSocket connections need
sticky routing (`ip_hash` in the Nginx upstream) if you run more than one API
replica.

---

## 10. Data retention

Set a policy before go-live; the platform does not delete anything on its own.

| Data | Suggested |
|---|---|
| Consultation recordings | 90 days, then delete (largest consumer of disk) |
| Reports and prescription PDFs | Retain per medical records policy |
| Audit logs | Retain at least as long as the records they describe |
| Demo data | Purge before go-live |
