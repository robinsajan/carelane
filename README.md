# Carelane - Local Hospital OPD

A hospital administration application built with **Next.js, Python FastAPI and Neon PostgreSQL**. SQLite remains available for offline development and disposable regression tests. The interface uses light blue and white. Doctors are assignable records, not users.

The application covers patients, OPD visits, per-doctor queues, follow-ups with on-screen reminders, operational reports, Master setup, individual Admin accounts and audit history. Billing supports doctor consultation fees, additional charges, full/partial payment records and printing. There is no upload, external messaging or data-export feature.

## Start on this Windows machine

Dependencies and a production frontend build have been prepared in this workspace. From PowerShell in this directory:

```powershell
.\scripts\start.ps1
```

Open **http://localhost:3000**. Keep the terminal running; Ctrl+C stops the application and its API child process.

If dependencies are missing or the source has changed, install/build first:

```powershell
.\scripts\install.ps1 -Python python
```

Use Python 3.12+ and Node.js 20.9+ (a maintained current Node release is preferable). If Python is not on PATH, pass its executable path to `-Python`. Installation needs internet to obtain packages; normal operation does not. If PowerShell execution policy blocks scripts, use the separate terminal commands below rather than changing your system-wide policy.

## First-run setup

1. Start the application. The API creates `backend/data/opd.sqlite3` and a first-run setup key.
2. Read `backend/data/opd.setup-key` locally on the server. Do not share it.
3. On the setup screen, enter the key, hospital name and the details/password for the one Master account. Use a password of 12 or more characters.
4. Setup becomes unavailable once Master exists. No default production username or password is supplied.
5. As Master, add departments, doctors and individual Admin accounts in Settings.
6. Admin accounts receive a temporary password and must replace it at first sign-in.
7. Leave undecided settings unset until the hospital chooses them. Doctor transfers are blocked until a token-transfer policy is selected. Reminder time is chosen explicitly per follow-up unless Master sets a default.

Patient age and address are mandatory. Phone numbers may be shared; use No mobile when appropriate. UHIDs are permanent unique eight-character uppercase alphanumeric values. Tokens restart each day separately for each doctor.

## Separate terminal commands

Backend, from the project root:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Frontend, from `frontend/`, in a second terminal:

```powershell
npm.cmd run build
npm.cmd run start
```

For frontend development, use `npm.cmd run dev` instead of `run start`. The frontend proxies `/api/*` to the loopback API. `API_URL` can change that internal target at runtime. No patient data is stored in browser localStorage.

## Local network use

```powershell
.\scripts\start.ps1 -Lan
```

Other hospital devices can open the server's LAN address on port 3000. FastAPI stays bound to loopback; do not expose API port 8000 separately. LAN addressing, local HTTPS certificate trust, Windows firewall policy, server account permissions and service startup need to be configured on the hospital's selected machine before real patient use. Once local HTTPS is installed, set `OPD_SECURE_COOKIE=1` for secure session cookies.

The configured database is Neon PostgreSQL. The backend requires internet access to Neon; browser clients still connect to the Next.js server. Offline SQLite mode is available only when no DATABASE_URL is configured. An unavailable Neon connection never silently falls back to SQLite.

## Follow-up reminders

- Admin selects a follow-up date, optional follow-up time, and explicit reminder date/time in hospital local time.
- Due reminders appear in a grouped in-app pop-up. Acknowledge and Snooze 30m affect only that staff member's reminder state.
- Closing a pop-up does not acknowledge it. The bell reopens the list.
- Dates, reminder revisions, acknowledgement and snooze state persist on the server.
- With the app closed, no message or OS push is sent. Pending reminders appear at the next authenticated session.
- A contact attempt never marks attendance. Use Patient arrived -> Create visit to link a fresh return visit.
- Date-only scheduled follow-ups become overdue after the end of their hospital-local date; staff explicitly mark No Show when appropriate.

## Fictional preview

Preview data is isolated in `backend/data/preview.sqlite3`; it is never inserted in the real hospital database. To create it on a new installation:

```powershell
.\backend\.venv\Scripts\python.exe -m backend.seed_demo
.\scripts\start.ps1 -Demo
```

The preview generator refuses to modify an existing preview database. Its randomly generated preview credentials are in `backend/data/preview-access.txt`, outside tracked source. The preview hospital name explicitly identifies it as a demo. Do not enter real patient information in the preview.

## Tests and build

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/test_workflows.py -q
cd frontend
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

Tests create disposable databases and never use the hospital database. The dependency versions used for verification are recorded in `backend/requirements.lock.txt` and `frontend/package-lock.json`.

## Local backups and recovery

Backups are server maintenance, not an in-app export option. Use unique filenames and an access-restricted destination:

```powershell
.\backend\.venv\Scripts\python.exe -m backend.manage backup "D:\HospitalBackups\opd-2026-10-23.sqlite3"
.\backend\.venv\Scripts\python.exe -m backend.manage verify-backup "D:\HospitalBackups\opd-2026-10-23.sqlite3"
.\backend\.venv\Scripts\python.exe -m backend.manage restore-copy "D:\HospitalBackups\opd-2026-10-23.sqlite3" "C:\HospitalData\restored-opd.sqlite3"
```

For legacy/offline SQLite mode, the backup uses SQLite's backup API to include committed WAL data. Restore creates a separate new file and refuses to overwrite an existing/live database. After checking the restored copy, stop the app and remove the Neon DATABASE_URL configuration and set `OPD_DATABASE` to that copy's absolute path before restarting in offline mode. The restore test should verify patient/visit counts and a real sign-in in a separate controlled instance; successful file integrity alone is not the entire operational recovery procedure.

For local Master recovery, stop the application and run:

```powershell
.\backend\.venv\Scripts\python.exe -m backend.manage recover-master
```

The command prompts locally for a new password, updates the existing sole Master, revokes all sessions and records recovery in the audit log. It does not create a second Master. Access to this command and the database must be restricted by server filesystem permissions.

## Project layout

```text
backend/main.py                 API, validation and authentication
backend/postgres.py             PostgreSQL adapter, pooled connections and transactions
backend/manage.py               Backup, verification, restore-copy and Master recovery
backend/seed_demo.py             Isolated fictional preview generator
backend/test_workflows.py        Behavioral API/database tests
backend/data/                   Runtime data and secrets (ignored by source control)
frontend/app/                   Next.js application and same-origin API proxy
frontend/app/globals.css        Light blue/white responsive design
scripts/install.ps1              Dependency setup and production build
scripts/start.ps1                Local process startup/shutdown
OPD_Management_System_Requirements.md  Product requirements
FINAL_IMPLEMENTATION_AND_NEXT_STEPS.md  Delivery status and remaining work
```

See the final handover for the implementation matrix, verification results, unresolved choices and hospital rollout checklist.

## Billing

Master sets separate new-visit and follow-up fees in Settings → Doctors. After completing a visit, open OPD → Complete view → Completed and use Bill. Review the consultation fee, add charge descriptions, quantities and unit prices, then generate the bill. Record full or partial payments with a method and optional reference. Billing lists totals, payments and balances with date and status filters. Open a bill to record later payments or print it.

Fees and payments use INR and integer paise. Zero consultation fees are supported; an unset fee blocks generation. Issued bills retain their original details and charges. Only one bill per visit is allowed. Payment recording does not process a bank or gateway transaction. See [Billing implementation](BILLING_IMPLEMENTATION.md). Restart backend and frontend after updating; database changes are additive on backend startup.

Master can maintain reusable charge names and prices under Settings & setup > Billing charges. Admins select active saved charges in a bill draft and adjust quantities.

Follow-up notifications run daily at 9:00 AM in the hospital timezone for due and overdue scheduled follow-ups. Keep the app open and signed in; opening it after 9 AM shows the day’s outstanding reminders. Acknowledge hides a reminder for the day; unresolved follow-ups return the next day. Reminder-only checks run once a minute while visible; hidden tabs pause and check on return. The global five-second UI refresh is removed; saved actions and reopening sections update their data.

OPD is the landing screen after sign-in. Its header offers Register patient and Create OPD visit. Registering from OPD keeps staff on OPD, with the existing Save & create visit flow available; saving a visit returns to the OPD queues.

Dashboard combines analytical summary counts, the seven-day OPD activity chart and the full report library on one page. Reports has no separate navigation item. Registration, visit creation, queue actions and follow-up operations remain in OPD; OPD stays the default screen.

Doctor queues has a three-dot Doctor availability popup for Admin and Master. Disable for today hides a doctor’s current queue and visit-selection option until the next 8:00 AM in hospital time (the same morning if disabled before 8 AM). Enable restores them sooner. Existing visits remain in Complete view, and Master’s permanent Active setting remains separate. Changes are versioned and audited. Expiry is checked by the backend and a one-off frontend timer restores the visible queue at expiry.

The compact light UI uses shared density tokens: 32px desktop controls, tighter table and queue rows, smaller form/card padding, and 44px phone touch targets. It follows the installed official shadcn skill’s design guidance while retaining the existing component implementation and light blue/white theme.

New passwords require 12–128 characters, one uppercase A–Z letter, one digit and one symbol (spaces do not count as symbols). Live checklists appear in account setup, staff creation/reset and password changes; the same policy applies server-side and to local Master recovery. Existing sign-ins are unaffected.

## Neon database configuration (current)

The backend loads `DATABASE_URL` from environment variables, the project `.env`, or `backend/.env`. The configured URL is server-only; never place it in a `NEXT_PUBLIC_` variable. Credentials and the supplied `backend/env.txt` are ignored by version control. `backend/.env.example` contains placeholders only.

Install backend dependencies, then start from the backend folder with the virtual environment active:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The provided Neon URL uses TLS and channel binding. Connections use a bounded Python pool with prepared statements disabled for the Neon pooled endpoint. Startup creates missing tables and default operational lists. Write transactions take a transaction-scoped PostgreSQL advisory lock to preserve queue-token, idempotency and optimistic-version guarantees. Case-insensitive master names/codes use lower-case unique indexes, and searches remain case-insensitive.

This switch starts with an empty Neon database as requested. Existing local SQLite records are not uploaded, copied or removed. Create the single Master account through first-run setup; the setup key remains in `backend/data/opd.setup-key` on the backend computer. Use Neon backup/restore facilities or `pg_dump` for PostgreSQL; `python -m manage backup` is guarded against using the SQLite backup format on Neon.

Normal backend tests use disposable SQLite databases even if the developer has Neon configured. For Neon integration testing, set `OPD_TEST_POSTGRES=1`: the fixture creates a unique `opd_test_*` schema, runs fictional test workflows, then removes only that schema. It never writes test patients into the public application schema. Network-enabled tests require the configured database role to create schemas.
