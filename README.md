# Voxera

Voxera is a multi-tenant voting and opinion platform built with Django REST Framework and React/TypeScript.

## What works today

- Email-based account registration, sign-in, sign-out, and profile editing.
- Organization workspaces with owner, administrator, creator, and member roles.
- Organization dashboards with member, poll, survey, and response totals (owners and administrators only).
- Public and restricted opinion polls, one response per signed-in account, and aggregate results.
- Surveys with single- and multi-choice, text, and 1–5 rating questions; response collection; and manager-only reports.
- CSV downloads for poll results and manager-authorized survey reports, with spreadsheet formula injection protection.
- Responsive discovery and management interfaces.
- PostgreSQL support, production-aware Django settings, Nginx routing, Docker Compose, and CI for PostgreSQL, Django tests, and the React build.

Formal organizational elections, anonymous ballots, discussions, notification delivery, subscriptions, and advanced analytics remain in active development. Voxera is not certified for governmental, legally regulated, or high-stakes elections. The current poll and survey response model links responses to signed-in accounts and must not be presented as anonymous.

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

## Run with PostgreSQL and Docker

1. Copy `.env.example` to `.env`.
2. Set `DJANGO_SECRET_KEY` to a unique, random secret and `POSTGRES_PASSWORD` to a unique password. Never commit `.env`.
3. Start the stack with `docker compose up --build`.
4. Open `http://localhost:8080`; Django admin is at `/admin/`.

The bundled Compose configuration is a local/self-hosted starting point and exposes HTTP. Production deployments must terminate HTTPS at a trusted reverse proxy, set `DJANGO_SECURE_SSL_REDIRECT=true`, use secrets supplied by the deployment platform, restrict `DJANGO_ALLOWED_HOSTS`, and review the deployment checklist, privacy obligations, retention policy, and election security design before accepting real election ballots.

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
- `GET|POST /api/v1/organizations/`; `GET|PATCH|DELETE /api/v1/organizations/{slug}/`; `GET|POST /api/v1/organizations/{slug}/members/`; `GET /api/v1/organizations/{slug}/analytics/` (owner/admin only)
- `GET|POST /api/v1/polls/`; `GET|PATCH|DELETE /api/v1/polls/{id}/`; `POST /api/v1/polls/{id}/responses/`; `GET /api/v1/polls/{id}/results/`
- `GET|POST /api/v1/surveys/`; `GET|PATCH|DELETE /api/v1/surveys/{id}/`; `POST /api/v1/surveys/{id}/responses/`; `GET /api/v1/surveys/{id}/report/`; `GET /api/v1/surveys/{id}/export-report/`
- `GET /api/v1/polls/{id}/export-results/`
- `GET /api/v1/health/` (database connectivity check)

Protected API endpoints use DRF token authentication. Public activity discovery intentionally returns only published public activities; private activity and reporting access is explicitly scoped to authorized organization members and managers.
