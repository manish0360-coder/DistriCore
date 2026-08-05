from django.apps import AppConfig


class InventoryConfig(AppConfig):
    """Stock.

    M1 creates only ReasonCode — the owner-maintained explanation attached to every
    stock adjustment (04 T-08). StockLocation, StockLot and StockMovement arrive in M2,
    where ADR-0004's CI gate enforces the structural columns.
    """

    name = "inventory"
    verbose_name = "Inventory"
