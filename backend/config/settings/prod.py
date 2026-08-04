"""Production settings.

A misconfigured production instance must refuse to start rather than run insecurely
(00 §10.1). These assertions run at import.
"""

from config.settings.base import *

DEBUG = False

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 60 * 60 * 12

# --- boot-time preconditions ------------------------------------------------
_errors = []

if DEBUG:
    _errors.append("DISTRICORE_DEBUG must be false in production")
if not SECRET_KEY or SECRET_KEY.startswith("dev-insecure"):
    _errors.append("DISTRICORE_SECRET_KEY is unset or still the development default")
if len(SECRET_KEY) < 50:
    _errors.append("DISTRICORE_SECRET_KEY must be at least 50 characters")
if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["*"]:
    _errors.append("DISTRICORE_ALLOWED_HOSTS must be an explicit list in production")
if SMS_PROVIDER == "console":
    _errors.append("DISTRICORE_SMS_PROVIDER must not be 'console' in production")
if LOG_FORMAT != "json":
    _errors.append("DISTRICORE_LOG_FORMAT must be 'json' in production (00 §12)")

if _errors:
    raise RuntimeError(
        "Refusing to start — production configuration is unsafe:\n  - " + "\n  - ".join(_errors)
    )

# --- monitoring (00 §13) ----------------------------------------------------
_SENTRY_DSN = env.str("SENTRY_DSN", default="")
if _SENTRY_DSN:  # pragma: no cover
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=env.float("DISTRICORE_SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        send_default_pii=False,  # SEC-3: never ship user data to a third party
        environment=DISTRICORE_ENV,
    )
