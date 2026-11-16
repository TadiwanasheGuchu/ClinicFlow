# CLAUDE.md — ClinicFlow

Guidance for Claude Code when working in this repository.

**ClinicFlow — Healthcare, organised.** A multi-tenant Healthcare Practice Management System (HPMS) for independent practitioners, private practices and multi-branch clinics. Initial market: Swakopmund and Walvis Bay (Erongo Region, Namibia), then nationwide. Currency: Namibian Dollar (NAD). Responsive web app (desktop + mobile).

> The repository is at the start of development. Follow the architecture and conventions below when scaffolding. If something here conflicts with code that already exists, ask before diverging.
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

Professional healthcare software — not a generic CRM or decorative AI dashboard. Light theme default, restrained colour, no unnecessary gradients, compact information-dense desktop tables, clear status indicators, avoid excessive cards.

Define as CSS variables / Tailwind tokens:

| Token | Colour |
|---|---|
| primary | `#126B67` (deep medical teal) |
| secondary | `#527F9B` (muted blue) |
| success | `#26856B` |
| warning | `#D69A38` |
| danger | `#C64E4E` |
| background | `#F5F8F8` |
| surface | `#FFFFFF` |
| text | `#203334` |
| text-muted | `#687C7D` |

Fonts: **Manrope** (headings), **Inter** (body), **IBM Plex Mono** (data, references, IDs, amounts).

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
