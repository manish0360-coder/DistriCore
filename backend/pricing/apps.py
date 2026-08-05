from django.apps import AppConfig


class PricingConfig(AppConfig):
    """Price resolution and the bounded manual discount (03 §2.1).

    Owns no tables. Edition 1 pricing is one price list — `product.selling_price` — so
    this module exists for the rule, not the data: every surface must resolve a price
    through the same function or PO-6 is unverifiable.
    """

    name = "pricing"
    verbose_name = "Pricing"
