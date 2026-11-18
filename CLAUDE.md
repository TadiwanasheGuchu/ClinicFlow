# CLAUDE.md — ClinicFlow

Guidance for Claude Code when working in this repository.

**ClinicFlow — Healthcare, organised.** A multi-tenant Healthcare Practice Management System (HPMS) for independent practitioners, private practices and multi-branch clinics. Initial market: Swakopmund and Walvis Bay (Erongo Region, Namibia), then nationwide. Currency: Namibian Dollar (NAD). Responsive web app (desktop + mobile).

> **Status:** Phases 1–5 (platform foundation; patients and scheduling; patient portal and notifications; clinical records; billing and medical aid) and, from Phase 6, operational and financial reports, laboratory orders and results, inventory and staff rostering are built — see "Implementation conventions" below and `README.md` for commands. If something here conflicts with existing code, ask before diverging.
>
> **Full specification:** [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md) — the complete product requirements, per-module features, full table/column definitions, commercial model and roadmap. Read the relevant section before implementing a module or designing its tables.

---

## Non-negotiable rules

These apply to every change. Treat a violation as a bug.

1. **Tenant isolation.** Every organisation-owned table has `organisation_id`; branch-specific tables also have `branch_id`. Every query is scoped by the current tenant on the backend. PostgreSQL Row-Level Security is defence in depth. Never rely on frontend filtering.
2. **Backend-enforced permissions.** Role-based, configurable per organisation and branch. Receptionists don't automatically see clinical notes; billing officers don't automatically see full medical history; platform super-admins have **no** default access to patient clinical records (support access must be explicitly authorised, time-limited and audited).
3. **No IDOR.** Never trust IDs from the client. A patient must not reach another patient's data by changing a URL or identifier. Load resources through tenant- and ownership-scoped queries.
4. **Clinical integrity.** Clinical notes have `draft → signed → amended` states. Signed records are never overwritten; amendments create a new version and keep the original. Prescription creation/cancellation is audited.
5. **Financial integrity.** Paid invoices are never silently edited — use credit notes and adjustments. Invoices, payments, claims and bookings run in database transactions. Money is `NUMERIC(12,2)`, never float. Never store raw card details.
6. **Audit everything sensitive.** `audit_logs` is append-only and not modifiable by application users. Log clinical record access, appointment changes, financial changes, permission changes and break-glass access (which must require a reason).
7. **No sensitive data in messages.** SMS/WhatsApp/email reminders must never contain diagnoses, prescriptions or other clinical information.
8. **No AI diagnosis or prescribing.** Do not build autonomous clinical decision features.
9. **No real patient data** in development, tests, fixtures, seeds or logs. Use synthetic data only. Don't log PHI.
10. **Secrets outside source code.** Use environment variables / secret stores.
11. **Don't over-claim integrations.** Medical aid electronic claims, eligibility checks, lab/pharmacy exchange, NAMIF/NAM-X and FHIR are *future adapters*. Ship manual workflows first; never label an integration "supported" or "certified" in UI or docs until it's formally verified.
12. **Credentials ≠ licence.** A registered professional doesn't automatically have a current licence; clinical permissions are enabled only after professional registration is verified.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router) + TypeScript |
| UI | shadcn/ui + Radix UI, Lucide icons |
| Styling | Tailwind CSS + CSS variables |
| Backend | Python, FastAPI |
| Database | PostgreSQL 16+ |
| ORM / migrations | SQLAlchemy / Alembic |
| Auth | OpenID Connect (Keycloak) |
| Background jobs | Celery |
| Queue / cache | Redis |
| Files | S3-compatible private object storage, short-lived signed URLs |
| API | REST + OpenAPI |
| Containers / proxy | Docker, Docker Compose; Caddy or Nginx |
| Observability | OpenTelemetry + error monitoring |
| Tests | Pytest (backend), Playwright (frontend/E2E) |

**Architecture:** a **modular monolith**, not microservices. Keep module boundaries clean (each module owns its models, schemas, services, routes) so modules can be extracted later. Modules talk through service interfaces, not each other's tables.

---

## Repository layout (target)

```text
backend/
├── app/
│   ├── main.py
│   ├── core/            # config, security, permissions, tenancy, audit, exceptions
│   ├── modules/         # organisations, branches, users, staff, patients, appointments,
│   │                    # queues, encounters, clinical_records, prescriptions, laboratory,
│   │                    # referrals, billing, medical_aid, inventory, notifications,
│   │                    # reports, subscriptions
│   ├── integrations/    # messaging, payments, medical_aid, laboratories, interoperability
│   ├── tasks/           # Celery tasks
│   └── shared/
├── migrations/          # Alembic
├── tests/
├── Dockerfile
└── pyproject.toml

frontend/
├── app/
│   ├── (public)/  (patient)/  (reception)/  (doctor)/  (clinic-admin)/  (platform-admin)/
├── components/  ui/ calendar/ patients/ clinical/ billing/ dashboard/
├── features/  hooks/  lib/  services/  types/
```

Dev environment (Docker Compose): frontend, backend, PostgreSQL, Redis, worker, object storage, reverse proxy.

---

## Implementation conventions (established in Phase 1)

**Backend**
- Tenant-scoped endpoints depend on `require("perm.code")` (or `require(..., org_wide=True)`) from `app/core/tenancy.py`. It resolves the `X-Organisation-Id` header, checks active membership, and scopes the DB session. For a specific branch's resource, also check `ctx.has_in_branch(...)` and `raise deny(ctx, ...)`.
- Look resources up by id through the scoped session (`db.get(Model, id)` → 404). RLS makes another tenant's id indistinguishable from a missing one.
- Handlers that write **call `db.commit()` explicitly** before returning, and record audit events in the same transaction with `ctx.audit(db, "resource.action", "resource", id, details=...)`.
- Every new tenant table needs, in its migration: `organisation_id`, `ENABLE` + `FORCE ROW LEVEL SECURITY`, a `tenant_isolation` policy (`organisation_id = app_current_org()`), grants to the app role, and composite FKs `(organisation_id, x_id)` for same-tenant references. Copy the pattern in `migrations/versions/*_0001_*`.
- The app connects as `clinicflow_app`; migrations run as `clinicflow_owner`. Neither is a superuser. Never use a superuser at runtime.
- Avoid `RETURNING` on inserts into tables whose SELECT policy may not match the new row (set defaults client-side, as `audit_logs.timestamp` does).
- New permission codes go in `app/core/permissions.py` (and role templates); `python -m app.cli sync-permissions` upserts them on deploy.
- Booking rules live in `app/modules/scheduling/service.py`; the DB exclusion constraints on `appointments` are the final guard against double-booking. Map `ExclusionViolation` to 409 `slot_taken`.
- Clinical permissions are filtered out in `get_tenant` unless the member's staff profile is verified and the licence current (rule 12) — don't bypass this when adding clinical endpoints.
- Patient portal endpoints use `PortalContext` (`app/modules/portal/context.py`), not `require()`. Patients are not members: always filter patient data by `ctx.patient.id` (`own_appointment`), and reuse the booking engine (`appointments.service.book/move/withdraw`) rather than writing new rules.
- Patient messages go through `notifications.service` (outbox + `python -m app.worker`). Templates may only use `MessageFields`; never add appointment type, practitioner, notes or anything clinical (rule 7). No SMS/WhatsApp provider is integrated yet — add one as an adapter in `notifications/adapters.py`.
- Clinical records (`app/modules/clinical/`): check `clinical.read/write/sign` / `prescriptions.issue` per branch with `service.require_in_branch`; audit every view with `service.log_view`; keep audit `details` to identifiers and types — never note text, diagnoses or medications (the audit log is readable without clinical access). Signed notes and issued prescriptions are trigger-protected: correct via amendments, status changes or cancellation, never UPDATE/DELETE.
- Billing (`app/modules/billing/`): money is `Decimal`/`NUMERIC(12,2)` with half-up rounding per line; lock the invoice row (`get_invoice(..., lock=True)`) before any money operation; derive status from amounts (`derive_status`), never set it directly. Issued invoices, payments, credit notes, refunds and claim history are trigger-protected — corrections are credit notes, refunds or reversals. Claims carry ICD-10 codes only, never diagnosis text. Medical aid stays a manual workflow (no electronic submission/eligibility).
- Standalone entry points (CLI, worker) must `import app.models` so every table is registered.
- Laboratory (`app/modules/laboratory/`): orders come from an open consultation (`clinical.write`); `lab.read`/`lab.process` are credential-gated like clinical permissions (the Laboratory technician role has no access to notes); review needs `clinical.sign`. Transitions live in `service.TRANSITIONS`. Results are trigger-protected — correct with entered-in-error plus a new result; any change to a reviewed order sends it back to `completed`. Audit details carry identifiers and counts only, never test names or values. Manual workflow only: no laboratory integration, no uploaded reports yet.
- Inventory (`app/modules/inventory/`): stock changes only by inserting `stock_movements`; a trigger applies each one to its batch, `quantity_remaining >= 0` blocks negative stock, and batches/movements can't be edited or deleted. Usage is first-expiry-first-out and never takes expired batches (write them off). Wrap movement inserts in `db.begin_nested()` with the `add` inside, so a rejected row is discarded. Quantities are whole units; costs are `NUMERIC(12,2)`.
- Roster (`app/modules/roster/`): exclusion constraints stop overlapping shifts and overlapping open leave per member. Every member manages their own leave (`/me/leave`); `roster.manage` decides it — branch managers only for staff with roles in their branch, and nobody approves their own. Approved leave for a practitioner creates a linked provider unavailability; affected appointments and shifts are reported, never cancelled automatically. Leave type and reason are shown only to the person and their managers.
- Every migration needs a working `downgrade()`; `tests/test_migrations.py` round-trips head → base → head.
- Reports (`app/modules/reports/`) are read-only aggregates gated by `reports.operational` / `reports.financial`; they return identifiers and counts, never clinical text, and cap ranges at 366 days.
- Tests use real PostgreSQL (`backend/tests/conftest.py`). Every feature gets cross-tenant and permission-denial tests.

**Frontend**
- Server components and server actions call the API through `api()` in `lib/api.ts`. Tokens never reach the browser; don't add client-side API calls with tokens.
- Mutations are server actions wrapped in `attempt()` (`lib/actions.ts`), returning `FormState` for `useActionState` forms. Render forms with `<ActionForm action={formAction} pending={pending}>` (`components/ui/form.tsx`), not `<form action>`: React 19 resets uncontrolled forms after every action, which would wipe input on validation errors.
- Clinical entry forms must not be resubmittable by accident: new-item forms clear after success (`useResetKey`) and new-note editors close once created (see `features/clinical/forms.tsx`).
- `proxy.ts` passes the requested path as `x-pathname`; `requireWorkspace` uses it as the return path when it has to send the user through `/switch` to pick an organisation.
- Times: scheduling uses the organisation timezone (`Africa/Windhoek`); use helpers in `lib/time.ts` (`dayRange`, `localISO`, `dateOf`, `timeOf`), never `iso.slice(0, 10)` for a local date.
- UI primitives live in `components/ui/`; merge classes with `cn()` from `lib/cn.ts`. Gate UI with `hasPermission` / `hasOrgWide`, but the API is the authority.

---

## Database conventions

- UUID primary keys; `created_at` / `updated_at` as `TIMESTAMPTZ`.
- Foreign keys everywhere; soft-delete only where appropriate (never for audit or signed clinical data).
- Every schema change goes through an Alembic migration.
- Status columns are validated state machines on the backend — reject invalid transitions.

**Key constraints**
- Unique per organisation: patient number, invoice number, prescription number. Unique appointment reference.
- No overlapping provider appointments — enforce at DB level (e.g. exclusion constraint on `tstzrange(start_at, end_at)` for active statuses), with an audited authorised-override path. Must hold under concurrent booking requests.
- No negative stock unless explicitly authorised.

**Core table groups** (full columns in `docs/BLUEPRINT.md` §6):
- Access: `organisations`, `branches`, `users`, `organisation_memberships`, `roles`, `permissions`, `role_permissions`, `staff_profiles`
- Patients: `patients`, `patient_contacts`, `patient_guardians`, `patient_consents`, `medical_aid_memberships`
- Scheduling: `providers`, `specialties`, `provider_availability`, `provider_unavailability`, `appointment_types`, `appointments`, `appointment_events`, `clinic_rooms`, `queue_entries`
- Clinical: `encounters`, `clinical_notes` (versioned), `diagnoses`, `allergies`, `observations`, `medication_catalogue`, `prescriptions`, `prescription_items`, `referrals`
- Lab: `laboratory_orders`, `laboratory_order_items`, `laboratory_results`
- Finance: `service_catalogue`, `invoices`, `invoice_items`, `payments`, `credit_notes`, `medical_aid_funds`, `medical_aid_claims`, `claim_events`
- Inventory: `inventory_items`, `suppliers`, `stock_batches`, `stock_movements`, `purchase_orders`
- Platform: `documents`, `notification_templates`, `notifications`, `audit_logs`, `subscriptions`, `licences`

Patients have an organisation-specific identifier. Never share patient identity across organisations automatically.

---

## Domain state machines

- **Appointment:** Requested, Pending confirmation, Confirmed, Checked in, Waiting, In consultation, Completed, Cancelled, No-show. Every change writes an `appointment_events` row.
- **Clinical note:** Draft, Signed, Amended.
- **Laboratory order:** Requested, Collected, Sent, Processing, Completed, Reviewed, Cancelled.
- **Medical aid claim:** Draft, Ready for submission, Submitted, Processing, Accepted, Rejected, Partially paid, Paid, Resubmission required.

Scheduling rules: no booking outside provider availability or during unavailability; configurable buffers; cancellation policies; authorised overrides are audited.

---

## User roles

Platform Super Administrator, Organisation Owner, Organisation Administrator, Branch Manager, Receptionist, Doctor, Dentist, Physiotherapist, Nurse, Practice Manager, Medical Billing Officer, Pharmacist/dispensary user, Laboratory Technician, Patient, Auditor (read-only). Roles map to configurable permission codes; check permission codes, not role names, in code.

---

## Specialty modules

The core EMR must stay specialty-agnostic. General practice, dental (tooth chart, treatment plans, quotations), physiotherapy (assessments, sessions, progress measures) and specialist workflows are optional extensions that build on the core — the core must not depend on any one specialty's data structure.

---

## Non-functional targets

- Dashboard responses < 2 s; common queries < 500 ms (to be load-tested).
- Paginate large lists. Notifications, reminders and reports run in background workers with retries and delivery tracking.
- 99.5% monthly availability target; automated encrypted backups with a tested restore procedure.
- Mobile-first patient portal; desktop-optimised reception/admin; low-bandwidth friendly; resilient to internet interruptions.
- Accessibility: keyboard navigation, labelled forms, adequate contrast, screen-reader-friendly controls, accessible error messages.

---

## UI / design system

**Read [`docs/DESIGN.md`](docs/DESIGN.md) before any UI work and run its review checklist before finishing.** It overrides blueprint §9. Key rules:

- **Fonts:** IBM Plex Sans (UI, body, headings) + IBM Plex Mono (IDs, amounts, codes, times). **Never** Inter, Manrope, Poppins, Plus Jakarta Sans, DM Sans, Geist, Outfit, Sora, Space Grotesk, Montserrat, Nunito or Roboto. Tabular numerals for all numbers.
- **Colour:** tokens only (primary teal `#126B67`, background `#F5F8F8`, surface `#FFFFFF`, text `#203334`). No Tailwind default palette classes, no raw hex in components. Use `-text` token variants for coloured text; the base warning, success, danger and secondary colours fail AA as text. No gradients, no purple, indigo or violet, no glass, blur or glow. Status is never shown by colour alone. Light theme only.
- **Icons:** Lucide only, stroke 1.5, 16px or 20px, only where they aid scanning. No `Sparkles`, `Rocket` or `Zap`, no emoji, no icons in tinted circles.
- **No generic-AI patterns:** no KPI-card grids with fake trends, no "Welcome back 👋" headers, no `rounded-2xl` shadowed cards everywhere (radius 6px, flat 1px borders), no marketing copy in the app, no decorative charts or animations, no unstyled stock shadcn.
- **Density:** tables are the primary component (36–40px rows, sticky headers, monospace right-aligned amounts). 14px base on staff screens, 16px on the patient portal.
- **Clinical safety UI:** a pinned patient identity banner (name, DOB and age, patient number) with an allergy indicator on every clinical screen, never blank. Confirmations for irreversible actions name the patient or object.
- **Formatting:** `N$1,250.00`, `16 Nov 2026`, 24-hour time, `Africa/Windhoek`, British English.

---

## Testing expectations

Write tests alongside features. Priorities:
- **Backend:** auth, permissions, tenant isolation (cross-tenant access must fail), booking conflicts incl. concurrency, clinical note signing/amendment, invoice calculations, payment reconciliation, claim transitions, audit logging.
- **Security:** IDOR, broken access control, privilege escalation, file access restrictions, injection, XSS, CSRF where applicable, session management.
- **Frontend (Playwright):** patient registration, online booking, check-in, consultation, invoicing, patient portal, responsive layouts.

---

## MVP scope & roadmap

**MVP:** organisations/branches, roles & permissions, patients, doctors, scheduling, patient self-booking, reception queue, EMR & consultation notes, basic prescriptions, invoicing & payments, reminders, operational reports, audit logs, backup/recovery.

**Deferred:** advanced pharmacy, lab integrations, electronic claims submission, complex hospital workflows, AI clinical features.

**Build order:**
1. Platform foundation — tenancy, branches, auth, users, roles/permissions, audit logging
2. Patients & scheduling — registration, search, providers, availability, booking engine, reception dashboard
3. Patient portal & notifications
4. Clinical records — encounters, notes, allergies, observations, diagnoses, referrals, prescriptions, signing/amendments
5. Billing & medical aid — catalogue, invoices, payments, receipts, credit notes, claim preparation/tracking
6. Specialty & operational modules — dental, physio, lab, inventory, staff scheduling, advanced reports (prioritise by pilot clinic needs)
7. Security testing, pilot, launch

Avoid scope creep: build what the current phase and pilot clinic need.

---

## Commercial context (affects licensing code)

Two models: **subscription** (Solo / Practice / Professional / Enterprise tiers gate features) and **once-off installation + annual maintenance** (dedicated deployments, tracked in `licences`). Support both managed multi-tenant cloud and dedicated installations from the same codebase. Feature gating must be driven by plan/licence data, not hard-coded per customer.

---

## Compliance note

Before production: legal/professional review against Namibian law (Health Professions Act 2024, Hospitals and Health Facilities Act, record retention, consent/disclosure, medicines and prescription rules, electronic transactions/cybersecurity, cross-border hosting, emerging data-protection law). Design the integration layer to accommodate Namibia's Digital Health Policy 2026–2036 (NAMIF, NAM-X) and HL7 FHIR via a mapping layer, without claiming compliance.
