from django.apps import AppConfig


class WebAdminConfig(AppConfig):
    """Server-rendered admin for the owner (ADR-003).

    Not an API client: it calls services in-process. Both surfaces share the same
    service layer, so a rule cannot differ between them (BR-001).
    """

    name = "webadmin"
    verbose_name = "Web admin"
