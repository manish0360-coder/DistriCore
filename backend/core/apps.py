from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Shared foundation: base models, audit, permissions, storage seam, field types.

    Owns nothing business-specific. Every other module depends on this one; this one
    depends on no other module (03 §2.1).

    Named ``core`` rather than ``platform`` — see ADR-0002.
    """

    name = "core"
    verbose_name = "Core"
