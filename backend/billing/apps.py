from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "billing"
    verbose_name = "Billing"

    def ready(self) -> None:
        # R-2: register Invoice and CreditNote as permitted ledger source documents.
        from billing import registry  # noqa: F401
