# Neon database handover

The application backend now uses Neon PostgreSQL through a server-only `DATABASE_URL` loaded from `backend/.env`. The provided `backend/env.txt` was used to configure that file. Neither file is included in version control; no real connection URL is stored in source code or documentation.

## Fresh setup

The user confirmed an empty database. Only schema and default operational lists were initialized. Local SQLite records were not migrated or deleted. Open the application at http://127.0.0.1:3000/ and create the single Master account. The server setup key is in `backend/data/opd.setup-key`; do not send it to other users.

The frontend still runs on this computer. A cloud database alone does not publish the frontend or make localhost available on a phone outside the network.

## Start the backend

From the backend directory with its virtual environment active:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The connection uses the Neon pooled endpoint with SSL and channel binding. A bounded psycopg connection pool reuses connections. Prepared statements are disabled for transaction-pool compatibility. Schema/search-path settings and the application write lock are transaction-scoped. Multi-query reads use repeatable-read snapshots; write transactions use read-committed isolation under the application lock. Startup DDL is batched to reduce network round trips. Settings are cached only for a single database transaction and invalidated when updated.

## Operational behavior

- Internet connectivity from the backend to Neon is required. Connection failure does not trigger a switch to a different database.
- Existing application validation, password rules, authentication, version checks, audit history, exact currency calculations and duplicate-request protection remain in place.
- PostgreSQL identity columns provide generated IDs. Case-insensitive unique indexes preserve master-record uniqueness, and searches use case-insensitive matching.
- PostgreSQL write transactions preserve the single-writer guarantees used for doctor tokens, availability and bill/payment updates.
- Use Neon backups/restore or PostgreSQL pg_dump for cloud backups. The legacy SQLite backup command refuses to run against Neon.
- `recover-master` operates on the configured database and still requires local server access.

## Verification

`/api/health` reports `database: postgresql`; the same response is available through Next.js at `/api/health`. `setup_required: true` is expected until the new Master account is created.

Offline regression tests always use disposable SQLite files. Set `OPD_TEST_POSTGRES=1` to exercise the same workflows against unique disposable `opd_test_*` schemas in Neon; the fixture removes only its own generated schema, keeping the public hospital database empty. No local patient data is used in integration tests.

Completed validation: 36 Neon workflow tests passed (SQLite backup-format test excluded), plus an isolated Neon repeatable-read concurrency test. The offline regression run passed 37 tests, with the additional snapshot test also passing offline. All 28 frontend interaction tests and the Next.js production build passed. Live health checks through both FastAPI and Next.js confirm PostgreSQL and fresh first-run setup.
