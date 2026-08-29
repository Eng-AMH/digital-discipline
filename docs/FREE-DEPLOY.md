# Free-first deployment

## Backend
- PostgreSQL: Neon Free (set `DATABASE_URL` on Render).
- Web service: Render Free using `backend/Dockerfile`.
- Start command: `daphne -b 0.0.0.0 -p 10000 config.asgi:application`.
- Health URL: `/health/`.
- Redis is optional; Channels falls back to in-memory for a single free instance.

## Scheduled jobs
Use the included `.github/workflows/scheduler.yml`. Add GitHub repository secrets:
- `DATABASE_URL`
- `DJANGO_SECRET_KEY`
- `UNLOCK_TOKEN_SIGNING_KEY_B64`

The scheduled workflow runs the Django management command `run_scheduled_tasks`.

## Android
Open `android/` in Android Studio or use the included GitHub Actions workflow. The app build now uses the Kotlin 2 Compose compiler plugin, includes a launcher icon, and has a release ProGuard file.

## Important
The VPN/domain-filter implementation still needs real-device networking tests before claiming production-grade website blocking.
