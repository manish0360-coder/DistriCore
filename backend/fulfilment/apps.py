from django.apps import AppConfig


class FulfilmentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fulfilment"
    verbose_name = "Fulfilment"

    def ready(self) -> None:
        # R-2: register Delivery as a permitted stock source document. Registration
        # lives with the model's own module so `inventory` imports nothing from above
        # it. This is the entry that closes TD-16 — the registry has been empty since
        # M2 and this is its first real member.
        from fulfilment import registry  # noqa: F401
