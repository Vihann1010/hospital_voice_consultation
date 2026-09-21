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
ADMIN_EMAIL=<the administrator's email>
ADMIN_PASSWORD=<strong password>

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

### Which modules this site runs

`ENABLED_MODULES` decides which optional parts of the platform exist here. The
default is `all`, so an existing hospital that sets nothing keeps everything it
has. A site that lists modules gets only those: the rest are **not registered on
the API at all** and answer 404, and the screens that would reach them are gone
from the sidebar and the Settings page.

| Module | What it covers |
|---|---|
| `ipd` | Admissions, wards, beds, nursing charts, discharge |
| `laboratory` | In-house lab: sample collection, result entry, verification |
| `diet` | Diet orders and the kitchen sheet — needs `ipd` |
| `room_charges` | The nightly bed-charge run — needs `ipd` |
| `theatre` | Operations and procedures, rooms, consent, notes |
| `insurance` | Insurers, TPAs, employers and their claims |
| `radiology` | The radiology worklist, for studies reported in-house |

Registration, billing, consultations, prescriptions, ordering investigations,
patient uploads and the Visit Pad are not switchable. A clinic without them is
not this product.

```ini
# A hospital: everything (the default)
ENABLED_MODULES=all

# A day clinic with procedures but no beds, no bench and no panel work
ENABLED_MODULES=theatre
```

`ENABLED_DEPARTMENTS` is the list the registration screens offer. Empty (the
default) means every department the build knows. A single-speciality clinic
names its own, and the screens follow: the counter's dropdown holds one entry,
the patient kiosk stops asking a question with one answer, and the line under
the logo says what this site actually does.

`DEFAULT_DEPARTMENT` belongs with this: it is where a clinician's prescriptions
and investigation orders are filed when their account names no department. It
defaults to `orthopedics`, which is what the code did before it was a setting;
a single-speciality clinic should name its own.

### Prescribing content awaiting sign-off

`APPROVED_FORMULARY` names the departments whose drafted medicines and regimen
templates a consultant of that speciality has reviewed. The two departments the
platform was built with — `orthopedics,gynecology` — were reviewed before
release and are the default.

Content added for a new speciality is marked provisional in the source and is
**withheld from the prescribing screens** until its department is named here:
it cannot be found by search, cannot be reached through a regimen template, and
cannot be fetched by typing its code. A comment saying "needs review" is not a
control, and a regimen nobody has approved should not be one click from a
patient. The API says which departments are waiting at `GET /api/v1/config` and
again in the startup log, every boot.

Two things the gate deliberately does not touch. A prescription already issued
stays readable — hiding the drug afterwards would make an old prescription
unreadable and helps nobody. And the interaction and duplicate checks resolve
drafted entries too: a safety warning that is missing while content awaits
review would be missing exactly when it is most needed.

```ini
# After the gastroenterologist has been through the formulary
APPROVED_FORMULARY=orthopedics,gynecology,gastroenterology
```

`THEATRE_VOCABULARY` is `theatre` (the default) or `procedures`. It changes
only the words on screen — "Theatre" becomes "Procedures", the operation list
becomes the procedure list — for a clinic whose list is fifteen-minute scopes
rather than operations. The module, the records and the rules are identical.

Two behaviours worth knowing. A module whose parent is off is dropped and the
startup log says so, so `diet` without `ipd` is not a half-working kitchen
sheet. And a name that is not a module stops the boot rather than quietly
disabling a ward — a typo in this line must not be discovered by a nurse.

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

**A brand-new, empty database** cannot be built by running the chain from the
start. Migration `0001_initial` creates its tables with `create_all` over the
*current* models, so it already makes every table the later migrations add, and
`0007` then fails on a `consultants` table that exists. Until the chain is
repaired, build the schema from `0001` and record it as current:

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade 0001_initial
docker compose -f docker-compose.prod.yml run --rm backend alembic stamp head
docker compose -f docker-compose.prod.yml up -d
```

This is correct, not a shortcut: `0001` produces the schema the models describe
today, enum values included. It was checked against a fresh database — the
`gastroenterology` department, the `endoscopy` investigation category and
`surgeries.visit_id` from migrations 0031–0033 are all present afterwards.

**An existing database** that is already migrated takes new migrations the
normal way:

```bash
docker compose -f docker-compose.prod.yml run --rm migrate
```

**A new site's own data.** For the gastroenterology clinic:

```bash
docker compose -f docker-compose.prod.yml run --rm backend python -m scripts.seed_gastro_clinic
```

It creates the price list, the endoscopy suite and recovery bay, and the
procedure list — all at placeholder rates. It creates no staff logins and no
consultants; those are the clinic's to enter, and the script says so when it
finishes.

Before the first patient, a new site also sets its identity in `.env`:
`HOSPITAL_NAME` and `HOSPITAL_CITY` (printed on every prescription and bill,
and said aloud by the intake assistant), `DOCUMENT_PREFIX` (three letters at
the front of every UHID and invoice number — permanent once patients are
registered), `PRESCRIPTION_NUMBER_PREFIX` (the front of every prescription
number), and `ADMIN_EMAIL`. Replace `backend/app/assets` logo files with the
site's own, or set `HOSPITAL_LOGO=none` to print `HOSPITAL_NAME` as a wordmark
until it has some. `PLATFORM_BRAND=medicos` shows the MedicOS mark beside the
site's own on the sign-in screen and in the console, and names the browser tab
"<site> · MedicOS"; `none` (the default) shows the site alone.

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

`status` should be `ok`, and `dependencies.cache.backend` should be
`in-memory`.

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

## 6. The first account

One account is created on first boot, from `ADMIN_EMAIL` and `ADMIN_PASSWORD`
in `.env`. **Change that password immediately**, at Settings → Staff accounts.

Everyone else — doctors, reception, nurses — is created by the administrator
from that same screen, which records who created each account. Named
consultants used to be seeded here too, which meant every site that installed
this build got logins for two doctors who did not work there, each with a
shipped default password.

Front-desk staff hold **no clinical authority**: reception can read records and
upload reports but cannot prescribe, order investigations, sign off
consultations or use the copilot. The full matrix is in `docs/ROLES.txt`.

A consultant is not a login. Doctors who see patients are also entered in
Settings → Consultants, which is where their OPD hours, fees and registration
number live, and where the intake assistant reads the name it says to patients.
A visiting endoscopist who never touches the software needs a consultant entry
and no account at all.

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

The cache is in-process, so rate limits and cached responses are maintained
independently by each API replica. Run the delivery retry worker once when
scaling out: either enable `MESSAGING_SWEEP_INTERVAL_S` on one replica and
disable it on the others, or move the sweep to a dedicated container. The
delivery table already holds all state such a worker needs.

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
