"""Shared settings.

Environment-specific values come only from environment variables and are parsed and
validated here, at startup (FD-11). A missing required variable must fail the boot,
not surface hours later as a corrupted invoice.
"""

from __future__ import annotations

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # -> backend/
REPO_ROOT = BASE_DIR.parent

env = environ.Env()

# --------------------------------------------------------------------------- core
DISTRICORE_ENV = env.str("DISTRICORE_ENV", default="development")
DEBUG = env.bool("DISTRICORE_DEBUG", default=False)
SECRET_KEY = env.str("DISTRICORE_SECRET_KEY")
ALLOWED_HOSTS = env.list("DISTRICORE_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("DISTRICORE_CSRF_TRUSTED_ORIGINS", default=[])

# --------------------------------------------------------------------------- apps
# django.contrib.admin is deliberately absent (ADR-0003): it writes directly through
# the ORM, bypassing services.py (N-01) and able to mutate audit rows (N-04).
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "axes",
    "core.apps.CoreConfig",
    "identity.apps.IdentityConfig",
    "catalogue.apps.CatalogueConfig",
    "customers.apps.CustomersConfig",
    "inventory.apps.InventoryConfig",
    "ledger.apps.LedgerConfig",
    "pricing.apps.PricingConfig",
    "orders.apps.OrdersConfig",
    "fulfilment.apps.FulfilmentConfig",
    "field.apps.FieldConfig",
    "billing.apps.BillingConfig",
    "receivables.apps.ReceivablesConfig",
    "sync.apps.SyncConfig",
    "webadmin.apps.WebAdminConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "webadmin" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------- database
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False  # transactions are explicit, in services
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DISTRICORE_DB_CONN_MAX_AGE", default=60)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"  # DBD-01

# --------------------------------------------------------------------------- identity
# I-01: irreversible. Must be set before the first `makemigrations` ever runs.
AUTH_USER_MODEL = "identity.User"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",  # must be first (FR-IAM-004)
    "identity.backends.PhoneBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",  # FR-IAM-002
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# django-axes — login rate limiting (FR-IAM-004)
AXES_FAILURE_LIMIT = 10
AXES_COOLOFF_TIME = 0.25  # 15 minutes
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = None

# --------------------------------------------------------------------------- i18n
LANGUAGE_CODE = "en-in"
LANGUAGES = [("hi", "हिन्दी"), ("en", "English")]
TIME_ZONE = "UTC"  # N-08: storage and computation in UTC, always
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- static / media
STATIC_URL = "/static/"
STATIC_ROOT = REPO_ROOT / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_ROOT = Path(env.str("DISTRICORE_MEDIA_ROOT", default=str(REPO_ROOT / "media")))
MEDIA_URL = ""  # media is NEVER served by URL — only through an authorised view (04 T-25)
MAX_UPLOAD_BYTES = env.int("DISTRICORE_MAX_UPLOAD_MB", default=5) * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES

# --------------------------------------------------------------------------- API
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "EXCEPTION_HANDLER": "api.v1.exception_handler.problem_detail_handler",
    "DEFAULT_PAGINATION_CLASS": "api.v1.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    # DRF accepts only second|minute|hour|day (it reads period[0] -> s/m/h/d).
    # "3/15min" parses '1' and raises KeyError. These are the coarse PER-IP backstops
    # from 05 §13; the security-meaningful PER-PHONE limits live elsewhere:
    #   * OTP requests  -> identity.services.request_otp (3 per phone / 15 min)
    #   * OTP attempts  -> OtpRequest.attempt_count (5 per code)
    #   * Password login-> django-axes (10 per phone / 15 min, AXES_* above)
    "DEFAULT_THROTTLE_RATES": {
        "otp_request": "20/hour",  # 05 §13: 20 per IP per hour
        "otp_verify": "60/hour",
        "login": "40/hour",
        "sync_push": "60/hour",
        "media_upload": "100/hour",
        "user": "1000/hour",
    },
    "COERCE_DECIMAL_TO_STRING": True,  # AD-02: money is a decimal string, never a float
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%SZ",  # AD-06
    "UNAUTHENTICATED_USER": None,
}

_ACCESS_MIN = env.int("DISTRICORE_ACCESS_TOKEN_MINUTES", default=30)
_REFRESH_DAYS = env.int("DISTRICORE_REFRESH_TOKEN_DAYS", default=30)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": __import__("datetime").timedelta(minutes=_ACCESS_MIN),
    "REFRESH_TOKEN_LIFETIME": __import__("datetime").timedelta(days=_REFRESH_DAYS),
    "ROTATE_REFRESH_TOKENS": True,  # 05 §7.1
    "BLACKLIST_AFTER_ROTATION": True,  # reuse detection
    "UPDATE_LAST_LOGIN": False,  # done explicitly in services, audited
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "sub",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "TOKEN_OBTAIN_SERIALIZER": "api.v1.serializers.NoopSerializer",
}

# --------------------------------------------------------------------------- OTP
OTP_LENGTH = env.int("DISTRICORE_OTP_LENGTH", default=6)
OTP_EXPIRY_MINUTES = env.int("DISTRICORE_OTP_EXPIRY_MINUTES", default=10)
OTP_MAX_ATTEMPTS = env.int("DISTRICORE_OTP_MAX_ATTEMPTS", default=5)
OTP_RETENTION_HOURS = env.int("DISTRICORE_OTP_RETENTION_HOURS", default=24)

SMS_PROVIDER = env.str("DISTRICORE_SMS_PROVIDER", default="console")
SMS_API_KEY = env.str("DISTRICORE_SMS_API_KEY", default="")
SMS_SENDER_ID = env.str("DISTRICORE_SMS_SENDER_ID", default="")
SMS_TEMPLATE_ID = env.str("DISTRICORE_SMS_TEMPLATE_ID", default="")

# --------------------------------------------------------------------------- health
BACKUP_STAMP_PATH = env.str("DISTRICORE_BACKUP_STAMP_PATH", default="/srv/backups/last_success")
BACKUP_MAX_AGE_HOURS = env.int("DISTRICORE_BACKUP_MAX_AGE_HOURS", default=26)
DISK_WARN_PERCENT = env.int("DISTRICORE_DISK_WARN_PERCENT", default=85)

# --------------------------------------------------------------------------- logging
LOG_LEVEL = env.str("DISTRICORE_LOG_LEVEL", default="INFO")
LOG_FORMAT = env.str("DISTRICORE_LOG_FORMAT", default="console")

from config.logging import build_logging_config  # noqa: E402

LOGGING = build_logging_config(LOG_LEVEL, LOG_FORMAT)

# --------------------------------------------------------------------------- misc
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"
