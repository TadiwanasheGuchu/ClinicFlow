# Deploying ClinicFlow on free hosting

This is the launch setup for the pilot. It needs no payment card:

| Part | Service | Free plan limits that matter |
|---|---|---|
| Web app, API and reminder sender (one container) | [Render](https://render.com) web service, Frankfurt | Sleeps after 15 minutes without traffic (an uptime check keeps it awake); 512 MB memory; Render says free instances are not for production |
| Database | [Neon](https://neon.com) PostgreSQL, Frankfurt | 1 GB storage per project; short point-in-time restore window — our own daily backups cover the rest |
| Sign-in | [Auth0](https://auth0.com) | No custom domain without a card, so the sign-in page is on `your-tenant.eu.auth0.com` |
| Backups, admin tasks | GitHub Actions | Encrypted backups kept for 30 days |
| Uptime check | [UptimeRobot](https://uptimerobot.com) | 5-minute checks |

Free-plan terms change. Check each provider's current terms when you sign up.

> **Patient data and the law.** On this setup, patient data is stored in Germany (Neon,
> Render) and staff identities are stored in the EU (Auth0). Before any real patient is
> recorded, get the legal and professional review described in `CLAUDE.md`. It covers
> cross-border hosting, consent and record retention, and an agreement with the pilot
> clinic. Until then, use the system only with made-up (synthetic) patients.

The steps below take about an hour. Keep a password manager open, and save every password
and secret you create in it.

---

## 1. Database (Neon)

1. Sign up at neon.com and create a project. Choose region **AWS Europe Central 1
   (Frankfurt)** and PostgreSQL **17**.
2. Open **SQL Editor** while connected to the default `neondb` database. Paste
   [`deploy/neon/setup.sql`](../deploy/neon/setup.sql), replace the three passwords and run
   it. Use letters and digits only, for example `openssl rand -hex 24`.
   - If `CREATE ROLE clinicflow_maintenance … BYPASSRLS` is refused, run the rest without
     it. Then use the project's default connection string as the backup URL in step 5.
     The backup job checks that it works.
3. Switch the editor to the new **`clinicflow`** database and run the two lines at the
   bottom of the file.
4. From **Connection details**, copy the host name (like
   `ep-calm-sun-123456.eu-central-1.aws.neon.tech`). Build these three URLs:

   ```text
   CLINICFLOW_DATABASE_URL=postgresql+psycopg://clinicflow_app:APP_PASSWORD@HOST/clinicflow?sslmode=require
   CLINICFLOW_MIGRATION_DATABASE_URL=postgresql+psycopg://clinicflow_owner:OWNER_PASSWORD@HOST/clinicflow?sslmode=require
   BACKUP_DATABASE_URL=postgresql://clinicflow_maintenance:MAINTENANCE_PASSWORD@HOST/clinicflow?sslmode=require
   ```

The app creates all tables itself when it first starts. It also refuses to start if either
of its database roles can bypass row-level security.

## 2. Sign-in (Auth0)

1. Sign up at auth0.com. Create a tenant in the **EU** region.
2. **Applications → APIs → Create API**
   - Name `ClinicFlow API`, identifier **`clinicflow-api`**, signing algorithm RS256.
   - In its settings, set **Token Expiration (Seconds)** to `36000` (10 hours, the
     session length) and turn on **Allow Offline Access**.
     Tokens never reach the browser: they stay in an encrypted, httpOnly cookie on the
     server. The API checks membership, suspension and permissions on every request,
     whatever the token's age.
3. **Applications → Applications → Create Application → Regular Web Application**, named
   `ClinicFlow`. In **Settings**:
   - Allowed Callback URLs: `https://YOUR-APP.onrender.com/api/auth/callback/oidc`
   - Allowed Logout URLs: `https://YOUR-APP.onrender.com/signin`
   - Allowed Web Origins: `https://YOUR-APP.onrender.com`
   - Under **Refresh Token Rotation**, leave rotation **off**.
   - Under **Advanced → Grant Types**, keep Authorization Code and Refresh Token.

   Save the **Domain**, **Client ID** and **Client Secret**. You'll get your Render
   address in step 3; come back and fill in the URLs then.
4. **Actions → Library → Create Action → Build from scratch**. Name it `ClinicFlow claims`,
   with trigger *Login / Post Login*. Paste this code, then deploy it:

   ```js
   exports.onExecutePostLogin = async (event, api) => {
     const ns = "https://clinicflow.app/";
     api.accessToken.setCustomClaim(ns + "email", event.user.email);
     api.accessToken.setCustomClaim(ns + "email_verified", event.user.email_verified);
     api.accessToken.setCustomClaim(ns + "name", event.user.name);
   };
   ```

   Then go to **Actions → Triggers → post-login**, drag `ClinicFlow claims` into the flow
   and apply. ClinicFlow only accepts verified email addresses, and this is how the API
   learns them.
5. **Authentication → Database → Username-Password-Authentication**: set the password
   policy to *Good* or stronger. **Security → Attack Protection**: turn on brute-force
   protection and breached-password detection.
6. **Settings → Advanced**: turn on *RP-Initiated Logout End Session Endpoint Discovery*.
   Sign-out ends the Auth0 session too.

Auth0 sends verification emails through its built-in test mail service, which has low
limits. Before staff start using the system, add your own email provider under
**Branding → Email Provider**.

## 3. App (Render)

1. Merge the release branch into `main` on GitHub. Render deploys `main`.
2. Sign up at render.com with your GitHub account. Choose **New → Blueprint** and pick
   this repository. Render reads [`render.yaml`](../render.yaml).
3. Fill in the values it asks for:

   | Variable | Value |
   |---|---|
   | `CLINICFLOW_DATABASE_URL`, `CLINICFLOW_MIGRATION_DATABASE_URL` | from step 1 |
   | `CLINICFLOW_OIDC_ISSUER`, `AUTH_ISSUER` | `https://YOUR-TENANT.eu.auth0.com/` **with the trailing slash** |
   | `CLINICFLOW_OIDC_JWKS_URL` | `https://YOUR-TENANT.eu.auth0.com/.well-known/jwks.json` |
   | `AUTH_CLIENT_ID`, `AUTH_CLIENT_SECRET` | from step 2 |
   | `NEXTAUTH_URL`, `CLINICFLOW_PUBLIC_WEB_URL` | your service address, e.g. `https://clinicflow-abcd.onrender.com` |

   If you don't know the address yet, enter a placeholder. Correct it once the service is
   created, then choose **Manual Deploy → Deploy latest commit**.
4. The first build takes about 10 minutes. When it's done,
   `https://YOUR-APP.onrender.com/healthz` shows `ok`.
5. Go back to Auth0 (step 2.3) and fill in the three URLs with the real address.

## 4. First administrator

1. Open the app and sign up (or sign in) with your own email address. Verify the email.
2. In GitHub, go to **Settings → Secrets and variables → Actions** and add the secret
   `MIGRATION_DATABASE_URL`, using the migration URL from step 1.
3. Under **Actions → Grant platform admin → Run workflow**, enter your email address.
4. Reload the app. Choose **Open platform administration** on the set-up page, or use
   **Platform** in the menu.

New practices wait for your approval. When a clinic registers, approve it under
**Platform**. Your own practices are active immediately.

## 5. Backups

1. In GitHub, add these secrets:
   - `BACKUP_DATABASE_URL` — from step 1.
   - `BACKUP_PASSPHRASE` — a long random passphrase. Keep a copy outside GitHub: without
     it the backups can't be read.
2. Under **Variables**, add `BACKUPS_ENABLED` = `true`.
3. Under **Actions → Database backup → Run workflow**, run it once and check it goes green.

Each night (02:17 Windhoek time) the job makes an encrypted backup. It then **restores
that backup into a throwaway database** and checks it: row counts match, row-level
security still hides data, integrity triggers are back and the schema is current. The
backup is kept for 30 days as a workflow artifact. If a night's job fails, GitHub emails
you.

**Restoring after a loss.** Make an empty database: a new Neon project, set up with
step 1 but without running the app. Download the backup artifact. Then run:

```bash
RESTORE_DATABASE_URL='postgresql://clinicflow_maintenance:…@HOST/clinicflow?sslmode=require' \
BACKUP_PASSPHRASE='…' deploy/backup/restore.sh clinicflow-YYYYMMDD-HHMM.dump.gpg
```

Point Render's two database URLs at the new database and redeploy.

## 6. Uptime check

Create a free UptimeRobot account and add an **HTTP(s)** monitor for
`https://YOUR-APP.onrender.com/healthz` every **5 minutes**, with email alerts. This does
two jobs:
- It keeps the free service awake. One always-on service uses about 744 of Render's 750
  free hours a month, so don't run a second free service in the same Render account.
- It tells you when ClinicFlow or its database is down.

## 7. Patient messages (optional)

Until a provider is set up, appointment confirmations and reminders are saved and shown
under **Messages** as *not delivered*. Nothing is sent.

- **Email:** set `CLINICFLOW_EMAIL_PROVIDER=smtp` plus `CLINICFLOW_SMTP_HOST`,
  `CLINICFLOW_SMTP_PORT` (587), `CLINICFLOW_SMTP_USERNAME`, `CLINICFLOW_SMTP_PASSWORD`,
  `CLINICFLOW_SMTP_STARTTLS=true` and `CLINICFLOW_EMAIL_FROM`. You can use any SMTP provider
  with a free plan.
- **SMS and WhatsApp:** these need a contracted provider. Each one is added as an adapter
  in `backend/app/modules/notifications/adapters.py`.

Messages never contain clinical information.

---

## Launch checklist

- [ ] `/healthz` shows `ok`, and UptimeRobot is green.
- [ ] Signing in, signing out and the email-verification email all work.
- [ ] You are a platform admin, and a test practice can be approved.
- [ ] Practice set-up is done: branches, staff invitations, roles, verified practitioner
      registrations, working hours, appointment types and price list.
- [ ] One full test visit with a **made-up patient**: book, check in, consultation note,
      invoice and payment.
- [ ] The backup workflow ran green, and its restore drill passed.
- [ ] The backup passphrase and all passwords are stored outside GitHub and Render.
- [ ] Legal and professional review is done, and the clinic has agreed in writing, before
      the first real patient.
- [ ] The clinic knows the free-hosting limits. The first page load after a pause can take
      up to a minute, and outages are possible.

## Moving off free hosting later

The same code runs anywhere Docker runs:

- **One container:** deploy `deploy/render/Dockerfile` (Render paid plan, Koyeb, a VPS…).
- **Self-hosted, Keycloak included:** use the services in `docker-compose.yml` with your
  own production settings.

Use your own domain and a paid database plan with longer point-in-time recovery. Prefer a
data centre in southern Africa if the legal review recommends it.
