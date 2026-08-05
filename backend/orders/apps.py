from django.apps import AppConfig


class OrdersConfig(AppConfig):
    """Sales orders — commercial intent (M3_Design_Review §1).

    An order records what was agreed. It changes no physical fact and no financial
    fact: no module here writes a StockMovement (M3-6) or a ledger entry.
    """

    name = "orders"
    verbose_name = "Orders"
