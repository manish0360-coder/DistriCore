from django.apps import AppConfig


class ReceivablesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "receivables"
    verbose_name = "Receivables"

    def ready(self) -> None:
        # R-2: register Payment as a permitted ledger source document. Registration lives
        # with the model's own module so `ledger` imports nothing from above it — the
        # same pattern `billing` and `fulfilment` follow.
        from receivables import registry  # noqa: F401
