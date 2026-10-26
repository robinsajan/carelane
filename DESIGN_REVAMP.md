# OPD design revamp

Implemented using the project-installed `design-taste-frontend` skill from Leonxlnx/taste-skill.

## Direction

Framed sheet, seed **952344936**. No redraws. The existing light blue and white palette is retained; a pale blue frame surrounds a white working sheet. Segoe UI is used locally, without a font download. The signature element is the doctor's token alongside patient identity, attendance control, and follow-up action.

The main question is: **Who needs reception's attention next?** Registration and visit creation are available in the dashboard title row. The live queue leads the workspace; follow-ups carry the next action, while activity remains secondary.

## Delivered

- Consistent shell, navigation, typography, spacing, controls, and restrained status colours across patient management, OPD, follow-ups, reports, and settings.
- Practical page titles instead of promotional copy; sentence-case table headings.
- One divided metric strip instead of separate decorated KPI cards. Counts show their actual values without decorative zero padding.
- Five-row dashboard queue and four-row follow-up preview with links to the full views.
- Direct attendance controls and existing edit/follow-up actions retained.
- Compact blue activity bars with integer ticks, zero-height zero values, and no decorative minimum bar height.
- Flat sign-in layout with a brief explanation of patient records, doctor queues, and internal reminders.
- Larger, higher-contrast labels and fields; sticky dialog headers and save actions; visible keyboard focus.
- Tablet navigation folds. On phones, OPD queues become stacked entries with attendance and follow-up controls. Follow-ups appear before the activity chart. Other wide tables scroll within their frame.
- No backend, authentication, permission, or hospital-data changes.

## Screen questions

| Screen | Primary question |
| --- | --- |
| Reception overview | Who is waiting, being attended, or due to return? |
| Patients | Is this an existing patient, and which record should staff use? |
| Today's OPD | Which patients are in this doctor's queue and what is their attendance state? |
| Follow-ups | Which return visits need attention? |
| Patient profile | What information and visit history belong to this patient? |
| Reports | What happened during the selected period? |
| Hospital settings | Which operational or access setting needs changing? |

## Validation and limits

- Next.js production build and TypeScript checks passed.
- All **11 frontend interaction tests passed**, including name suggestions/autofill, existing-record reuse, attendance, conflicts, and follow-up defaults/indicators.
- Live browser review used only the separate fictional preview database. Verified the queue filters and patient-name suggestions, selection, autofill, and Create visit action.
- The installed skill's browser inspector ran on a captured dashboard DOM with local styles at **1440, 768, and 390 pixels**: **0 FAIL, 2 WARN**. Every final fold and page screenshot was opened and reviewed.
- The inspector's text-size warning reflects the many 11–12px secondary labels and captions; patient identities and primary data use 13–14px. Its data-hue warning misses the CSS bar chart; the screenshots visibly show the blue data series. Neither warning is suppressed.
- Source lint on the changed UI files and theme: **0 FAIL**. Remaining warnings concern the rule hiding obsolete eyebrows, floating dialog shadows, `backdrop-filter:none`, and real token/visit-number padding.
- An initial attempt to inspect the already-running port 3000 returned an unstyled loading screen with stale assets. No valid before/after score comparison is claimed. Responsive inspection uses a captured rendered dashboard, not an automated signed-in navigation sweep of every screen.
- A later browser confirmation for closing an unsaved preview form stopped responding; no patient changes were saved. The production build and interaction tests remain the verification for operations beyond the browser checks above.
- No external imagery, new production dependencies, invented hospital statistics, or sample content were added to the application. Screenshot names and counts come from the existing fictional preview only.

## Final visual critique

1. Hierarchy: patient queue first; registration and visit creation immediately visible. The activity header appears near the desktop fold.
2. Grid: one 24px gutter; a 228px navigation frame, fluid white sheet, and 290px follow-up rail. Smaller widths stack the rail without stretching empty panels.
3. Colour: pale blue frame, neutral controls, blue patient count/activity, semantic follow-up/status signals. No gradients on visible working screens.
4. Data: preview counts reconcile (11 visits = 7 waiting + 1 being attended + 1 legacy Called + 2 completed). Weekly bars total 39. Dashboard previews are deliberately capped; counts describe the complete queue.
5. States: real zeros remain zero; selection, disabled controls, errors, and existing-record reuse retain their original behavior.
6. Chart: one blue series, integer count ticks, no fictitious growth or decorative values.
7. Phone: navigation folds and queue controls remain visible within stacked entries. Full directory/report tables retain internal scrolling.

Restart the frontend after deploying this build and hard-refresh the browser to clear stale asset references. Backend restart is not required for this design change.

## Doctor queue overview update

OPD now starts with peer doctor panels, replacing the mixed all-doctor visit list. The existing Framed sheet direction and palette are retained. Each panel answers: who is being attended by this doctor, and who is next? A full-day count strip doubles as the status filter; patient/token previews are real visit rows. Selecting a count drills into the existing attendance and follow-up workflow. No new production dependencies or fixture data were added.

### Queue overview validation

- Existing Framed sheet direction, seed 952344936, retained without redraws.
- Live preview checked today's zero queues, a previous day's populated queues, and selecting Dr Priya's Being Attended count to show only her current patient with the existing attendance and follow-up controls.
- Captured rendered overview inspected at 1440, 768 and 390px: 0 failures, 1 warning (secondary 11–12px labels). Every listed fold and page screenshot was reviewed. Primary patient names are 14px, doctor names 16px, and queue counts 24px.
- Critique: the first block answers which doctor has waiting patients; all panels share the same grid; colour marks waiting counts and in-progress patients; totals reconcile across doctors (5 + 3 + 3 = 11 in the fictional preview); zeros and empty queues remain explicit; there are no charts or misleading legends; phone panels stack with full-size controls. Panels keep their natural height for different queue lengths.
- Preview names and counts are existing fictional fixtures. No hospital data was changed. Tests: 22 backend and 13 frontend interactions passed.

### Attendance actions on doctor cards

Each waiting patient preview has Attend and Cancel controls. Each patient being attended has Complete and Cancel controls. Cancellation collects a required short reason inline. Cancelled visits appear in an expandable section of the doctor card, with Back to waiting; this restores the same visit and original token, with an audit reason. The card previews up to three cancelled visits and links to the complete cancelled list when there are more. Actions use version checks, show saving/errors, refresh counts and previews after saving, and prevent repeating a successful action while the refreshed queue is loading.

### Doctor queue reference layout

Use the supplied reference image: one white rounded board, a Doctor queues heading with date and live doctor/visit totals, a compact summary of waiting patients, patients in consultation and available doctors, and aligned Doctor / Patient queue / Action columns. Each doctor has a single row with initials, clickable name and availability derived from active status and current attendance. Patient tokens, names and Next in line / In consultation labels align with Attend or Complete and a cancel icon. Empty rows say Queue is clear. On narrow screens the doctor identity stacks above its queue without hiding controls. All actions use the existing API and audit/version checks. No preview-only labels or fixed sample statistics are rendered in the live app.

Reference-table visual review: checked the live fictional preview with empty and populated queues. Responsive captured-DOM screenshots reviewed at 1440, 768 and 390px. The inspector's micro-label rule is explicitly allowed for the three uppercase column headers because they match the user's supplied reference. The phone warning concerns small secondary metadata. Primary names and actions remain readable and visible on a single patient row. The patient actions, cancellation form, existing queue navigation, counts, and build pass all 16 frontend interaction tests. Critique: doctor identities and patient/action columns align; summaries derive from the same daily rows; inactive/empty data remain explicit; the phone stacks doctor identity over the queue without losing controls. The existing Framed sheet palette and font remain in use; no new assets or mock data were added to the application.
