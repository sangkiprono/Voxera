# Voxera

Voxera is a multi-tenant voting and opinion platform built with Django REST Framework and React/TypeScript.

## What works today

- Email/password account registration and sign-in with email verification, password reset, mandatory TOTP authenticator setup, one-time recovery codes, sign-out, and profile editing.
- Organization workspace requests with manual staff approval, followed by owner, administrator, creator, and member roles.
- Organization dashboards with member, poll, survey, and response totals; daily poll/survey trends over 30 days; and top-five poll and survey response counts (owners and administrators only).
- Admin-configured subscription plans and workspace usage caps for members, active polls, and active surveys. Checkout and payment processing are intentionally disabled pending provider and pricing decisions.
- In-app notifications for workspace additions and activity comments, with recipient-only inboxes and read controls.
- Optional queued SMTP email delivery for those notifications, with recorded failures, a five-attempt retry limit, and a management command for a single scheduled worker.
- Low-stakes organization election setup: admin-created drafts, active-member eligibility snapshots at nomination opening, member self-nominations, and nomination close/cancel controls. Ballot casting is intentionally not implemented.
- Public and restricted opinion polls with direct share links, one response per signed-in account, and aggregate results.
- Surveys with single- and multi-choice, text, and 1–5 rating questions; response collection; and manager-only reports.
- CSV downloads for poll results and manager-authorized survey reports, with spreadsheet formula injection protection.
- Account-linked comments on active polls and surveys; activity creators and workspace administrators can hide/restore comments, with moderation history.
- Responsive discovery and management interfaces.
- PostgreSQL support, production-aware Django settings, Nginx routing, Docker Compose, and CI for PostgreSQL, Django tests, and the React build.

Election ballot casting, checkout/payment processing, and additional analytics remain in active development. Voxera is not certified for governmental, legally regulated, or high-stakes elections. Poll and survey responses and discussion comments are linked to signed-in accounts and must not be presented as anonymous. The eligibility roster is a point-in-time snapshot; no ballot or anonymity protocol is provided.

## Start locally

Requirements: Python 3.12+ and Node.js 20.19+.

### Django API

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py runserver
```

The API is available at `http://127.0.0.1:8000/api/v1/`. If `backend/venv` is unavailable:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
```

### React app

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Vite proxies `/api` requests to Django. Open the local URL printed by Vite.
After publishing a poll, copy its direct link from the share dialog. Public links open the selected poll; private polls remain limited to workspace members. Respondents must sign in, and local development links are only reachable from devices that can access your development server.
In local development, email verification and password-reset links are printed by Django's console email backend. Configure SMTP for Docker/self-hosted deployments so these messages reach users.

## Run with PostgreSQL and Docker

1. Copy `.env.example` to `.env`.
2. Set `DJANGO_SECRET_KEY` to a unique, random secret, `MFA_ENCRYPTION_KEY` to a generated Fernet key, `FRONTEND_BASE_URL` to the public frontend origin, SMTP host/credentials/sender, and `POSTGRES_PASSWORD` to unique values. Never commit `.env`. Generate the MFA key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and keep it stable across deployments; losing or rotating it prevents decryption of existing authenticator secrets.
3. Start the stack with `docker compose up --build`.
4. Open `http://localhost:8080`; Django admin is at `/admin/`.

The bundled Compose configuration is a local/self-hosted starting point and exposes HTTP. Production deployments must terminate HTTPS at a trusted reverse proxy, set `DJANGO_SECURE_SSL_REDIRECT=true`, use secrets supplied by the deployment platform, restrict `DJANGO_ALLOWED_HOSTS`, and review the deployment checklist, privacy obligations, retention policy, and election security design before accepting real election ballots.

To send notification emails, set `NOTIFICATIONS_EMAIL_ENABLED=true`, configure SMTP credentials and `DEFAULT_FROM_EMAIL`, then schedule a single backend worker to run `python manage.py send_notification_emails`. Delivery failures are retained and retried up to five times; notifications continue to work in-app if email delivery is unavailable.

Subscription plans are configured in Django admin under **Subscription plans**, then assigned to organizations under **Organization subscriptions**. Unset caps are unlimited; organizations without a plan have no configured caps. The subscription panel and API expose plan and usage to organization owners/admins. There is no checkout, recurring charge, or payment-provider integration.

New accounts must verify their email and enroll a TOTP authenticator before using protected application APIs. Verification links expire after 24 hours; password-reset links expire after 30 minutes and revoke existing API tokens. Login issues a short-lived challenge, and successful MFA enrollment rotates the account's API token. Save the single-use recovery codes when they are shown. Local development derives an MFA encryption key from `DJANGO_SECRET_KEY`; production Compose requires SMTP, a public frontend URL, and the dedicated key above.

## Tests and checks

```powershell
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

```powershell
cd frontend
npm ci
npm run build
```

GitHub Actions runs the Django suite against PostgreSQL and builds the React app for pushes and pull requests.

## API overview

- `POST /api/v1/auth/register/`, `POST /api/v1/auth/login/`, `POST /api/v1/auth/logout/`, `GET|PATCH /api/v1/auth/me/`
- `POST /api/v1/auth/email/verification/`, `POST /api/v1/auth/email/verification/resend/`, `POST /api/v1/auth/password/reset/request/`, `POST /api/v1/auth/password/reset/confirm/`
- `GET|POST /api/v1/organizations/`; `GET|PATCH|DELETE /api/v1/organizations/{slug}/`; `GET|POST /api/v1/organizations/{slug}/members/`; `GET /api/v1/organizations/{slug}/analytics/`; `GET /api/v1/organizations/{slug}/subscription/` (owner/admin only)
- `GET /api/v1/organizations/applications/` (applicant's requests; staff see pending requests); `POST /api/v1/organizations/{slug}/review/` (staff only, requires decision and reason)
- `GET|POST /api/v1/polls/`; `GET|PATCH|DELETE /api/v1/polls/{id}/`; `POST /api/v1/polls/{id}/responses/`; `GET /api/v1/polls/{id}/results/`
- `GET|POST /api/v1/polls/{id}/comments/`; `PATCH /api/v1/polls/{id}/comments/{comment_id}/moderate/`
- `GET|POST /api/v1/surveys/`; `GET|PATCH|DELETE /api/v1/surveys/{id}/`; `POST /api/v1/surveys/{id}/responses/`; `GET /api/v1/surveys/{id}/report/`; `GET /api/v1/surveys/{id}/export-report/`
- `GET|POST /api/v1/surveys/{id}/comments/`; `PATCH /api/v1/surveys/{id}/comments/{comment_id}/moderate/`
- `GET /api/v1/polls/{id}/export-results/`
- `GET /api/v1/health/` (database connectivity check)
- `GET /api/v1/notifications/`; `GET /api/v1/notifications/unread-count/`; `POST /api/v1/notifications/{id}/read/`; `POST /api/v1/notifications/read-all/` (authenticated recipient only)
- `GET|POST /api/v1/elections/`; `GET|PATCH|DELETE /api/v1/elections/{id}/`; `POST /api/v1/elections/{id}/open-nominations/`; `POST /api/v1/elections/{id}/nominate/`; `POST /api/v1/elections/{id}/close-nominations/`; `POST /api/v1/elections/{id}/cancel/`

Protected API endpoints use DRF token authentication. Public activity discovery intentionally returns only published public activities; private activity and reporting access is explicitly scoped to authorized organization members and managers.
