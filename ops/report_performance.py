"""FR-RPT-015 — measure every report against five years of history (M7 §10.1).

**No report in M7 may be declared done on the strength of a fast test-suite run**, which
exercises tens of rows. NFR-PER-003's stated method is a load test against a synthesised
five-year dataset, and this is that dataset.

Run inside the Docker stack, against a scratch database — it writes tens of thousands of
immutable financial documents and must never be pointed at anything real::

    docker compose -f docker/compose.dev.yml run --rm tools \\
        python ops/report_performance.py

Timings are reported **per report**, not as an aggregate. One "reports are fast" number
hides the one that is not, and §10.1 names two suspects in advance:

* **receivables** — the only report whose figures come from a row-by-row Python walk (§5A)
  rather than a database aggregate. It walks every ledger entry for every visible customer.
* **top-customers** — raised by independent review (§17.2). It aggregates across `invoice`
  and `credit_note`, groups by customer and orders by the result, and the two candidate
  indexes both lead on `customer` rather than on the date.

If a report breaches, the fix is an index or a domain optimisation recorded with the
measurement that justified it (§7) — **never a reporting shortcut and never a stored
aggregate** (M7-4).
"""

from __future__ import annotations

import os
import random
import sys
import time as clock
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django

django.setup()

from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from billing.models import CreditNote, Invoice, InvoiceLine  # noqa: E402
from catalogue.models import Product  # noqa: E402
from customers.models import Customer, Zone  # noqa: E402
from identity.models import User  # noqa: E402
from inventory.models import ReasonCode, StockLocation, StockLot, StockMovement  # noqa: E402
from ledger.models import CustomerLedgerEntry  # noqa: E402
from orders.models import SalesOrder  # noqa: E402
from reporting import selectors as reports  # noqa: E402

# --- DR-8, scaled to five years of retained history (NFR-4, FR-RPT-015) ----------------
# 10,000 order lines per day is the envelope's *peak*; the sustained figure that produces
# ~73,000 invoices over five years is the one M7 §10.1 sized against.
YEARS = 5
INVOICES = 73_000
LINES_PER_INVOICE = 4
CUSTOMERS = 1_000
PRODUCTS = 500
MOVEMENTS = 60_000
CREDIT_NOTE_RATE = 0.03
PAYMENTS_PER_CUSTOMER = 30
BUDGET_SECONDS = 10.0

SEED = 20260808


def _log(message: str) -> None:
    print(message, flush=True)


def _bulk(model, rows, label):
    _log(f"    {label}: {len(rows):,}")
    model.objects.bulk_create(rows, batch_size=2_000)


@transaction.atomic
def synthesise() -> User:
    """Write the dataset directly, bypassing the services.

    Deliberate: the services enforce credit, stock and numbering rules whose cost is not
    what is being measured, and running 73,000 orders through them would take hours. The
    *shape* of the data is what the query planner sees, and the shape is faithful.

    This is a measurement fixture, not a fixture the suite may reuse — writing financial
    documents without their services is exactly what N-01 forbids in production code.
    """
    # S311: this is a deterministic measurement fixture, not a security context. The seed
    # is fixed so two runs measure the same shape and can be compared to each other.
    rng = random.Random(SEED)  # noqa: S311
    today = date.today()
    start = today - timedelta(days=365 * YEARS)

    owner = User.objects.filter(roles__code="OWNER").first()
    if owner is None:
        raise SystemExit("Seed an OWNER before running this harness.")

    zone = Zone.objects.first() or Zone.objects.create(name="Perf", city="Patna", pin_code="800001")
    location = StockLocation.objects.get(is_default=True)
    reasons = list(ReasonCode.objects.filter(is_active=True))

    _log("--> customers and products")
    customers = [
        Customer(code=f"PERF-C-{n:05d}", shop_name=f"Perf Shop {n}", zone=zone,
                 phone=f"+9170000{n:05d}", billing_address="Perf Bazaar")
        for n in range(CUSTOMERS)
    ]
    _bulk(Customer, customers, "customers")
    customers = list(Customer.objects.filter(code__startswith="PERF-C-"))

    products = [
        Product(code=f"PERF-P-{n:05d}", name=f"Perf Product {n}",
                selling_price=Decimal("100.00"), tax_rate_percent=Decimal("18.00"))
        for n in range(PRODUCTS)
    ]
    _bulk(Product, products, "products")
    products = list(Product.objects.filter(code__startswith="PERF-P-"))
    lots = {
        product.pk: StockLot.objects.get_or_create(product=product, code="DEFAULT")[0]
        for product in products
    }

    _log("--> stock movements")
    _bulk(
        StockMovement,
        [
            StockMovement(
                product=(product := rng.choice(products)),
                location=location,
                lot=lots[product.pk],
                movement_type=StockMovement.Type.ADJUSTMENT,
                quantity=Decimal(rng.randint(-50, 50)),
                reason_code=rng.choice(reasons) if reasons else None,
                occurred_at=timezone.make_aware(
                    datetime.combine(
                        start + timedelta(days=rng.randint(0, 365 * YEARS)), time.min
                    )
                ),
                created_by=owner,
            )
            for _ in range(MOVEMENTS)
        ],
        "movements",
    )

    _log("--> orders, invoices, lines, ledger")
    series = Invoice.objects.first()
    if series is None:
        raise SystemExit("Issue one real invoice first so a NumberSeries exists.")

    orders, invoices = [], []
    for n in range(INVOICES):
        customer = rng.choice(customers)
        day = start + timedelta(days=rng.randint(0, 365 * YEARS))
        orders.append(
            SalesOrder(
                order_number=f"PERF-O-{n:06d}", customer=customer, order_date=day,
                status=SalesOrder.Status.DELIVERED, source=SalesOrder.Source.WEB,
                assigned_user=owner, created_by=owner,
                subtotal_amount=Decimal("400.00"), total_amount=Decimal("472.00"),
            )
        )
    _bulk(SalesOrder, orders, "orders")
    orders = list(SalesOrder.objects.filter(order_number__startswith="PERF-O-"))

    for n, order in enumerate(orders):
        invoices.append(
            Invoice(
                invoice_number=f"PERF-INV-{n:06d}", number_series=series.number_series,
                sales_order=order, customer=order.customer, invoice_date=order.order_date,
                financial_year=f"{order.order_date.year}-{(order.order_date.year + 1) % 100:02d}",
                status=Invoice.Status.ISSUED, seller_legal_name="Perf", buyer_name="Perf",
                subtotal_amount=Decimal("400.00"), taxable_amount=Decimal("400.00"),
                cgst_amount=Decimal("36.00"), sgst_amount=Decimal("36.00"),
                total_amount=Decimal("472.00"), issued_by=owner,
            )
        )
    _bulk(Invoice, invoices, "invoices")
    invoices = list(Invoice.objects.filter(invoice_number__startswith="PERF-INV-"))

    _bulk(
        InvoiceLine,
        [
            InvoiceLine(
                invoice=invoice, line_number=index,
                product=(product := rng.choice(products)),
                product_code=product.code, product_name=product.name,
                quantity=Decimal("1.000"), unit_name="PCS", unit_price=Decimal("100.00"),
                taxable_amount=Decimal("100.00"), tax_rate_percent=Decimal("18.00"),
                cgst_amount=Decimal("9.00"), sgst_amount=Decimal("9.00"),
                line_total=Decimal("118.00"),
            )
            for invoice in invoices
            for index in range(1, LINES_PER_INVOICE + 1)
        ],
        "invoice lines",
    )

    _bulk(
        CustomerLedgerEntry,
        [
            CustomerLedgerEntry(
                customer=invoice.customer, entry_date=invoice.invoice_date,
                entry_type=CustomerLedgerEntry.Type.INVOICE, amount=Decimal("472.00"),
                narration=invoice.invoice_number, source_document_type="INVOICE",
                source_document_id=invoice.pk, created_by=owner,
            )
            for invoice in invoices
        ],
        "ledger entries",
    )

    _log("--> credit notes")
    credited = rng.sample(invoices, int(len(invoices) * CREDIT_NOTE_RATE))
    _bulk(
        CreditNote,
        [
            CreditNote(
                credit_note_number=f"PERF-CN-{n:06d}", number_series=series.number_series,
                invoice=invoice, customer=invoice.customer,
                credit_note_date=invoice.invoice_date + timedelta(days=rng.randint(0, 40)),
                financial_year=invoice.financial_year, reason="Perf",
                reason_code=rng.choice(reasons) if reasons and n % 3 else None,
                seller_legal_name="Perf", buyer_name="Perf",
                subtotal_amount=Decimal("100.00"), taxable_amount=Decimal("100.00"),
                cgst_amount=Decimal("9.00"), sgst_amount=Decimal("9.00"),
                total_amount=Decimal("118.00"), issued_by=owner,
            )
            for n, invoice in enumerate(credited)
        ],
        "credit notes",
    )

    _log("--> payment ledger entries")
    # **The receivables walk reads the ledger, not the payment table** (§5A), so PAYMENT
    # entries are what actually stress the named suspect. Without them the walk has nothing
    # to settle, every invoice stays fully open, and the measurement flatters itself.
    #
    # Amounts are negative: `ck_cle_sign` encodes the accounting direction in the database,
    # so a positive payment would be refused by the constraint rather than by a service.
    _bulk(
        CustomerLedgerEntry,
        [
            CustomerLedgerEntry(
                customer=customer,
                entry_date=start + timedelta(days=rng.randint(0, 365 * YEARS)),
                entry_type=CustomerLedgerEntry.Type.PAYMENT,
                amount=Decimal("-472.00"),
                narration=f"PERF-PAY-{customer.pk}-{n}",
                created_by=owner,
            )
            for customer in customers
            for n in range(PAYMENTS_PER_CUSTOMER)
        ],
        "payment entries",
    )
    return owner


def measure(owner: User) -> int:
    """Time every report individually. Returns the number that breached the budget."""
    today = date.today()
    year = (today - timedelta(days=365), today)
    five = (today - timedelta(days=365 * YEARS), today)

    cases = [
        (
            "sales (1y, day)",
            lambda: reports.sales_report(owner, date_from=year[0], date_to=year[1]),
        ),
        (
            "sales (5y, day)",
            lambda: reports.sales_report(owner, date_from=five[0], date_to=five[1]),
        ),
        (
            "sales (5y, product)",
            lambda: reports.sales_report(
                owner, date_from=five[0], date_to=five[1], group_by="product"
            ),
        ),
        (
            "sales (5y, customer)",
            lambda: reports.sales_report(
                owner, date_from=five[0], date_to=five[1], group_by="customer"
            ),
        ),
        ("stock position", lambda: reports.stock_position(owner)),
        (
            "stock variance (5y)",
            lambda: reports.stock_variance(owner, date_from=five[0], date_to=five[1]),
        ),
        (
            "returns (5y)",
            lambda: reports.returns_report(owner, date_from=five[0], date_to=five[1]),
        ),
        ("receivables ageing", lambda: reports.receivables_ageing(owner)),
        (
            "top customers (5y)",
            lambda: reports.top_customers(owner, date_from=five[0], date_to=five[1]),
        ),
        (
            "order pipeline (5y)",
            lambda: reports.order_pipeline(owner, date_from=five[0], date_to=five[1]),
        ),
        ("dashboard", lambda: reports.dashboard(owner)),
    ]

    _log("")
    _log(f"{'report':<26} {'seconds':>9}  {'rows':>7}  result")
    _log("-" * 62)
    breaches = 0
    for label, build in cases:
        started = clock.perf_counter()
        result = build()
        elapsed = clock.perf_counter() - started
        rows = len(getattr(result, "rows", getattr(result, "metrics", ())))
        verdict = "OK" if elapsed < BUDGET_SECONDS else "BREACH"
        breaches += verdict == "BREACH"
        _log(f"{label:<26} {elapsed:>9.3f}  {rows:>7}  {verdict}")
    _log("-" * 62)
    _log(f"FR-RPT-015 budget {BUDGET_SECONDS:.0f}s per report — {breaches} breach(es)")
    return breaches


if __name__ == "__main__":
    if Invoice.objects.filter(invoice_number__startswith="PERF-INV-").exists():
        _log("Dataset already present; measuring without regenerating.")
        actor = User.objects.filter(roles__code="OWNER").first()
    else:
        started = clock.perf_counter()
        actor = synthesise()
        _log(f"--> dataset built in {clock.perf_counter() - started:.1f}s")
    sys.exit(1 if measure(actor) else 0)
