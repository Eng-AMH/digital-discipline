"""
Django settings for the Digital Discipline Platform backend.

Per docs/01-REQUIREMENTS-AND-ARCHITECTURE.md §0.3: no hardcoded secrets. Every
sensitive value is read from the environment, with .env.example documenting what's
required. This file is safe to commit; a real .env is not.
"""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(key, default=None, required=False):
    value = os.environ.get(key, default)
    if required and value is None:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. See .env.example."
        )
    return value


def env_bool(key, default=False):
    val = os.environ.get(key)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-insecure-key-DO-NOT-USE-IN-PRODUCTION")
DEBUG = env_bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")

AUTH_USER_MODEL = "accounts.User"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_celery_beat",
    "django_filters",
    "drf_spectacular",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "channels",
    # Local apps — order matters for migration dependency resolution readability,
    # not for correctness (Django resolves FK dependencies regardless of order).
    "apps.core",
    "apps.accounts",
    "apps.devices",
    "apps.policies",
    "apps.gamification",
    "apps.social",
    "apps.monetization",
    "apps.ai_coach",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database — PostgreSQL per architecture doc §12. SQLite fallback ONLY for
# environments (like this one) with no Postgres server available, so migrations
# can still be authored/checked; docker-compose.yml uses real Postgres.
# ---------------------------------------------------------------------------
if env("DATABASE_URL"):
    import dj_database_url  # noqa — only imported if actually configured

    DATABASES = {"default": dj_database_url.parse(env("DATABASE_URL"))}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# CORS — web frontend origin(s), env-driven since this differs per deploy env
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS", default="http://localhost:3000").split(",")

# ---------------------------------------------------------------------------
# DRF + JWT — §48 Security: short-lived access token, rotating revocable refresh
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    # Registers apps.policies.views.policy_exception_handler, which turns
    # ValidationErrorResponse (raised when a weekly-lock guard or plan-tier
    # ceiling blocks a policy change) into a clean 403 with a message, and falls
    # through to DRF's default handler for everything else.
    "EXCEPTION_HANDLER": "apps.policies.views.policy_exception_handler",
    # §39 Anti-Abuse: the three endpoint families the blueprint explicitly flags
    # (unlock, referral, rewarded-ad) get their own scoped throttle rates —
    # everything else uses generic per-user rates. See apps/*/views.py for which
    # views declare which throttle_scope.
    "DEFAULT_THROTTLE_RATES": {
        "unlock": "20/hour",
        "referral": "10/hour",
        "rewarded_ad": "15/hour",
        "auth": "10/minute",
        "device_heartbeat": "120/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

INSTALLED_APPS.append("rest_framework_simplejwt.token_blacklist")

SPECTACULAR_SETTINGS = {
    "TITLE": "Digital Discipline Platform API",
    "DESCRIPTION": "Backend API — see docs/01-REQUIREMENTS-AND-ARCHITECTURE.md for design rationale.",
    "VERSION": "1.0.0",
}

# ---------------------------------------------------------------------------
# Celery + Redis — §12/§54: streak resets, weekly unlocks, AI reports,
# achievement evaluation, referral qualification checks all run here.
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="").strip()
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
if REDIS_URL:
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
else:
    # Free-tier fallback: scheduled jobs are run synchronously by the management
    # command / GitHub Actions, so Redis is optional for the MVP deployment.
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

# Channels: Redis is preferred when configured; in-memory is enough for a
# single free web instance and keeps the backend deployable without Redis.
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

# ---------------------------------------------------------------------------
# Unlock token / device signing — architecture doc §5.2/§5.3. This is the
# SERVER's Ed25519 private key (base64-encoded raw 32 bytes). Generate with:
#   python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; \
#              import base64; k=Ed25519PrivateKey.generate(); \
#              print(base64.b64encode(k.private_bytes_raw()).decode())"
# NEVER commit a real value — .env.example documents this as required.
# ---------------------------------------------------------------------------
UNLOCK_TOKEN_SIGNING_KEY_B64 = env(
    "UNLOCK_TOKEN_SIGNING_KEY_B64",
    default="4NHXV3yEbBWTQrVLQq4b0X6bfR33nmcJ9Xz9vQ0ZbUE=",  # dev-only fixed key, DO NOT use in prod
)

# ---------------------------------------------------------------------------
# AI Coach provider — architecture doc §6. 'mock' ships by default since no
# LLM credentials were supplied in this build environment.
# ---------------------------------------------------------------------------
AI_COACH_PROVIDER = env("AI_COACH_PROVIDER", default="mock")

# ---------------------------------------------------------------------------
# Payment providers — architecture doc §0.2/§7. Webhook signing secrets are
# read here but the webhook handlers themselves document that verification
# cannot be tested without real provider credentials.
# ---------------------------------------------------------------------------
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
GOOGLE_PLAY_SERVICE_ACCOUNT_JSON = env("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", default="")
APPLE_IAP_SHARED_SECRET = env("APPLE_IAP_SHARED_SECRET", default="")

# ---------------------------------------------------------------------------
# Push notifications — Android FCM. Real send call documented as integration
# point in apps.notifications.services (architecture doc §2, §44).
# ---------------------------------------------------------------------------
FCM_SERVER_KEY = env("FCM_SERVER_KEY", default="")

# ---------------------------------------------------------------------------
# Production/security helpers
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
X_FRAME_OPTIONS = "DENY"

CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in env("CSRF_TRUSTED_ORIGINS", default="").split(",") if origin.strip()
]
