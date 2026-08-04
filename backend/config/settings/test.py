"""Test settings.

Fast hashing and disabled rate limiting, because a test suite that spends its time on
Argon2 is a test suite that stops being run. Everything security-relevant is still
exercised by the adversarial suite against the real code paths.

Selected by ``--ds=config.settings.test`` in pyproject.toml, which overrides the
``DJANGO_SETTINGS_MODULE`` that compose.dev.yml exports. Without that flag the suite
runs against DEV settings, which is exactly what broke the first test stage.
"""

from config.settings.base import *

DEBUG = False
ALLOWED_HOSTS = ["*", "testserver"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AXES_ENABLED = False

# The in-memory SMS double. ConsoleSmsProvider deliberately has no ``sent`` list —
# see docs/M0_Completion_Report.md §5 for why that contract is canonical.
SMS_PROVIDER = "memory"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {},
    "root": {"handlers": []},
}

# Throttling OFF in tests. Emptying DEFAULT_THROTTLE_RATES is NOT the way to do it:
# DRF then raises ImproperlyConfigured("No default throttle rate set for '<scope>'")
# on every scoped view. Remove the classes instead.
#
# This does not weaken rate-limit coverage. The security-meaningful limits are:
#   * per-phone OTP requests -> identity.services.request_otp  (tested)
#   * per-code OTP attempts  -> OtpRequest.attempt_count        (tested)
#   * per-phone login        -> django-axes
# The DRF throttle is a per-IP backstop whose rates are class attributes read at
# import time, so a settings override inside a test would not take effect anyway.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}
