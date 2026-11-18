# ClinicFlow

Healthcare practice management for independent practitioners, private practices and
multi-branch clinics in Namibia. See [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md) for the product
specification and [`docs/DESIGN.md`](docs/DESIGN.md) for the design rules.

**Status:** Phases 1–6 are built. Phase 7 (launch) is prepared: free hosting on Render, Neon and Auth0 with encrypted, restore-tested daily backups. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

- **Platform foundation:** multi-tenancy, authentication, branches, staff, roles and
  permissions, audit log.
- **Patients and scheduling:** patient register with duplicate detection, practitioner
  registration verification, working hours and leave, appointment types, a booking engine
  that prevents double-booking at the database level, a Today reception list, and a day
  calendar.

- **Patient portal and notifications:** per-practice online booking at `/book/<slug>`
  (self-registration or link codes from reception), confirmations and reminders through a
  retrying outbox worker. SMS/WhatsApp delivery is simulated until a provider is contracted;
  email works over SMTP.

- **Clinical records:** consultations linked to appointments; SOAP notes with
  draft/sign/amend versions (signed notes are immutable at the database level); allergies
  with an explicit "no known allergies" state in the patient banner; vital signs;
  diagnoses (optional ICD-10 code); referrals; printable prescriptions with a basic allergy
  name check. Every clinical view is audited.

- **Billing and medical aid:** service price list, invoices (draft → issued, VAT optional per
  practice), payments and receipts, credit notes, refunds, payment reversals, patient
  statements and daily cash-up; medical aid funds, memberships and manually tracked claims
  (no electronic submission) with remittances posted as payments. Issued financial records
  are immutable at the database level.

- **Reports:** operational (appointments, cancellations, no-shows, waiting times, new
  patients, consultations per practitioner) and financial (invoiced, collected by method,
  refunds, revenue by service and practitioner, aged debt, medical aid claims) for any range up
  to a year, by branch.

- **Laboratory:** tests requested from a consultation (from the practice's test list or
  named by hand), a printable request form, a worklist of outstanding orders, specimen
  collection and dispatch, results per analyte with flags, and clinician review. Results are
  never edited (only marked entered in error). Manual workflow: no laboratory system is
  connected and report uploads wait for object storage.

- **Inventory:** items and suppliers, stock batches per branch with batch numbers and expiry
  dates, purchase orders and deliveries, usage (first expiry first out, never expired stock),
  stock counts, write-offs, transfers between branches, reorder and expiry lists, valuation
  at cost and a full stock history. The database refuses negative stock and edits to history.

- **Staff rostering:** a weekly roster per branch (overlapping shifts are refused), repeat a
  week, and leave: staff request it, managers approve it, and approved leave for a
  practitioner blocks their bookings. Everyone has a "My shifts and leave" page.

- **Specialty modules (switched on per practice under Organisation):** dental — FDI tooth
  chart, treatment plans issued as printable quotations (frozen once quoted), accepted
  treatment marked done and put on a draft invoice; physiotherapy — episodes of care with
  goals, sessions counted from consultations, outcome measures (pain, PSFS, range of
  movement, strength) with first-to-latest progress, and discharge.

Not yet: clinical document uploads
(needs object storage).

## Layout

```text
backend/    FastAPI modular monolith, SQLAlchemy, Alembic, pytest
frontend/   Next.js (App Router) staff app; server-side API calls (BFF)
infra/      Postgres role bootstrap, Keycloak realm for local development
docs/       Blueprint and design rules
```

## Run locally with Docker

```bash
cp .env.example .env
```

Edit `.env` and set real values for every password and `NEXTAUTH_SECRET`, then:

```bash
docker compose up --build
```

- App: http://localhost:3000. Choose **Register** on the Keycloak screen to create an
  account. The verification email arrives in Mailpit at http://localhost:8025.
- API docs: http://localhost:8000/docs
- Keycloak admin: http://localhost:8080 (user `admin`, password from `.env`)

To make a user a platform administrator, after they have signed in once:

```bash
docker compose exec backend python -m app.cli grant-platform-admin someone@example.com
```

## Backend development

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and PostgreSQL 16.

```bash
cd backend && uv sync
```

```bash
uv run pytest
```

Tests create a throwaway database and the `clinicflow_app` / `clinicflow_owner` roles. They
connect as a superuser through `TEST_ADMIN_DSN` (default
`postgresql://postgres:postgres@localhost:5432/postgres`).

```bash
uv run ruff check app tests migrations && uv run ruff format app tests
```

## Frontend development

```bash
cd frontend && npm install && npm run dev
```

Set `CLINICFLOW_API_URL`, `NEXTAUTH_URL`, `NEXTAUTH_SECRET` and `KEYCLOAK_ISSUER` in the
environment (see `docker-compose.yml` for values).

## Security model (Phase 1)

- **Tenancy:** every request names its organisation (`X-Organisation-Id`); the caller must be
  an active member. The database session is scoped to that organisation and PostgreSQL
  Row-Level Security (forced, non-superuser roles) hides all other tenants' rows.
- **Permissions:** checked by permission code on the server. Roles are per organisation and
  can be granted organisation-wide or per branch. Nobody can grant permissions they don't
  hold; only owners can grant the Owner role; the last owner can't be removed.
- **Audit:** sensitive changes and denied access attempts are written to `audit_logs`, which
  database triggers make append-only.
- **Tokens:** access tokens stay in the encrypted, httpOnly session cookie and are only used
  server-side; the browser never sees them.
