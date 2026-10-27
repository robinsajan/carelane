# Billing implementation

Scope updated on 24 October 2026. Next.js, FastAPI and SQLite; all records remain local.

## Staff workflow

1. Master opens Settings → Doctors and sets separate new-visit and follow-up consultation fees in INR. Blank means not configured; zero means a free consultation.
2. Staff completes a visit. OPD → Complete view → Completed shows a Bill action; the visit detail also offers Generate bill.
3. The bill draft loads the fee for the visit type from the assigned doctor. Staff may add up to 50 extra charge lines, each with a description, integer quantity and unit price, plus an optional note.
4. Review the calculated total, then generate one bill for the visit. The bill receives a unique number. Additional charges are editable before generation and through Edit bill afterwards.
5. Record a full or partial payment, choosing Cash, UPI, Card, Bank transfer or Other and an optional reference. This records money received; it does not initiate a financial transaction.
6. Reopen through Billing or the visit's View bill action. Record later payments against the remaining balance or print the bill with payment history.

Billing offers date-range, patient name/UHID and payment-status filters. Status is derived from totals: Unpaid, Part paid or Paid. A zero-total bill is Paid. The list displays total, paid amount and balance.

## Permissions and storage

Only Master can change doctor fees. Both Master and Admin can generate bills and record payments. Every endpoint requires an authenticated session; existing request/session protection applies.

Doctor fee columns are added through non-destructive SQLite startup migrations. Bills reference one unique visit and store the original hospital, patient, doctor and visit details plus charge lines. Payments form a separate append-only history with amount, method, reference, staff name and timestamp. Generation and payments are audited.

All calculations use integer paise. The server chooses consultation fees and recalculates totals. It rejects missing fees, non-completed visits, invalid amounts, stale versions, duplicate bills and payments above the balance. Write transactions serialize simultaneous requests; idempotency keys protect retries. Issued bill amounts and details remain fixed when doctor fees or patient information change. A billed visit cannot be cancelled, reopened or reassigned.

## Current boundaries

Issued bills can be corrected through Edit bill; deletion is not offered. Voiding, refunds, discounts, tax calculations, insurance claims, payment gateways and financial reports are not included in this version. Printing uses the browser print dialog. No data export is added.

## Validation

Six backend billing tests cover completion and fee gates, exact totals, new/follow-up fees, zero pricing, permissions, persistence, snapshot stability, duplicate/retry protection, concurrency and partial/full payments. Four frontend tests cover exact currency parsing, additional charges, missing fees and partial-payment/overpayment handling, alongside the existing OPD interaction suite. Production build includes TypeScript validation.

Restart the backend to apply additive database changes, then restart the frontend to load the new build. Configure doctor fees before generating the first bill.

## Saved billing charges

Master opens Settings & setup > Billing charges to add charge names and unit prices in INR, edit them, or mark them inactive. Names are unique. Only Master may change this catalog; Admin can use active entries on a bill.

The bill draft includes a Saved billing charge selector. Selecting an entry fills its name and unit price, with quantity defaulting to one. Quantity remains editable; the catalog name and price are read-only on that row. Remove the row to change the selection. Manual additional charges remain available through Add charge.

The server validates the saved charge version, active state, name and price before generation. A changed or deactivated charge must be selected again or removed before issuing the bill. Issued bills retain their original names, prices and quantities even after catalog edits. No deletion removes historical charges. The new billing_charges SQLite table is created automatically on backend startup.

## Generate bills directly from Billing

Billing opens to Completed visits, listing all completed visits across dates, newest first, with patient name/UHID search and optional visit-date bounds. Unbilled visits offer Generate bill; billed visits offer View bill. Each visit remains a separate row even for a returning patient. Bills & payments retains the existing bill register and payment filters. Both lists refresh after bill generation.

Billing date picker update: Completed visits and Bills & payments each use one date picker, defaulting to the hospital current date. Completed visits filter by visit date; bills filter by bill date. Both request an exact single-day interval.

## Edit bill

Open an existing bill and choose Edit bill. Master and Admin can add/remove additional charges, change manual charge descriptions/prices, adjust quantities, and edit the bill note. Original consultation fee, bill number/date, patient/doctor snapshot and payment history remain fixed. Saved catalog lines retain their original price; newly selected lines use the current master price. The corrected total cannot fall below money already received. Saving recalculates the outstanding balance and payment status. Bill/payment version checks prevent stale overwrites, retries are idempotent, and the audit log retains before/after charges, totals and notes. Cancel returns to the saved bill.

Database update: billing and payments now use the configured Neon PostgreSQL database, retaining exact integer-paise arithmetic, transaction/version checks, idempotency and audit history. Existing SQLite data was not migrated; SQLite remains the offline regression-test backend.

## Immutable bill revision history

- The bill ID and printed bill number remain the same across edits. Content revisions start at v1 and increase by one per successful edit; the highest revision is current.
- Separate bill_revisions records preserve the full bill snapshot, charges, quantities, prices, total, note and payment state at the time of saving. Editor identity, recorded timestamp and optional edit reason accompany each snapshot.
- Database triggers reject UPDATE and DELETE of revision records. Authenticated staff can list/view historical revisions; historical views have no edit or payment controls. This supports review, but is not a guarantee against a privileged database administrator tampering with the database.
- Payment recording keeps its existing separate ledger/audit trail. It increments the concurrency version, not the content revision. Historical payment amounts are explicitly snapshots at the revision timestamp.
- Existing bills receive a v1 baseline on upgrade, labelled System migration. Earlier revisions not stored by the previous application cannot be reconstructed by this feature.
- Idempotent retry does not add revisions; stale edits are rejected. Revision insertion and current bill update share one transaction.
