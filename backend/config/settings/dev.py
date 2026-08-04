"""Development settings. Never used in production."""

from config.settings.base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
AXES_ENABLED = True
