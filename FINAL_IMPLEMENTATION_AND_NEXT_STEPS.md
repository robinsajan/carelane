# Hospital OPD - Final Implementation and Next Steps

- Date: 23 October 2026
- Stack: Next.js + React + TypeScript; Python FastAPI; Neon PostgreSQL (SQLite retained for offline/tests)
- Deployment: Local hospital server and browser clients on the hospital LAN
- Product scope: Administrative/reception OPD operations only
- Delivery status: Working implementation with automated API tests and browser workflow checks. Hospital deployment and staff acceptance remain to be completed.

This document records what has been built and what still needs to be done. It does not silently settle unconfirmed hospital policies or claim production acceptance.

## 1. Confirmed decisions implemented

| Decision | Result |
| --- | --- |
| Single location | One hospital configuration and shared operational workspace |
| Next.js + FastAPI + Neon PostgreSQL | Current database configuration; SQLite retained for offline tests |
| Light blue and white UI | Responsive sidebar/dashboard, cards, forms, queues and lists |
| Administration only | No doctor login or clinical workspace |
| One Master | Database uniqueness rule; setup cannot create another Master |
| Admin logins | Individual Admin accounts with server-enforced permissions |
| Age/address required | Validated in UI and API; approximate reported age supported |
| Eight-character alphanumeric UHID | Generated, collision-checked, permanent and unique |
| Tokens per doctor | Separate atomic daily counters and historical allocation ledger |
| Follow-up pop-ups | Server-persisted reminder schedules, on-screen pop-ups, per-user acknowledgement and snooze |
| No messages | No SMS, WhatsApp, email, telephony or external reminder integration |
| No data export | In-app reports only; no export/download route or controls |
| Everything local | Server database, accounts, history and reminder state stay local |
| Billing | Master controls separate new/follow-up doctor fees; completed visits support bills, extra charges and full/partial payment records |
| Uploads excluded | No file, document or patient-photo upload/camera controls |

## 2. Delivered functional modules

### Access and account security

- First-run setup requires the random setup key stored only on the server.
- Master is created once; production has no default credentials or sample accounts.
- Passwords use salted scrypt hashes. Session tokens are random; only their hashes are stored in SQLite.
- HTTP-only, SameSite Strict cookies; eight-hour sessions; logout and account revocation.
- Server-side Admin/Master authorization and request-header CSRF barrier with no cross-origin API access configured.
- Login failure throttling and temporary-password replacement for new/reset Admin accounts.
- Master can add/deactivate Admin accounts and reset their temporary passwords.
- Master cannot deactivate the sole Master or create a second one.
- Local interactive Master recovery updates the same account and invalidates sessions.

### Dashboard and application shell

- Hospital identity, staff identity, global patient search and internal reminder indicator.
- Today's visits, waiting patients, completed attendance and follow-ups due.
- Live queue preview, quick actions, follow-up watch and seven-day OPD activity.
- Operational lists refresh every five seconds; connectivity errors are visible.
- Desktop sidebar, tablet layout and mobile navigation; scrollable tables contain their own overflow.

### Patient registration and profiles

- Name autocomplete searches the local database from the first character in the single Name field. Matching patients appear in a persistent panel below the names, including partial/reordered names and omitted middle names. Selecting a suggestion fills existing details and exposes Create visit with the same UHID; any edited details update that record rather than registering another patient.
- Single required Name field (no separate middle name/surname); existing full names are preserved. Essential registration fields have optional expandable contact/address/emergency details.
- Mandatory age/address; optional known DOB with server-calculated age; approximate age retains its recorded date.
- No-mobile registration and shared family phone support.
- Eight-character permanent UHID; searchable directory with inactive filter and pagination.
- Registration suggestions and possible-duplicate warnings match by name only. Shared phone numbers never trigger a possible-record match; staff may acknowledge intentionally distinct patients with the same name.
- Save patient and Save & Create Visit actions.
- Overview, Reported History and Visits tabs.
- Master-only merge preview with demographic conflicts and linked-record counts; explicit confirmation preserves visits, history, follow-ups, aliases and the source snapshot in audit history.

### Patient-reported history

- Conditions, allergies, medications, surgeries, hospitalizations, family history and lifestyle.
- Information reported, None reported, Unknown and Not asked states.
- Patient/caregiver source, source details, recorder and timestamps.
- Append-only revisions; category revision conflicts are rejected.
- Important reported condition/allergy indicators.
- Each visit stores references to the history revisions that existed at arrival, preserving the earlier reported state.

### OPD visits and queue

- Fresh visit records, current multiple complaints/durations and reception remarks.
- Active department/doctor validation and configurable visit types.
- No automatic copying of earlier complaints.
- Per-doctor per-local-day token counters with transactional allocation and a uniqueness-constrained ledger.
- Manage attendance offers only Waiting, Completed and Cancelled. Direct status dropdowns on the dashboard live queue and Today's OPD update visits without a pop-up; required cancellation/correction reasons are collected inline. Older status values remain preserved in historical records.
- Date, doctor, department, status and patient search filters.
- Versioned updates, correction/cancellation reasons, reassignment history and visit activity timelines.
- Doctor transfer is disabled while the token-transfer policy is Unspecified. Master may explicitly select Next token or Preserve if available.
- Inactive doctors/departments cannot receive new visits; historical identities remain accessible.

### Follow-ups

- Schedule from patient, visit or follow-up list. Queue Actions provides a small edit icon and Follow-up button; the editable pop-up defaults to seven days after the visit (today + seven for standalone scheduling) and pre-fills patient/doctor/department. Visit shortcuts use the configured reminder time, otherwise editable 09:00. After saving, the visit action becomes a green calendar checkmark labelled Follow-up set and opens the existing record; this persists on refresh. Cancelling the linked follow-up restores the add action.
- Return date, optional time, explicit reminder time, doctor, department, notes and optional assignee.
- Due Today, Upcoming, Overdue and All views with staff/doctor/department/status filters.
- Persistent on-screen reminders; no external message delivery or browser notification permission.
- Per-staff acknowledgement and 30-minute snooze; reminders can be reopened from the bell.
- Record manual contact attempts and outcome/notes without marking attendance.
- Rescheduling, cancellation and No Show changes with reasons and revision history.
- New schedule revisions invalidate old reminder acknowledgements/snoozes.
- Arrival creates a fresh linked Follow-up visit and marks the schedule Attended in the same transaction.
- Duplicate attendance links are prevented; retry-safe submissions avoid duplicate creation.
- Closing the browser does not lose reminders; overdue state is calculated using hospital local time, with date-only returns due through the end of that date.

### Reports and Master setup

- OPD visit register, patient registrations, visits by doctor/department, statuses, visit types, follow-up register, contact attempts and first-attendance waiting duration.
- Date, relevant doctor/department, status and staff filters; distinct patient and visit counts; paginated in-app results.
- No CSV/Excel/PDF export or dedicated print action.
- Hospital identity/timezone, doctor transfer policy and optional reminder default.
- Doctors, departments, visit types, common complaints, referral sources, cancellation/rescheduling reasons and contact outcomes.
- Active/inactive master records preserve existing history.
- Master-only audit viewer with staff/time, action, entity and permitted prior-value details.

### Local maintenance

- Repeatable install/build and local startup scripts.
- Loopback API with Next.js same-origin proxy; optional frontend LAN binding.
- SQLite WAL mode, foreign keys, busy timeout, short write transactions and version conflict checks.
- Server-only backup, integrity/foreign-key verification, safe restore to a new database file and Master recovery commands.
- Isolated fictional preview database; no seed data in the hospital database.
- Locked dependency inventories for reproducing the verified installation.

## 3. Verification completed

| Check | Result |
| --- | --- |
| Backend workflow tests | 20 tests passed using disposable SQLite databases |
| Frontend interaction tests | 11 tests passed: patient Name suggestions/autofill, existing-record reuse/edits, keyboard/partial-name entry, direct status changes, inline cancellation reasons stale-update handling, correct row-action identity, and editable seven-day defaults |
| Next.js production build | Passed, including TypeScript checks and dynamic API proxy route |
| Concurrent token allocation | Ten simultaneous visit submissions produced distinct sequential tokens |
| Daily token boundary | New hospital-local day resets the doctor's sequence |
| Authentication/permissions | One Master, protected setup, forced Admin password change, denied Master-only actions, deactivation/session revocation |
| Patient integrity | Required fields, DOB/age calculation, duplicate warnings, repeat submission safety, search, pagination and edit conflicts |
| Clinical-history boundary | Reported-history revisions preserved and old visit snapshots unchanged |
| Follow-up integrity | Snooze/revision behavior, contacts without attendance, cancellation, date-only overdue behavior, linked attendance and duplicate protection |
| Duplicate resolution | Merge preserves visits/follow-ups and search through previous UHID |
| Backup/restore-copy | Consistent backup verified; restored copy retains patient/visit counts; overwrite of live path rejected |
| Browser workflow | Preview sign-in -> register fictional patient -> Save & Create Visit -> doctor/token -> profile -> schedule follow-up -> pop-up -> record contact attempt |
| Responsive checks | Desktop at 1440px and mobile at 390px; no document-level horizontal overflow in the mobile dashboard |
| Excluded endpoints | No export or upload endpoints exposed; authenticated billing endpoints are available |
| Production launcher | Windows startup script served the production Next.js build and a separate loopback API; runtime proxy, sign-in cookies and security headers passed |
| First-run hospital database | Browser shows the Master setup screen; zero users and zero patients remain in the actual hospital database |

The test adapter emits one dependency deprecation warning; it does not fail the tests. A complete independent security assessment, hospital-volume load test, every-device accessibility audit and staff acceptance have not been performed. The browser preview uses fictional data only.

Saved evidence: `docs/screenshots/dashboard.png` (fictional preview records) and `docs/screenshots/first-run-setup.png` (empty hospital setup). Verification servers were stopped after the checks; use the launcher to start the application.

## 4. Open decisions kept neutral

| Question | Current behavior | Still to be decided |
| --- | --- | --- |
| Doctor transfer token | Unspecified; transfers are blocked until configured | Hospital chooses destination queue token policy |
| Expected workload | No invented doctor, patient or concurrency quantities | Provide doctors, visits/day, total patient records and simultaneous staff |
| Default reminder time | Blank; Admin must choose time per follow-up | Master may set a hospital default if wanted |
| Follow-up ownership | Optional assignee; normal Admin operational visibility is shared; acknowledgement is per staff | Confirm whether assignment should route pop-ups more narrowly or impose ownership rules |
| Existing patient migration | No general import/upload UI | Confirm whether any old system data needs a separate controlled migration |
| Local infrastructure | SQLite and application files stay on local server | Select server, LAN address/name, power protection and operator |
| Backup policy | Commands supplied; no automatic backup schedule invented | Select restricted backup destination, schedule, retention and restore owner |
| Language | English interface implemented | Confirm whether translations are required as a separate change |
| Data retention/correction | Historical records retained; operational deactivation supported | Agree hospital retention and correction procedures |

Single-location operation, Next.js/FastAPI/SQLite, mandatory age/address, one Master, UHID length and no exports are confirmed, not open questions.

## 5. What is to be done before hospital rollout

### A. Hospital configuration

1. Start the empty hospital database and complete first-run setup locally with the actual Master account holder.
2. Set the hospital name/address/contact details and confirm timezone before any visits exist.
3. Add the actual departments, doctors and active operational list values.
4. Create named Admin accounts; have each staff member replace their temporary password.
5. Set a doctor transfer policy only after the hospital decides. Leave it unset otherwise.
6. Choose a reminder default only if wanted; otherwise keep explicit per-follow-up times.
7. Keep the fictional preview separate from real records.

### B. Local infrastructure and recovery

1. Select the hospital server and use its local disk for SQLite. Do not place the live database on a network share.
2. Set OS permissions so only the server service account/authorized local operator can read the database, setup key, backup and recovery tools.
3. Configure a trusted local HTTPS reverse proxy/certificate and Secure cookies for LAN production use.
4. Restrict network access to the intended hospital devices. FastAPI should remain loopback-only.
5. Set up automatic startup/restart and agreed monitoring using the selected machine's service/task management. The delivered script is an interactive launcher, not an installed Windows service.
6. Agree and configure scheduled backups to a restricted local/offline destination. No recurring backup schedule is installed by default.
7. Run a hospital-specific restore rehearsal, check counts and sign in to the restored instance without overwriting the live database.
8. Document who owns Master recovery, backup verification and machine maintenance. Use disk encryption/physical access controls according to the hospital's infrastructure policy; SQLite itself is not encrypted by this app.

### C. Staff acceptance and capacity

1. Walk through new patient, family-shared mobile, no-mobile, infant age/DOB, returning patient and duplicate-resolution cases.
2. Run a real working-day simulation with more than one Admin and more than one doctor queue.
3. Verify cancellation, no-show, hold/resume, closed-visit correction and configured doctor transfer behavior.
4. Verify follow-up reminder timing, multiple signed-in users, snooze/acknowledgement, rescheduling, restart and return attendance.
5. Reconcile dashboard/report counts on hospital sample scenarios.
6. Test keyboard navigation, label readability and table scrolling on the actual reception devices.
7. Supply workload targets and load-test against those numbers before adopting the proposed response-time targets as verified.
8. Record acceptance results and resolve release-blocking issues before replacing the existing workflow.

## 6. Implementation limits to carry into planning

- Reminders are evaluated on server requests and polled by the signed-in app; there is no closed-browser alert or background OS notifier.
- The five-second refresh interval is a design setting, not a measured LAN service-level guarantee.
- Some aggregate reports and patient-history screens read their relevant records into server memory; test representative historical volume and optimize SQL/history pagination if the agreed capacity requires it.
- A doctor currently has one assigned department. If the hospital needs simultaneous multi-department doctor membership, agree that rule and extend the relation/UI deliberately.
- English is the only implemented interface language.
- HTTPS, automatic service startup, automatic backup scheduling, OS/disk permissions and infrastructure monitoring are deployment tasks, not silently installed services.
- Client browser disconnection does not support independent offline writes. The app works without internet only while the local server and LAN remain reachable.
- Real patient data, hospital credentials and full operational acceptance have not been supplied or created during development.

## 7. Scope boundaries for future changes

The following remain excluded: refunds, financial reports, uploads/photos, doctor login, clinical consultation/prescription features, external messages and data exports. They should not appear merely because Master has broad setup permissions. Doctor pricing is now available exclusively to Master.

## 8. How to continue

Use `README.md` for installation, first-run setup, local/LAN launch commands, tests, backup/restore and recovery. Use `OPD_Management_System_Requirements.md` for the product baseline. Keep this handover updated as the hospital resolves open decisions and completes acceptance.

- Today’s OPD filters: Waiting (default), Being Attended, Completed, and Cancelled. Remove All visits. The same four statuses are available in inline and visit-detail attendance controls.
# Interface redesign

The application now uses the light blue and white Framed sheet design documented in `DESIGN_REVAMP.md`, covering the shell, dashboard, patient records, OPD queues, follow-ups, forms, reports, and settings. The redesign retains existing workflows and data. Production build and 11 frontend interaction tests pass; the captured dashboard passes responsive inspection at 1440, 768, and 390px with 0 failures and 2 documented warnings.


### Follow-ups inside OPD

Remove the standalone Follow-ups navigation page. Today's OPD has a Follow-ups button opening a right-side panel. It defaults to the current hospital date, supports any selected date and a Today shortcut, and lists all follow-up statuses for that exact due date with pagination. Each row opens the existing follow-up record. Scheduling, attendance, and internal reminders remain available. The dashboard View all follow-ups shortcut leads to this OPD panel.

### Scope update: remove reported patient history

Reported history is no longer part of the application UI: remove its patient-profile tab, add/update form, patient-reported alerts, visit snapshot display, and merge-preview history counts. Keep patient demographics, visit records, complaints, and follow-ups. Existing stored history is retained for compatibility; no historical database records are deleted.

### Daily doctor queue overview

OPD opens with separate doctor queue panels for a selected day (today by default). Each panel shows doctor and department, total visits, Waiting / Being Attended / Completed / Cancelled counts, up to two patients being attended, and the next three waiting patients in arrival order. Counts use the full daily dataset rather than a page of visits. Empty active doctor queues stay visible; inactive doctors appear when they have visits for that date. Legacy attendance states are counted explicitly as other statuses.

Click a count or Open queue to see only that doctor's patients, with patient search, attendance updates, edit and follow-up controls. Date, department and doctor filters are available, with a return to all doctor queues. Existing tokens remain per doctor per day. The overview refreshes every five seconds and keeps current results visible during background refresh.

Validation: 22 backend workflow tests, 13 frontend interaction tests, and production build passed. Tests include independent doctor counts above 30 visits, separate token sequences, empty queues, exact date and department scoping, and opening the selected doctor/status.

### Attendance actions on doctor cards

Each waiting patient preview has Attend and Cancel controls. Each patient being attended has Complete and Cancel controls. Cancellation collects a required short reason inline. Cancelled visits appear in an expandable section of the doctor card, with Back to waiting; this restores the same visit and original token, with an audit reason. The card previews up to three cancelled visits and links to the complete cancelled list when there are more. Actions use version checks, show saving/errors, refresh counts and previews after saving, and prevent repeating a successful action while the refreshed queue is loading.

### Simplified doctor cards

Doctor cards display only the doctor name, Being attended, and Next in line, with existing attendance/cancellation controls kept beside patient names and tokens. Remove department subtitles, visit totals, status-count strip, UHID sublines, cancelled-preview section, and footer details. Click the doctor name to open the full queue, where Completed and Cancelled tabs (including returning cancelled visits to Waiting) remain available. Preview overflow links remain within the two patient sections.

### Doctor queue reference layout

Use the supplied reference image: one white rounded board, a Doctor queues heading with date and live doctor/visit totals, a compact summary of waiting patients, patients in consultation and available doctors, and aligned Doctor / Patient queue / Action columns. Each doctor has a single row with initials, clickable name and availability derived from active status and current attendance. Patient tokens, names and Next in line / In consultation labels align with Attend or Complete and a cancel icon. Empty rows say Queue is clear. On narrow screens the doctor identity stacks above its queue without hiding controls. All actions use the existing API and audit/version checks. No preview-only labels or fixed sample statistics are rendered in the live app.

### Separate current and next patient columns

The doctor queue board has Doctor, Current status, and Next in line columns. Current status shows the patient being attended with Complete and Cancel controls. Next in line shows the next waiting patient with Attend and Cancel controls. Overflow links open the full doctor queue for each status; empty columns show explicit empty-state text. Both columns stack with labels on phones. Remove the combined Patient queue / Action columns.

### OPD Complete view toggle

OPD defaults to the doctor queue overview. A Complete view switch shows the paginated visit table for the selected date, department and doctor (all doctors when none is selected). The table retains patient search, Waiting / Being Attended / Completed / Cancelled filters, attendance updates, edit and follow-up actions. Switching off returns to the doctor overview; selecting a doctor from the overview opens Complete view for that doctor. Build and all 17 frontend interaction tests pass.

## Billing scope update — 24 October 2026

Billing is now included following the user’s updated request. See [BILLING_IMPLEMENTATION.md](BILLING_IMPLEMENTATION.md) for the final implemented workflow, data model, permissions and current boundaries. Earlier no-billing scope statements are superseded by this update.

## Neon scope update

The user requested Neon PostgreSQL and confirmed starting empty. This supersedes earlier local-only database requirements. The application server remains local, while database records are stored in Neon and require internet. Existing SQLite data remains untouched. See README Neon configuration for startup, secret handling, setup and testing.

Department colours: Master settings are ordered Hospital, Departments, Doctors, Billing charges, then staff/lists/audit. Departments offer eight light pastel colours. Doctors inherit their department colour, displayed with department names in settings and OPD queues/complete view. Existing departments default to pastel blue. Changing a department colour updates all its doctors without individual edits.
