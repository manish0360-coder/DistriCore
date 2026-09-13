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

# **Static storage without a manifest, and this is not a convenience (M11.4).**
#
# `base.STATICFILES_STORAGE` is whitenoise's CompressedManifestStaticFilesStorage. Its
# `url()` consults a manifest that only `collectstatic` writes, and it is skipped entirely
# when `DEBUG` is true. Both other environments are therefore fine: dev never looks
# (DEBUG=True), production always has one (the entrypoint runs collectstatic).
#
# Tests are the single case that is neither: `DEBUG = False` above, and no collectstatic in
# the test container. Before M11.4 nothing noticed, because the product had **no static
# files at all** and no template called `{% static %}`. The moment `base.html` links one
# stylesheet, every one of the ~57 tests that renders a web-admin page would die on
# `ValueError: Missing staticfiles manifest entry for 'webadmin/districore.css'`.
#
# The fix is to test against storage that does not require a build artefact, rather than to
# build one during tests or to drop `{% static %}` and lose production cache-busting. A
# contract in `test_visual_system.py` asserts this override still exists.
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

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
