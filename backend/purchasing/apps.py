from django.apps import AppConfig


class PurchasingConfig(AppConfig):
    """Suppliers and the documents the distributor buys through (D5, FR-PUR-001…015)."""

    name = "purchasing"
    verbose_name = "Purchasing"

    def ready(self) -> None:
        # R-2: register GoodsReceipt as a permitted source document in BOTH the stock and
        # the ledger registries — it is the one document that moves stock and raises money
        # in the same act. Registration lives with the model's own module so neither
        # `inventory` nor `ledger` imports anything from above it.
        from purchasing import registry  # noqa: F401
