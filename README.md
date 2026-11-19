# Digital Discipline Platform

An API-first digital self-management platform focused on intentional device use. The current repository scope centers on a Django REST backend and an Android enforcement agent, with asynchronous jobs and real-time services separated from the HTTP application.

> **Scope matters:** the web frontend, iOS agent, and live payment-provider wiring are documented as future/deferred work. The AI Coach configuration currently supports the mock provider. Docker Compose is included, but its full end-to-end startup is not claimed as verified in this repository's build notes.

## Current architecture

- **Backend API:** Django + Django REST Framework.
- **Authentication:** JWT support through SimpleJWT.
- **Persistence:** PostgreSQL for the containerized setup; SQLite is documented as a local development fallback.
- **Background work:** Celery worker and Celery Beat.
- **Cache and broker:** Redis.
- **Realtime:** Django Channels with an ASGI process served by Daphne.
- **Android:** Kotlin-based device agent intended to interact with Android usage and device-management APIs.
- **Security controls:** environment-based configuration and cryptographic signing for unlock/device-related tokens.

## Repository map

| Path | Purpose |
|---|---|
| `backend/` | Django backend, application modules, settings, requirements, and Dockerfile |
| `android/` | Android client/enforcement-agent code |
| `docs/01-REQUIREMENTS-AND-ARCHITECTURE.md` | Requirements, architecture, scope, and implementation decisions |
| `docs/03-REQUIREMENTS-AUDIT.md` | Requirements audit |
| `docs/FREE-DEPLOY.md` | Deployment notes |
| `docker-compose.yml` | Local orchestration for PostgreSQL, Redis, Django, ASGI, Celery worker, and Celery Beat |

## Local setup

### Prerequisites

- Docker and Docker Compose
- Git

### Configure the environment

From the repository root:

```bash
cp backend/.env.example .env
```

Edit `.env` and provide unique values for at least:

- `POSTGRES_PASSWORD`
- `DJANGO_SECRET_KEY`
- `UNLOCK_TOKEN_SIGNING_KEY_B64`

The environment template explains the expected formats and includes a key-generation example. Do not use development defaults or commit a real `.env` file.

### Start the services

```bash
docker compose up --build
```

After the containers are healthy, apply Django migrations:

```bash
docker compose exec backend python manage.py migrate
```

The Compose configuration is supplied as reviewed setup configuration; the project notes explicitly state that a complete Docker startup was not executed in the original build environment. Verify service startup and migrations on your machine before treating the stack as operational.

## Implementation boundaries

The architecture document is the source of truth for feature status. In particular:

- The backend and Android agent are the focus of this phase.
- A Next.js web frontend and an iOS agent are not implemented in this phase.
- Live Stripe/Play Billing/Apple IAP calls and AdMob/AdSense wiring require provider credentials and remain deferred.
- `AI_COACH_PROVIDER=mock` is the supported AI Coach setting documented for this build.
- Android code still needs to be built and tested on a suitable device/emulator.

## Engineering notes

This repository is structured around explicit service boundaries rather than a single all-in-one process. The separate ASGI service exists because WSGI does not serve WebSocket connections; Celery worker and beat processes handle asynchronous and scheduled work independently.

For detailed requirements, decisions, and status, start with [the architecture document](docs/01-REQUIREMENTS-AND-ARCHITECTURE.md).

## Maintainer

**Ammar Mostafa Hendam** — Full-Stack Development and AI-enabled systems.
