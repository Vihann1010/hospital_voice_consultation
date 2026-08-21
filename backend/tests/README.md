# Testing strategy

Three layers, chosen so the fastest tests cover the most dangerous code.

## Unit (`tests/unit`) — no I/O, milliseconds

Pure functions where a mistake is silent and clinically dangerous. These get
the heaviest coverage because they are where bugs hide:

| Area | Why it is tested hard |
|---|---|
| `emergency.py` | A missed red flag delays emergency care |
| `parsing.py` | A wrong abnormal flag misleads the doctor |
| `medication_rules.py` | A missed allergy conflict can cause harm |
| `dictation.py` | A misheard drug becomes a printed prescription |
| `uploads.py` | The boundary where hostile files arrive |
| `permissions.py` | The rule that front desk holds no clinical authority |
| `recording.py` | Resampler arithmetic that silently corrupts audio |
| `reference_ranges.py` | Sex/age range selection drives every lab flag |

Run: `pytest -m unit`

## Integration (`tests/integration`) — real PostgreSQL

Schema, transactions, repository queries and API contracts, exercised through
the real app with a real database. Each test runs inside a transaction that is
rolled back, so tests never see each other's data.

Run: `docker compose up -d db && pytest -m integration`

## End-to-end (manual, documented in DEPLOYMENT.md)

The paths that need real credentials and a browser: patient voice intake with
Sarvam, WhatsApp delivery, OCR of a genuine scanned report. These are release
checks rather than CI checks.

## What is deliberately not mocked

External AI calls are not mocked into unit tests. A test asserting that a
mocked model returns what we told it to prove nothing. Instead the *contract*
around the model is tested — JSON parsing, schema validation, self-repair,
and the rule that deterministic checks override model output.
