# Hospital OPD Management System

## 1. Document purpose

This document defines the requirements and implementation scope for an admin-operated hospital outpatient department (OPD) management system.

- Version: 1.2
- Date: 23 October 2026
- Status: Confirmed product baseline; implementation delivered with rollout/open decisions recorded in FINAL_IMPLEMENTATION_AND_NEXT_STEPS.md
- Source: The supplied OPD PRD and the subsequent scope decisions made in discussion.
- Precedence: The agreed scope below replaces conflicting requirements in the original PRD. The reference registration image is field/workflow inspiration, not a requirement to reproduce its design.

Requirements described as proposed defaults or open decisions are recommendations, not confirmed user decisions. The selected stack is Next.js, Python FastAPI and SQLite. Unconfirmed reminder defaults and transfer policies remain unset until configured.

## 2. Product objective

Give hospital administration and reception staff one place to register patients, maintain patient-reported history, create OPD visits, assign doctors, manage queues, schedule follow-ups, and review operational reports.

The system must be fast for everyday reception work, preserve earlier records, and use a modern light blue and white interface.

## 3. Confirmed scope

### Included

- Single hospital location, with individual Admin accounts and exactly one Master account.
- Entire application and database hosted locally within the hospital.
- Patient registration with a permanent unique hospital identifier (UHID).
- Patient search and potential duplicate detection.
- Patient profile and patient-reported medical history.
- Separate records for each OPD visit.
- Department and doctor assignment.
- Daily queue/token management.
- Follow-up scheduling and on-screen pop-up reminders inside the application.
- Follow-up contact-attempt tracking and return-visit linking.
- Operational dashboard and reports.
- Doctor, department, and other operational master data.
- Staff administration, permissions, hospital settings, and audit logs.

### Excluded

- Refunds and financial reports. Billing and payment records are included by the 24 October 2026 scope update.
- Document, report, prescription, image, and patient-photo uploads; camera capture.
- Doctor logins or a doctor-facing workspace.
- Clinical consultation notes, diagnosis entry, prescriptions, treatment plans, or automated medical advice.
- Pharmacy, inpatient management, laboratory operations, and inventory.
- SMS, WhatsApp, email, or other external patient reminder delivery.
- A patient-facing portal or mobile application.
- Data export/download features for both roles, including CSV, Excel, and PDF export. No dedicated report-print feature in this release.

Adding any excluded feature requires an explicit scope change.

## 4. Roles and access

Admin means an operational administration/reception staff member. Master means a privileged system administrator; it is a role, not a shared staff identity.

| Capability | Admin | Master |
| --- | --- | --- |
| View dashboard and operational reminders | Yes | Yes |
| Search, register, and update patients | Yes | Yes |
| View and update patient-reported history | Yes | Yes |
| Create and manage visits and queues | Yes | Yes |
| Schedule and manage follow-ups/contact attempts | Yes | Yes |
| View operational reports | Yes | Yes |
| Export/download data | No | No |
| Manage doctors and departments | No | Yes |
| Manage configurable operational lists | No | Yes |
| Create/deactivate Admin accounts and reset access | No | Yes |
| Configure hospital settings and permissions | No | Yes |
| Review system-wide audit logs | No | Yes |
| Resolve duplicate patients through a controlled merge | No | Yes |

### Authentication requirements

- One login screen for both roles; route users to their permitted workspace after login.
- Every staff member uses an individual account. No public signup.
- Master creates Admin accounts and can deactivate them without removing their historical actions.
- Secure password handling, sign-out, session expiry, and login rate limiting.
- Deactivated accounts cannot start or continue authenticated work.
- Authorization must be enforced on the server for every protected action, not only by hiding UI controls.
- Do not ship hardcoded credentials. Establish the first Master through a controlled setup process.
- Exactly one Master account exists; prevent its deletion or deactivation. No UI/API may create a second Master.
- Master exclusively controls adding doctors, departments, Admin accounts, and all system setup.
- Only Master controls new-visit and follow-up consultation fees per doctor.
- Master account creation/recovery procedures must be finalized before production.

## 5. Information structure

Keep the following concepts separate:

| Record | Purpose |
| --- | --- |
| Patient | Permanent identity and current demographic/contact information |
| Reported history | Patient/caregiver-reported background with revision history |
| OPD visit | A particular attendance with complaints, doctor, department, token, and status |
| Follow-up | A planned return associated with a patient and, normally, an earlier visit |
| Contact attempt | A dated staff record of an attempt to contact a patient about a follow-up |

A returning patient keeps the same UHID and gets a new visit record. A planned follow-up is not itself an attended visit.

## 6. Navigation and screen inventory

### Shared navigation

1. Dashboard
2. Patients
3. Today's OPD
4. Follow-ups
5. Reports
6. Settings (role-dependent)

Display the hospital name, current staff identity/role, global patient search, internal reminder indicator, and sign-out action in the application shell.

### Required screens and panels

- Login.
- Dashboard.
- Patient directory and patient registration/edit panel.
- Patient profile with Overview, Reported History, and Visits tabs.
- New visit/edit visit panel.
- Today's OPD queue.
- Follow-up list and follow-up create/edit/detail panel.
- Reports.
- Doctor and department settings.
- Staff account management (Master).
- Hospital and operational settings (Master).
- Audit log viewer (Master).

## 7. Patient registration and search

### Registration fields

| Field | Requirement/behavior |
| --- | --- |
| UHID | System-generated, exactly 8 uppercase alphanumeric characters (A-Z, 0-9), unique and permanent; not manually editable |
| Name | Required single full-name field; no separate middle-name or surname inputs |
| Gender | Required; configurable inclusive options and unknown/prefer not to say |
| Age | Mandatory; accept age in years/months/days or calculate it from a valid DOB; approximate reported age is allowed and labelled |
| Date of birth | Optional alternative input for calculating mandatory age; never invent an exact DOB |
| Age precision | Distinguish known DOB from approximate age; support years, months, and days |
| Primary mobile | Required unless No mobile is selected |
| No mobile | Explicit option; allow registration without a fabricated number |
| Additional mobile | Optional |
| Email | Optional |
| Address | Mandatory; at least a nonblank address line/locality |
| Area/landmark | Optional additional details |
| City, state, pincode | Optional by default; configurable mandatory policy if needed |
| Emergency contact name, relationship, phone | Optional |
| Blood group | Optional; Unknown supported |
| Referral source/person | Optional |
| Registration date/time | Automatic; controlled correction if authorized |
| Administrative remarks | Optional |
| Active/inactive status | Default Active; retain all history when inactive |

Do not carry over generic Extra-1/Extra-2 fields without a defined purpose. Do not default unknown DOB to the current date. If approximate age is used to estimate birth information, retain the approximation flag and the date on which age was recorded.

### Registration experience

- While entering Name, show matching existing patients from the database from the first character, in a persistent panel below the Name field. Match partial words across first, middle and surname fields. Suggestions identify the patient by name, UHID, age, contact and address.
- Selecting a suggestion fills the registration form from that existing patient record and offers Create visit using the same UHID. Unchanged details do not create or update a patient; edited details are saved to the existing record before continuing.
- Support mouse and keyboard selection and an explicit action to clear the selection for another/new patient.
- Show essential fields first and group optional information into expandable sections.
- Provide Save and Save & Create Visit actions.
- Saving a patient alone does not create a queue entry.
- Show clear inline validation and preserve entered values after recoverable errors.
- Before creating a record, warn about likely duplicates using the patient name only. Phone number and age must not determine possible-record matches.
- Shared family phone numbers are allowed and must not be treated as a unique patient identifier.
- Staff can review suggested matches and open an existing patient instead of registering again.
- Allow a distinct patient to be created after acknowledging a duplicate warning; record that acknowledgement.

### Search and profile

- Search by UHID, name, and phone; support doctor/date filters in visit-related searches.
- Search results show enough identifying information to distinguish similar names.
- Profile header shows UHID, name, age/DOB precision, gender, phone, and significant reported allergy/condition indicators.
- Overview shows demographic details, latest visit summary, and next follow-up.
- Visits tab shows chronological visits and associated follow-ups.
- Master can resolve duplicates using a reviewed merge with a chosen surviving UHID, conflict preview, linked history preservation, and an audit record. Old identifiers remain traceable. Do not silently discard records.

## 8. Patient-reported history

### Information captured

- Existing illnesses/conditions.
- Reported allergies and reactions where known.
- Ongoing medications as reported.
- Past surgeries and hospitalizations.
- Optional family and lifestyle history.
- Source: patient or caregiver; optional source details.
- Staff member and time recorded/updated.

### Recording rules

- Clearly label this section Patient-reported history. It is not a clinical assessment.
- For each category distinguish Information reported, None reported, Unknown, and Not asked.
- Record updates separately with prior values available; do not overwrite earlier history without a trace.
- Capture the report state at the time of a visit, through a snapshot or revision reference, so later updates do not change what was recorded previously.
- Show reported allergy/important condition alerts prominently without representing them as clinically verified.
- Keep history optional during quick registration so reception can complete it afterward.

## 9. OPD visits

### Visit data

- Unique visit identifier and patient UHID link.
- Arrival/visit date and time.
- Department and assigned doctor.
- Visit type: New, Follow-up, or another configured type.
- One or more patient-reported complaints, with optional duration per complaint.
- Administrative/reception remarks.
- Queue/token number and current status.
- Created/updated by and timestamps.
- Originating follow-up link where applicable.

### Visit rules

- Create a separate visit for every attendance, including follow-up attendance.
- Never automatically copy old complaints into a new visit.
- Doctor selection must respect the selected department and active status.
- Inactive doctors/departments remain visible on past records but cannot be assigned to new visits.
- Detect possible duplicate active visits for the same patient and doctor on the same day; warn before proceeding.
- Preserve reassignment and status-change history.
- Record a reason for cancellation and for corrections to completed visits.
- Marking a visit Completed is an administrative action; it does not create clinical notes.

## 10. Queue and token management

### Statuses

The Manage attendance selector offers only **Waiting**, **Completed**, and **Cancelled**. Older status values, if present, remain traceable in historical records.

| Status | Meaning |
| --- | --- |
| Waiting | Registered and waiting |
| Completed | Attendance has finished |
| Cancelled | Visit cancelled with a reason |

### Queue behavior

- Change visit status directly in the dashboard live queue and Today's OPD table without opening visit details. Cancellation/correction reasons are entered inline when required; updates retain staff/time and version checks.

- Filter by date, doctor, department, and status.
- Show token, patient name/UHID, arrival time, waiting duration, doctor, and status.
- Allow admins to call, hold, resume, complete, cancel, or mark no-show using context-appropriate actions.
- Allow reassignment to another doctor with an audit record and an explicit token policy.
- Completed/Cancelled/No Show records leave the active waiting view but remain searchable.
- Support correction/reopening through a controlled action with a reason.
- Updates should become visible to other logged-in staff without requiring a full page reload.
- Generate tokens atomically so simultaneous registrations cannot produce duplicates.

**Confirmed:** token sequence resets each hospital-local day separately for each doctor. Do not reuse cancelled tokens. Store token scope/date with the token; a token alone is not a permanent visit identifier.

## 11. Follow-ups and internal reminders

### Purpose

Allow the admin team to record a planned return, see when follow-ups need attention, track contact attempts, and link actual attendance to a new OPD visit. Staff enter the follow-up schedule; the application must not generate clinical advice.

### Follow-up fields

The queue Actions column has a compact edit icon and a Follow-up button. New follow-ups default to seven calendar days after the originating visit (or today when no visit is supplied). The pop-up pre-fills patient/doctor/department and allows quick edits before saving. For visit shortcuts, the pop-up reminder uses the configured hospital time, or editable 09:00 when none is configured.

| Field | Requirement/behavior |
| --- | --- |
| Patient | Required |
| Originating visit | Linked when scheduled from a visit; optional for a standalone administrative entry |
| Follow-up date | Required |
| Follow-up time | Optional |
| Doctor and department | Default from originating visit; editable to valid active selections |
| Reason/admin note | Optional; operational context |
| Reminder date/time | Required; must not be after the scheduled follow-up |
| Assigned Admin | Optional; unassigned items remain visible to the team |
| Status | Scheduled, Attended, Cancelled, or No Show |
| Contact outcome | Derived from separately recorded contact attempts |
| Created/updated by | Automatic with timestamps |
| Attendance visit | Linked when the patient returns |

### Workflow

1. Admin selects Schedule Follow-up from a visit/profile or the Follow-ups page.
2. Admin chooses the return date, optional time, and reminder date/time.
3. System validates the entry and displays it in the patient's profile and follow-up list.
4. When reminder time arrives, show an actionable on-screen pop-up in the signed-in application; do not send any message.
5. Admin may record a contact attempt, reschedule, cancel, or create a return visit.
6. When the patient arrives, Admin creates a new visit and explicitly links it to the scheduled follow-up; the follow-up becomes Attended.

### Follow-up list and reminders

- Views: Due Today, Upcoming, Overdue, and All, with separate filters for reminders that need action.
- Overdue means a still-Scheduled follow-up whose scheduled date/time has passed. For date-only entries, evaluate overdue after that local date ends.
- Reminder due time and follow-up due time are separate concepts; an advance reminder may be actionable before the follow-up date.
- Show patient/UHID, contact details, doctor, follow-up date, reminder time, assignee, status, and latest contact outcome.
- Contact outcomes: No answer, Contacted, Confirmed, Requested reschedule, and Other with notes.
- Recording contact does not automatically mark a follow-up Attended or remove it from the scheduled list.
- Rescheduling retains the old date, reason, actor, and time in history and replaces pending reminders for the old schedule.
- Dismissing/acknowledging a reminder does not cancel the follow-up. Track acknowledgement per user separately from team-level follow-up status.
- Cancelled and Attended follow-ups do not continue generating pending reminders.
- Do not automatically convert an overdue follow-up to No Show; an Admin makes that decision.
- Warn about overlapping/duplicate scheduled follow-ups for the same patient and doctor; allow intentional separate records.
- An app reopened after reminder time must show outstanding reminders reliably. No background browser permission or external messaging is required.
- Reminder delivery must be idempotent so retries do not create duplicate items.
- Pop-ups show patient name/UHID, doctor, follow-up date/time, and actions to open the record, acknowledge, or snooze. Group simultaneous reminders to avoid stacked blocking dialogs.
- Pop-ups only appear while the application is open and signed in. Due reminders persisted on the local server appear when staff next open/sign in. No operating-system push notification or external delivery is required.

**Delivery confirmed:** on-screen application pop-ups only, with no messages. Reminder time is explicitly selected by Admin. No default time is preselected; Master may configure one later. Assignees are optional; no restrictive ownership rule is assumed.

## 12. Dashboard

### Summary cards

- Patients registered today.
- OPD visits today.
- Currently waiting.
- Being attended.
- Completed visits today.
- Follow-ups due today.
- Overdue follow-ups.

### Working areas

- Current queue preview with doctor/department filters.
- Follow-up reminders needing attention.
- Quick actions: Register Patient, Find Patient, Create Visit, and Schedule Follow-up.
- Relevant empty states with a clear next action.

The operational dashboard remains focused on OPD; bills and payment balances are available in Billing. Count definitions must be consistent between dashboard and reports. Cancelled and No Show visits should remain distinguishable from completed attendance.

## 13. Operational reports

- Patient registration register.
- OPD visit register.
- Doctor-wise and department-wise visit counts.
- Visit status report.
- New versus follow-up visit report.
- Follow-ups due, overdue, attended, cancelled, and no-show.
- Follow-up contact-attempt report.
- Queue waiting duration report, based on actual recorded transitions.

### Report behavior

- Filter by date range, doctor, department, status, and relevant staff/assignee.
- Distinguish patient counts from visit counts; one patient can have multiple visits.
- Reports are viewable and filterable inside the application only; neither role has data export/download actions or export endpoints.
- Use the hospital timezone consistently for dates and daily boundaries.
- Preserve applied filters while navigating reports.
- Keep sensitive reported history out of general operational report tables.
- Database backups are restricted local maintenance operations, not a user-facing data export feature.

## 14. Master data and settings

### Doctor master

- Name, identifier/code, department association, optional qualification/designation and contact, and active/inactive state.
- No login is created for a doctor.
- Historical visits retain the doctor identity after deactivation or edits.

### Department master

- Name, code, optional description, and active/inactive state.

### Operational lists

- Visit types.
- Common complaints, with free-text entry allowed.
- Referral sources.
- Cancellation and rescheduling reasons.
- Contact outcomes, with sensible initial defaults.

### Hospital settings

- Hospital name and text contact/address details.
- Timezone; proposed default Asia/Kolkata.
- Fixed eight-character alphanumeric UHID generation; existing identifiers never change.
- Fixed per-doctor daily token scope/reset; optional transfer-token policy remains Unspecified until configured.
- Follow-up reminder defaults.
- Required registration fields; age and address must remain mandatory.
- No setting to enable report exports in this release.

Changes to settings must not renumber existing patients, alter past tokens, or erase historical meanings. No upload control is included in settings.

## 15. UI and interaction requirements

### Visual direction

- Light blue and white theme; no dark theme required for the initial release.
- Proposed palette: page background #F5F9FF, surfaces #FFFFFF, primary blue #2563EB, pale blue #EFF6FF, main text #0F172A, secondary text #64748B, and borders #E2E8F0.
- Verify contrast in implementation; do not assume a colour combination is accessible solely because it is in this palette.
- Rounded cards/controls, subtle borders and shadows, generous spacing, and a readable sans-serif font.
- Use colour with text/icons for statuses; never colour alone.
- Keep essential data and actions visible without making the screen visually dense.

### Layout

- Desktop-first sidebar with a compact header and spacious main content area.
- Tables for patient, queue, follow-up, and report lists.
- Drawers or focused panels for quick registration and scheduling; use a full page when forms need more room.
- Responsive tablet layouts; smaller screens retain all essential actions without clipped controls.
- Queue and follow-up views should allow staff to act with minimal navigation.
- Patient profile should remain visually distinct from a visit so staff know which record they are editing.

### Interaction quality

- Keyboard-accessible navigation, visible focus, labelled fields, and logical tab order.
- Clear required/optional indicators and concise validation messages.
- Search, filters, loading, empty, error, and save-success states.
- Confirm destructive or disruptive actions such as merges, cancellations, or account deactivation.
- Warn about unsaved changes before leaving a form.
- Prevent accidental double submission; show recoverable errors without losing input.
- No upload buttons, doctor workspace, or external-message actions.

## 16. Core journeys

### New patient

Search for existing record -> review possible matches -> register -> optionally record reported history -> create visit -> assign department/doctor -> generate token -> manage queue status -> complete visit -> optionally schedule follow-up.

### Returning patient

Find patient -> review earlier visits and reported history -> update history if needed -> create a fresh visit with current complaints -> assign queue -> complete attendance.

### Scheduled follow-up return

Open follow-up/patient -> verify identity -> create new Follow-up type visit -> link scheduled follow-up -> mark follow-up Attended -> manage the new visit through the queue.

### Follow-up reminder handling

Open due reminder -> view patient contact details -> record contact attempt -> keep scheduled, reschedule, cancel, or later record attendance. No external message is sent by the application.

### Master administration

Sign in -> manage staff, doctors, departments, and settings -> review audit logs and operational reports.

## 17. Suggested data model

| Entity | Key contents |
| --- | --- |
| HospitalSettings | Identity, timezone, numbering and reminder configuration |
| StaffUser | Identity, role, credential reference, active state |
| Patient | UHID, demographics, contacts, address, active state |
| PatientIdentifierAlias/Merge | Previous identifiers and controlled merge mapping |
| HistoryRevision | Patient, category, reported state/content/source, actor, time |
| Department | Code, name, active state |
| Doctor | Code, name, active state |
| DoctorDepartment | Valid doctor/department associations |
| OPDVisit | Patient, date/time, department, doctor, type, status, history revision reference |
| VisitComplaint | Visit, complaint, optional duration |
| QueueEntry/Transition | Visit, token scope/date, status history and timestamps |
| FollowUp | Patient, origin visit, scheduled date/time, reminder, assignee, status, attendance visit |
| FollowUpRevision | Previous schedule/status changes, actor, reason, time |
| ContactAttempt | Follow-up, outcome, note, actor, timestamp |
| InternalReminder | Follow-up schedule revision, due time, lifecycle state |
| ReminderAcknowledgement | Reminder, staff user, acknowledged/snoozed state and time |
| AuditEvent | Actor, action, entity, time, reason, permitted change details |
| OperationalLookup | Typed configurable list values and active state |

Use database uniqueness constraints for UHIDs and token scope/number combinations. Use stable internal IDs rather than names as record references. Store timestamps consistently and display them in the configured hospital timezone. Keep date-only follow-ups as date-only values rather than inventing a clinical appointment time.

## 18. Security, integrity, and reliability

- Protect patient information through authenticated access and role checks.
- Use encrypted transport in production and securely stored password hashes.
- Keep secrets out of source code, browser bundles, and logs.
- Record important patient edits, history changes, visit/status changes, follow-up changes, merges, staff changes, and settings changes with actor/time.
- Restrict audit access and redact credentials and unnecessary sensitive values from logs.
- Archive/deactivate operational records rather than silently deleting historical data.
- Use transactions for patient/visit creation, token allocation, merges, and follow-up attendance linking.
- Handle concurrent edits with a conflict warning/version check rather than silently overwriting another staff member's changes.
- Use idempotency or equivalent safeguards for repeat submissions and reminder generation.
- Back up the database and verify a restore before production rollout.
- Define retention, access review, recovery objectives, and hosting arrangements before production.
- Routine operation must work without internet while the local server and hospital LAN are available.
- Bundle required fonts/assets locally; avoid runtime cloud dependencies.
- A disconnected client does not support independent offline writes; show local-server connectivity failures and allow safe retry.

## 19. Performance and operational targets

Proposed initial targets, to be validated against expected hospital volume:

- Common search/list/dashboard actions complete within 2 seconds under the agreed normal load.
- Typical saves complete within 2 seconds excluding network interruptions.
- Queue changes become visible across active staff sessions within 5 seconds.
- Paginate large lists and report results.
- Define expected daily visits, total patient records, concurrent staff, and attachment-free database growth before load testing.
- Monitor application errors, failed sign-ins, reminder processing, and database health without exposing patient data unnecessarily.

## 20. Acceptance criteria

### Access

- Admin and Master can sign in using individual accounts.
- Admin cannot access Master-only APIs or screens, including by manually changing URLs.
- Deactivated Admin users lose access; the sole Master cannot be deactivated and a second Master cannot be created.

### Patient management

- A new patient receives exactly one unique 8-character alphanumeric UHID even if Save is retried; generation collisions are retried safely.
- Registration rejects missing age or missing/blank address on both client and server.
- A returning patient can be found by UHID, name, or phone without registering again.
- Shared phone numbers and No mobile registration work.
- Unknown DOB is not stored as today's date; approximate age remains identifiable.
- Duplicate warnings permit review, and controlled merges preserve linked records and identifier traceability.

### History and visits

- Reported history distinguishes None reported, Unknown, and Not asked.
- Updating history leaves previous revisions available.
- A new visit never overwrites an earlier visit or automatically inherits its complaints.
- Inactive doctors/departments cannot be assigned to new visits but remain visible historically.
- Concurrent registrations do not generate duplicate tokens within the selected scope.
- Every significant queue transition records the responsible staff member and time.

### Follow-ups

- Admin can schedule a follow-up and choose an internal reminder time.
- Due and overdue views use the configured timezone and date-only rules.
- Reminders remain available after signing out and reopening the application.
- Recording a contact attempt does not mark attendance.
- Rescheduling preserves history and prevents obsolete reminders from remaining active.
- Attendance creates a separate linked visit and closes the scheduled follow-up.
- Cancelled/Attended follow-ups do not continue producing pending reminders.
- Multiple staff members do not accidentally create duplicate attendance visits from the same follow-up.
- No SMS, WhatsApp, email, or other external patient message is sent.

### Reports and UI

- Dashboard counts reconcile with filtered visit and follow-up reports.
- Neither role has report/data export controls or accessible export endpoints.
- Due follow-ups produce in-app pop-ups, with no message delivery.
- Routine workflows work on the hospital LAN without internet.
- The light blue and white UI works with keyboard navigation and on agreed desktop/tablet sizes.
- There are no upload or doctor-login features exposed. Billing is available to authenticated staff.

## 21. Implementation work plan

### Phase 1: Confirm and design

- Resolve the open decisions below and agree measurable workload targets.
- Finalize screen flows, low-fidelity wireframes, and light blue/white design tokens.
- Finalize schema, role matrix, status transitions, and API contracts.
- Use Python FastAPI, Next.js and SQLite, hosted locally at the hospital.

### Phase 2: Foundation and access

- Create application shell and shared UI components.
- Implement authentication, Admin/Master authorization, secure initial Master setup, and staff management.
- Implement database migrations, audit infrastructure, and hospital configuration.
- Implement doctor, department, and lookup masters.

### Phase 3: Patients and history

- Build directory/search, registration, validation, duplicate warnings, profile, and history revisions.
- Implement controlled duplicate resolution.
- Verify patient identity and historical record preservation.

### Phase 4: Visits and queue

- Build visit creation, complaints, doctor/department assignment, token allocation, and queue actions.
- Implement status history, concurrent updates, and returning-patient workflows.

### Phase 5: Follow-ups

- Build scheduling, internal reminders, due/upcoming/overdue views, contact attempts, rescheduling, cancellation, and return-visit linking.
- Verify reminder persistence and retry behavior.

### Phase 6: Dashboard and reports

- Build dashboard counts and actionable work lists.
- Build in-app operational reports and filters without export/download or dedicated print actions.
- Reconcile counts and permissions across screens.

### Phase 7: Validation and launch

- Test complete new-patient, returning-patient, and follow-up journeys with sample data.
- Test role boundaries, concurrency, numbering, date boundaries, rescheduling, and error recovery.
- Review accessibility, responsiveness, and performance against agreed targets.
- Verify backup/restore, deployment configuration, and staff onboarding instructions.
- Conduct hospital staff acceptance review and resolve release-blocking issues.

## 22. Confirmed decisions and remaining clarifications

### Confirmed on 23 October 2026

- One hospital location.
- Separate daily token sequence per doctor.
- Follow-up reminders are on-screen pop-ups only; no messages.
- Exactly one Master account controls doctors and all system setup; separate Admin staff accounts handle operations.
- Age and address are mandatory for registration.
- UHID is an 8-character alphanumeric identifier.
- No data export option for either role in this release.
- All application services and data remain local to the hospital.
- Selected stack: Python FastAPI backend, Next.js frontend and SQLite local database.
- Billing is included: Master controls doctor fees; staff generate bills for completed visits and record full/partial payments.

### Doctor reassignment explained

Example: a waiting patient has token 05 with Dr A and is moved to Dr B. Since each doctor has a separate queue, the proposed behavior is to allocate the next available token in Dr B's queue, retain token 05/Dr A in the audit history, and keep the same visit identifier. This proposal still needs confirmation.

### Local architecture

- Browser clients connect over the hospital LAN to a local server running the frontend, FastAPI API, reminder processing, and database.
- No cloud hosting, cloud patient storage, or external messaging dependency.
- Store reminders centrally on the local server so they survive browser closure/restarts.
- The server must be running for shared access and reminder evaluation; unopened clients show pending pop-ups on their next authenticated session.
- SQLite is selected. The server machine, backup destination/schedule, local HTTPS, and startup/service setup remain hospital deployment decisions. Backup, restore-copy and local Master recovery commands are delivered.
- Next.js is selected; Svelte/SvelteKit is not part of the implementation.

### Remaining clarifications

| Decision | Proposed default / clarification needed |
| --- | --- |
| Doctor reassignment | Next token in destination doctor's queue with original token retained in history; awaiting confirmation |
| Daily workload | The answer "yes" supplied no quantities; still need doctors, visits/day, concurrent staff, and approximate patient count |
| Follow-up reminder time | Admin-selectable; no default is assumed. Master may configure a default later |
| Follow-up visibility | Optional assignee with shared operational visibility; confirm whether narrower reminder routing is needed |
| Master recovery | Local interactive recovery is implemented; assign an authorized hospital server operator |
| Existing patient records | Confirm whether a one-time local migration is needed; no general upload/import UI is included |
| Local infrastructure | SQLite is selected; choose server machine, backup ownership/schedule and startup/HTTPS arrangements |
| Language | English initially; confirm need for Marathi/Hindi or other languages |
| Data retention | Agree retention and correction procedures before production |

These decisions do not expand the agreed functional scope. Billing, uploads, doctor-facing clinical features, and external messaging remain excluded.

## 23. Delivered implementation and handover

The local Next.js/FastAPI/SQLite implementation is in frontend/ and backend/. README.md provides run/setup/test and maintenance instructions. FINAL_IMPLEMENTATION_AND_NEXT_STEPS.md records delivered capabilities, verification results, implementation limits, open policies and the work remaining before hospital rollout. Business choices that remain open must not be interpreted as approved merely because implementation offers configuration controls.

- A visit with a saved, non-cancelled follow-up shows a green calendar checkmark and “Follow-up set” action. Clicking opens the existing follow-up; cancelling restores the add action. This indicator persists across refreshes.

- Today’s OPD filters: Waiting (default), Being Attended, Completed, and Cancelled. Remove All visits. The same four statuses are available in inline and visit-detail attendance controls.

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

## Billing requirements update — 24 October 2026

The updated billing specification and implemented workflow are documented in [BILLING_IMPLEMENTATION.md](BILLING_IMPLEMENTATION.md). This supersedes earlier billing exclusions.

## Database scope update

The user has changed the database requirement to Neon PostgreSQL and confirmed a fresh empty database. PostgreSQL is configured by server-only DATABASE_URL; credentials must never enter browser code or version control. No existing SQLite records are migrated. Earlier local-only storage requirements are superseded by this explicit change. Other workflows and permissions remain unchanged.
