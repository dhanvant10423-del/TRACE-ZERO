# Local HTTP API

Start the combined app with `python -B backend/server.py`. GET requests return JSON unless a download is indicated. POST requests require the header `X-Trace-Local: 1`. JSON request bodies are objects. Errors include an `error` string.

| Method | Path | Inputs or result |
|---|---|---|
| GET | /api/overview | Case inventory, rules, findings, baseline comparison. Optional `exclude` comma-separated case source or record IDs, and `hyp_rules` JSON object keyed by hypothesis ID |
| GET | /api/graph | `id` hypothesis result ID and optional case exclusions |
| GET | /api/records | `source`, `quality`, `q`, `offset`, `timeline`, `event_type`, `entity`, `start`, `end`, `relationship` |
| GET | /api/record | `ref` for a case evidence row |
| GET | /api/sentinel/catalog | Fixture settings, permitted actions and benchmark counts |
| POST | /api/sentinel/demo | Empty JSON object. Saves the packaged stable demos once |
| POST | /api/sentinel/run | `scenario` plus optional `settings` from the catalog |
| GET | /api/sentinel/runs | Saved simulation runs |
| GET | /api/sentinel/run | `id` and optional comma-separated `sim_exclude` record IDs |
| POST | /api/sentinel/review | `id`, `outcome` set to `verified` or `held`, and `note` |
| POST | /api/vault/upload | Raw file body. Send URL-encoded filename in `X-File-Name` |
| GET | /api/vault/inventory | Local uploads and validation counts |
| GET | /api/vault/source | `id` upload identifier and metadata |
| GET | /api/vault/rows | `id`, `query`, `status`, `type`, `start`, `end`, `offset` and `timeline` |
| GET | /api/vault/record | `ref` upload record identifier |
| POST | /api/vault/review | `ref` and `note` |
| GET | /api/vault/integrity | `id` verifies the original hash |
| GET | /api/vault/original | `id` downloads verified original bytes |
| GET | /api/exports/pdf, /api/exports/json, /api/exports/csv | Download with optional `exclude`, `hyp_rules`, `run` and `sim_exclude` |

Dates in filters are ISO calendar dates. The case timeline compares normalized record dates and retains source clock notes. Uploads with timezone-naive timestamps remain visible as ambiguous in the vault.
