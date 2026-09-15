# Logging and debugging

## What is logged

The backend writes one line per event to standard output.

| Event | Level | Carries |
|---|---|---|
| `request` — every HTTP request (except health checks and metrics) | INFO for 2xx/3xx, WARNING for 4xx, ERROR for 5xx | method, path, status, duration_ms, client_ip, user_id, user_role |
| `http_error` — the API refused a request | WARNING (ERROR for 5xx) | status, path, the reason shown to the user |
| `validation_error` — a form sent invalid values | WARNING | path, each field and why it was refused |
| `unhandled_exception` / `request_failed` — a bug | ERROR | path, full traceback |
| `slow_request` — took more than 2 seconds | WARNING | path, duration_ms |
| service events (`invoice_created`, `payment_recorded`, `books_posting_run`, …) | INFO | the ids and amounts involved |

Every line written while a request is being handled carries its **`request_id`**,
and `user_id` / `user_role` once the caller is signed in — including lines
written deep inside a service.

Never logged: request bodies, query strings, or clinical text. Validation errors
name the field, not the value.

## Tracing a problem a user reports

1. **Get the request id.** Every error response includes `request_id`. The browser
   console shows each failed call as
   `[api] POST /ipd/admissions/…/vitals -> 422 (request 1a2b3c4d5e6f7a8b): …`,
   and server errors show `(reference …)` in the on-screen message.
2. **Find every line for that request:**
   ```bash
   docker logs satya-backend 2>&1 | grep 1a2b3c4d5e6f7a8b
   ```
3. **No request id?** Look at a user's recent activity, or all refusals:
   ```bash
   docker logs satya-backend --since 30m 2>&1 | grep '"user_id": "<uuid>"'
   docker logs satya-backend --since 30m 2>&1 | grep -E '"level": "(WARNING|ERROR)"'
   ```
   With `jq` installed:
   ```bash
   docker logs satya-backend --since 1h 2>&1 | grep '^{' | jq -c 'select(.status >= 400)'
   ```

## Settings (`.env`)

| Setting | Default | Use |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` for more detail while investigating |
| `LOG_FORMAT` | `json` | `pretty` prints readable lines for local debugging |
| `LOG_REQUESTS` | `true` | turn off the per-request line if volume is a problem |

Changing `.env` needs the backend recreated:
`docker compose up -d --force-recreate --no-deps backend`.

## Writing log lines in new code

```python
from app.core.logging import get_logger

logger = get_logger(__name__)
logger.info("claim_booked", extra={"claim_number": claim.claim_number, "amount_paise": amount})
```

- The message is a short `snake_case` event name; details go in `extra`.
- Log identifiers (ids, numbers) and outcomes, not names, notes or clinical content.
- Do not add `request_id` or `user_id` yourself — they are attached automatically.
- Expected refusals are raised as `HTTPException` and logged by the error handler;
  use `logger.exception(...)` only inside an `except` for something unexpected.
