"""Performance and scalability evidence for V1 — five NFRs, one dataset.

**What this is.** The measurement instrument. It is not evidence; a run of it is. `02` §21
opens with the sentence this file exists to satisfy:

> *"A non-functional goal without a measurement method is not a requirement."*

**Three things are deliberately kept apart** and must not be conflated by any reader:

1. **This tooling** — code, versioned, reviewed, and provable by contracts in
   `backend/tests/adversarial/test_performance_harness.py`.
2. **Historical M7 evidence** — `docs/M7_Verification_Report.md` §13, measured 2026-08-09
   against a *different, smaller* dataset (1,000 customers, 500 products). Those numbers
   remain valid for what they measured and are never restated as current.
3. **Current authoritative evidence** — whatever the latest dated run recorded in
   `docs/M10.6_Performance_Report.md` says, and nothing else.

--------------------------------------------------------------------------------------
The five requirements, with thresholds taken verbatim from the frozen corpus
--------------------------------------------------------------------------------------

=========== ============================================================ ================
NFR         Threshold, as written                                        Stage here
=========== ============================================================ ================
PER-001     *"within 2 seconds at the 95th percentile under the DR-8     ``interactive``
            envelope"* (`02` §21.3; `01` NFR-3)
PER-003     *"within 10 seconds over five years of history"*             ``reports``
            (`02` §21.3, FR-RPT-015)
PER-005     *"re-measured against the five-year projected dataset        the run itself
            before each release"* — **Release gate** (`02` §21.3)
SCA-001     *"sustain the DR-8 three-year envelope without               ``reports`` +
            architectural change"* (`02` §21.4; envelope in `01` NFR-4)  ``interactive``
SCA-003     *"No query may degrade worse than linearly with retained     ``linearity``
            history"* (`02` §21.4)
=========== ============================================================ ================

**No threshold in this file is invented.** Each is a module constant carrying the document
that fixes it. Changing one is changing a frozen requirement, and a contract asserts the
values still match `02`.

--------------------------------------------------------------------------------------
Why the dataset grew, and why that is a correction rather than a change of goalposts
--------------------------------------------------------------------------------------

`01` NFR-4 states DR-8 as **≤10,000 active SKUs, ≤10,000 retailers, ≤100 concurrent
internal users, ≤50 synchronising devices, ≤10,000 order lines per day, ≤5 years retained
online.**

M7 sized this harness against FR-RPT-015's *history depth* and did that faithfully — but at
**1,000 customers and 500 products**, which is 10% and 5% of the envelope's master-data
ceilings. NFR-PER-001 and NFR-SCA-001 both say *"at the envelope"*, and
``receivables_ageing`` is a **per-customer Python walk** (M7 §5A) — the one report whose
cost is linear in the retailer count, and the one that breached at M7. Measuring it against
a tenth of the retailers and reporting *"sustains DR-8"* would be fabricated evidence.

So the ``dr8`` profile raises the two master-data dimensions to their stated ceilings. The
**transaction volume is left exactly as M7 sized it** — 73,000 invoices over five years —
because M7 recorded its reasoning for that figure (10,000 lines/day is the envelope's
*peak*, not its sustained rate) and this pass does not reopen it.

The ``m7`` profile reproduces the old shape, so the historical numbers stay comparable and
a regression can be distinguished from a re-scaling.

--------------------------------------------------------------------------------------
Running it
--------------------------------------------------------------------------------------

``make perf`` is the supported entry point. It expands to a run inside the Docker stack,
against a scratch database — this writes hundreds of thousands of immutable financial
documents and **must never be pointed at anything real**::

    docker compose -f docker/compose.yml -f docker/compose.dev.yml --env-file .env \\
        exec -T -w /app -e PYTHONPATH=/app/backend app \\
        python ops/report_performance.py --profile dr8 --json - > ops/perf-latest.json

Both compose files are required: the base one defines the services, the dev overlay sets
`DJANGO_SETTINGS_MODULE`. There is no separate `tools` service — quality tooling runs in
`app` with the project root as the working directory, exactly as `make verify` does.

**`--json -`, and the redirect is on the host.** `docker/compose.dev.yml` mounts
`../ops:/app/ops:ro`, deliberately, so stage-7 contracts can read this file — which means
the harness cannot write its own evidence next to itself from inside the container. The
document goes to stdout and the human log to stderr; the caller redirects. Relaxing the
read-only mount to make a reporting convenience work would trade a structural guarantee
for a filename.

Timings are reported **per operation**, never as an aggregate. One "it is fast" number hides
the one that is not, and M7 §10.1 named two suspects in advance:

* **receivables** — the only report whose figures come from a row-by-row Python walk (§5A)
  rather than a database aggregate. It walks every ledger entry for every visible customer.
* **top-customers** — raised by independent review (§17.2). It aggregates across `invoice`
  and `credit_note`, groups by customer and orders by the result, and the two candidate
  indexes both lead on `customer` rather than on the date.

If anything breaches, the fix is an index or a domain optimisation recorded with the
measurement that justified it (M7 §7) — **never a reporting shortcut, never a stored
aggregate (M7-4), and never a raised threshold.**
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys
import time as clock
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

#: **Nothing but the evidence document may reach the real stdout.**
#:
#: `config/logging.py` sends every application log line to stdout deliberately — `00` §12,
#: one JSON object per line, never a file inside a container — and that is right for the
#: application and is not changed here. It is wrong for a script whose stdout *is* a
#: machine-readable document: the first DR-8 run emitted
#:
#:     INFO     axes.apps: AXES: BEGIN version 6.5.2, blocking by username or ip_address
#:
#: above the opening brace, and `json.load` refused the file.
#:
#: Swapped **before** `django.setup()`, because `LOGGING` is applied during setup and
#: `axes` logs from `AppConfig.ready()` — a handler rebound afterwards would already be too
#: late. `ext://sys.stdout` in the logging config then resolves to this stderr object, so
#: every library that logs anywhere is captured, not just the one that was noticed.
_EVIDENCE_STREAM = sys.stdout
sys.stdout = sys.stderr

import django  # noqa: E402

django.setup()

# Pure, stdlib-only, and therefore importable by the contract suite — which is the whole
# reason the verdict mapping lives in its own module. See `ops/perf_verdicts.py`.
from perf_verdicts import StageResult, evaluate, failing  # noqa: E402, I001

from django.core.paginator import Paginator  # noqa: E402
from django.db import connection, transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from billing import selectors as billing_selectors  # noqa: E402
from billing.models import CreditNote, Invoice, InvoiceLine, NumberSeries  # noqa: E402
from catalogue import selectors as catalogue_selectors  # noqa: E402
from catalogue.models import Product  # noqa: E402
from customers import selectors as customer_selectors  # noqa: E402
from customers.models import Customer, Zone  # noqa: E402
from fulfilment import selectors as fulfilment_selectors  # noqa: E402
from identity.models import User  # noqa: E402
from inventory import selectors as stock_selectors  # noqa: E402
from inventory.models import ReasonCode, StockLocation, StockLot, StockMovement  # noqa: E402
from ledger.models import CustomerLedgerEntry  # noqa: E402
from orders import selectors as order_selectors  # noqa: E402
from orders.models import SalesOrder  # noqa: E402
from receivables import selectors as receivables_selectors  # noqa: E402
from reporting import selectors as reports  # noqa: E402
from sync import selectors as sync_selectors  # noqa: E402

# ======================================================================= frozen thresholds
#: `02` NFR-PER-003 and FR-RPT-015: *"within 10 seconds over five years of history."*
REPORT_BUDGET_SECONDS = 10.0

#: `02` NFR-PER-001 / `01` NFR-3: *"within 2 seconds at the 95th percentile."*
INTERACTIVE_BUDGET_SECONDS = 2.0
INTERACTIVE_PERCENTILE = 95

#: `02` NFR-SCA-003: *"No query may degrade worse than linearly with retained history."*
#: Linear growth is an exponent of exactly 1.0 in ``time ~ history ** k``. That is the
#: requirement's own line and it is what gets reported.
LINEAR_EXPONENT = 1.0

#: A **measurement-noise allowance, not a relaxation of the requirement.** Sub-second
#: timings are dominated by fixed per-call overhead, so a raw exponent bounces either side
#: of 1.0 between runs on identical code. An exponent above `LINEAR_EXPONENT` is always
#: reported as a WARN; only one above the allowance fails the stage. Both numbers are
#: printed so a reviewer can apply the frozen line themselves.
LINEARITY_NOISE_ALLOWANCE = 0.15

#: Below this, a timing is fixed overhead rather than work, and its growth exponent carries
#: no information. Such an operation is reported NOT ASSESSABLE, never PASS.
LINEARITY_NOISE_FLOOR_SECONDS = 0.050

#: `01` NFR-4's DR-8 master-data ceilings. Named so the profile below cannot drift from the
#: document silently, and so a contract can assert the two agree.
DR8_MAX_SKUS = 10_000
DR8_MAX_RETAILERS = 10_000
DR8_YEARS_RETAINED = 5

#: Repetitions per interactive operation. A 95th percentile needs enough samples for the
#: 95th to be a real observation rather than the maximum: at n=30 the nearest-rank p95 is
#: the 29th of 30, so two slow samples are needed to move it.
INTERACTIVE_REPETITIONS = 30

# ================================================================== the disposable target
#: **The only database this harness may write to.**
#:
#: The corpus is ~750,000 rows of synthetic financial documents written *without* their
#: services, and it is not undoable short of dropping the database. Run against the working
#: development database it would destroy the ability to demonstrate anything from real data
#: — including the source counts a B-3 restore rehearsal reads.
#:
#: A **separate database inside the same PostgreSQL container** is the repository's existing
#: answer to exactly this problem: `ops/restore.sh` restores into `districore_restore_test`
#: for the same reason and refuses the live names the same way. Same server, same volume,
#: same image, same Django, same migrations — a different `DATABASE_URL`, and nothing else.
PERF_DATABASE = "districore_perf"

#: Named only so the refusal can say *why*. The guard is an **allow-list**, so these — and
#: every other name — are already refused; this turns a blunt "wrong database" into the
#: sentence the operator needs to read.
PROTECTED_DATABASES = ("districore", "districore_prod")

#: `webadmin.master_views.PAGE_SIZE`. Every S1 list screen is paginated, so the interactive
#: cost of one is a COUNT plus one page — not the whole queryset. Measuring the unpaginated
#: queryset would overstate the screen by orders of magnitude and prove nothing about it.
S1_PAGE_SIZE = 25


# ============================================================================== profiles
@dataclass(frozen=True)
class Profile:
    """A dataset shape. `dr8` is the envelope; `m7` reproduces the historical measurement."""

    name: str
    customers: int
    products: int
    invoices: int
    movements: int
    payments_per_customer: int
    note: str

    lines_per_invoice: int = 4
    credit_note_rate: float = 0.03
    years: int = DR8_YEARS_RETAINED


PROFILES: dict[str, Profile] = {
    "dr8": Profile(
        name="dr8",
        customers=DR8_MAX_RETAILERS,
        products=DR8_MAX_SKUS,
        invoices=73_000,
        movements=60_000,
        payments_per_customer=30,
        note=(
            "DR-8 envelope: master data at `01` NFR-4's stated ceilings, transaction volume "
            "at M7's sustained sizing. The profile NFR-PER-001 and NFR-SCA-001 require."
        ),
    ),
    "m7": Profile(
        name="m7",
        customers=1_000,
        products=500,
        invoices=73_000,
        movements=60_000,
        payments_per_customer=30,
        note=(
            "The M7 shape, reproduced so 2026-08-09's numbers stay comparable. **Below the "
            "DR-8 master-data ceilings** — sufficient for FR-RPT-015's history depth, not "
            "sufficient to evidence NFR-SCA-001."
        ),
    ),
}

#: Adjustment sizes: uniform over ±50, **excluding zero**. `ck_stock_movement_qty_nonzero`
#: refuses a zero movement — "a zero movement is a bug, not a record" — so drawing from
#: `randint(-50, 50)` would have hit the constraint roughly 594 times in 60,000 rows.
NONZERO_ADJUSTMENTS: tuple[int, ...] = tuple(n for n in range(-50, 51) if n)

SEED = 20260808


def _log(message: str = "") -> None:
    """Human output on **stderr**, so stdout can carry the machine-checkable document.

    `docker/compose.dev.yml` mounts `../ops:/app/ops:ro` — deliberately, because stage 7
    contracts read it — so the harness **cannot write a file into `ops/` from inside the
    container**. Splitting the streams lets `--json -` return the evidence through
    `docker compose exec` for the caller to redirect on the host, without relaxing a
    read-only mount to suit a reporting convenience.
    """
    print(message, file=sys.stderr, flush=True)


def _bulk(model: Any, rows: list[Any], label: str) -> None:
    _log(f"    {label}: {len(rows):,}")
    model.objects.bulk_create(rows, batch_size=2_000)


def guard_database() -> str:
    """**Fail closed.** Refuse every database except the disposable one.

    An allow-list rather than a deny-list, and deliberately: a deny-list protects the two
    names someone thought of, and this harness would happily fill `districore_staging` or a
    colleague's restored copy with 750,000 synthetic documents. Anything that is not the
    disposable target is refused, so a forgotten `DATABASE_URL` override fails the run
    instead of the database.

    Called from `main` *and* from `synthesise`, because the second is the one that writes
    and a guard the writer does not consult is a guard someone can route around.
    """
    name = connection.settings_dict["NAME"]
    if name == PERF_DATABASE:
        return name

    protected = (
        f"`{name}` is a working database. "
        if name in PROTECTED_DATABASES
        else f"`{name}` is not the disposable performance database. "
    )
    raise SystemExit(
        f"REFUSED: {protected}This harness writes ~750,000 synthetic financial documents "
        f"directly, bypassing every service, and nothing undoes that.\n"
        f"    It may only run against `{PERF_DATABASE}`, which `make perf` drops and "
        f"recreates for each run.\n"
        f"    Use `make perf`. If you are invoking it by hand, override DATABASE_URL to "
        f"point at `{PERF_DATABASE}` — never at a database you would mind losing."
    )


# ============================================================================== dataset
@transaction.atomic
def synthesise(profile: Profile) -> User:
    """Write the dataset directly, bypassing the services.

    Deliberate: the services enforce credit, stock and numbering rules whose cost is not
    what is being measured, and running 73,000 orders through them would take hours. The
    *shape* of the data is what the query planner sees, and the shape is faithful.

    This is a measurement fixture, not a fixture the suite may reuse — writing financial
    documents without their services is exactly what N-01 forbids in production code.
    """
    guard_database()

    # S311: this is a deterministic measurement fixture, not a security context. The seed
    # is fixed so two runs measure the same shape and can be compared to each other.
    rng = random.Random(SEED)  # noqa: S311
    today = date.today()
    start = today - timedelta(days=365 * profile.years)

    owner = User.objects.filter(roles__code="OWNER").first()
    if owner is None:
        raise SystemExit("Seed an OWNER before running this harness.")

    zone = Zone.objects.first() or Zone.objects.create(name="Perf", city="Patna", pin_code="800001")
    location = StockLocation.objects.get(is_default=True)
    reasons = list(ReasonCode.objects.filter(is_active=True))

    _log("--> customers and products")
    _bulk(
        Customer,
        [
            Customer(
                code=f"PERF-C-{n:05d}",
                shop_name=f"Perf Shop {n}",
                zone=zone,
                phone=f"+9170{n:09d}",
                billing_address="Perf Bazaar",
            )
            for n in range(profile.customers)
        ],
        "customers",
    )
    customers = list(Customer.objects.filter(code__startswith="PERF-C-"))

    _bulk(
        Product,
        [
            Product(
                code=f"PERF-P-{n:05d}",
                name=f"Perf Product {n}",
                selling_price=Decimal("100.00"),
                tax_rate_percent=Decimal("18.00"),
            )
            for n in range(profile.products)
        ],
        "products",
    )
    products = list(Product.objects.filter(code__startswith="PERF-P-"))

    # The field is `lot_code`, not `code` (04 T-09). `uq_stock_lot` is (product, lot_code).
    # Bulk-created rather than `get_or_create`d per product: at the DR-8 ceiling that would
    # be 10,000 round trips before a single row of history exists.
    _bulk(
        StockLot,
        [StockLot(product=product, lot_code="DEFAULT") for product in products],
        "stock lots",
    )
    lots = {lot.product_id: lot for lot in StockLot.objects.filter(lot_code="DEFAULT")}

    _log("--> stock movements")
    _bulk(
        StockMovement,
        [
            StockMovement(
                product=(product := rng.choice(products)),
                location=location,
                lot=lots[product.pk],
                movement_type=StockMovement.Type.ADJUSTMENT,
                quantity=Decimal(rng.choice(NONZERO_ADJUSTMENTS)),
                reason_code=rng.choice(reasons) if reasons else None,
                occurred_at=timezone.make_aware(
                    datetime.combine(
                        start + timedelta(days=rng.randint(0, 365 * profile.years)), time.min
                    )
                ),
                created_by=owner,
            )
            for _ in range(profile.movements)
        ],
        "movements",
    )

    _log("--> orders, invoices, lines, ledger")
    # A `NumberSeries` row for the fixture's documents to point at. M7 borrowed one from an
    # existing invoice, which made the harness unrunnable on a fresh database — the state
    # every release measurement starts from. The counter is **not** advanced and no service
    # is involved: this is a foreign key the fixture needs, not a numbering exercise, and
    # `PERF-` document numbers never enter the gapless sequence the auditor reads.
    series, _created = NumberSeries.objects.get_or_create(
        series_key=NumberSeries.Key.INVOICE,
        financial_year="PERF-0000",
        defaults={"prefix": "PERF-", "is_active": False},
    )

    _bulk(
        SalesOrder,
        [
            SalesOrder(
                order_number=f"PERF-O-{n:06d}",
                customer=rng.choice(customers),
                order_date=start + timedelta(days=rng.randint(0, 365 * profile.years)),
                status=SalesOrder.Status.DELIVERED,
                source=SalesOrder.Source.WEB,
                assigned_user=owner,
                created_by=owner,
                subtotal_amount=Decimal("400.00"),
                total_amount=Decimal("472.00"),
            )
            for n in range(profile.invoices)
        ],
        "orders",
    )
    orders = list(SalesOrder.objects.filter(order_number__startswith="PERF-O-"))

    _bulk(
        Invoice,
        [
            Invoice(
                invoice_number=f"PERF-INV-{n:06d}",
                number_series=series,
                sales_order=order,
                customer=order.customer,
                invoice_date=order.order_date,
                financial_year=f"{order.order_date.year}-{(order.order_date.year + 1) % 100:02d}",
                status=Invoice.Status.ISSUED,
                seller_legal_name="Perf",
                buyer_name="Perf",
                subtotal_amount=Decimal("400.00"),
                taxable_amount=Decimal("400.00"),
                cgst_amount=Decimal("36.00"),
                sgst_amount=Decimal("36.00"),
                total_amount=Decimal("472.00"),
                issued_by=owner,
            )
            for n, order in enumerate(orders)
        ],
        "invoices",
    )
    invoices = list(Invoice.objects.filter(invoice_number__startswith="PERF-INV-"))

    _bulk(
        InvoiceLine,
        [
            InvoiceLine(
                invoice=invoice,
                line_number=index,
                product=(product := rng.choice(products)),
                product_code=product.code,
                product_name=product.name,
                quantity=Decimal("1.000"),
                unit_name="PCS",
                unit_price=Decimal("100.00"),
                taxable_amount=Decimal("100.00"),
                tax_rate_percent=Decimal("18.00"),
                cgst_amount=Decimal("9.00"),
                sgst_amount=Decimal("9.00"),
                line_total=Decimal("118.00"),
            )
            for invoice in invoices
            for index in range(1, profile.lines_per_invoice + 1)
        ],
        "invoice lines",
    )

    _bulk(
        CustomerLedgerEntry,
        [
            CustomerLedgerEntry(
                customer=invoice.customer,
                entry_date=invoice.invoice_date,
                entry_type=CustomerLedgerEntry.Type.INVOICE,
                amount=Decimal("472.00"),
                narration=invoice.invoice_number,
                source_document_type="INVOICE",
                source_document_id=invoice.pk,
                created_by=owner,
            )
            for invoice in invoices
        ],
        "ledger entries",
    )

    _log("--> credit notes")
    credited = rng.sample(invoices, int(len(invoices) * profile.credit_note_rate))
    _bulk(
        CreditNote,
        [
            CreditNote(
                credit_note_number=f"PERF-CN-{n:06d}",
                number_series=series,
                invoice=invoice,
                customer=invoice.customer,
                credit_note_date=invoice.invoice_date + timedelta(days=rng.randint(0, 40)),
                financial_year=invoice.financial_year,
                reason="Perf",
                reason_code=rng.choice(reasons) if reasons and n % 3 else None,
                seller_legal_name="Perf",
                buyer_name="Perf",
                subtotal_amount=Decimal("100.00"),
                taxable_amount=Decimal("100.00"),
                cgst_amount=Decimal("9.00"),
                sgst_amount=Decimal("9.00"),
                total_amount=Decimal("118.00"),
                issued_by=owner,
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
                entry_date=start + timedelta(days=rng.randint(0, 365 * profile.years)),
                entry_type=CustomerLedgerEntry.Type.PAYMENT,
                amount=Decimal("-472.00"),
                narration=f"PERF-PAY-{customer.pk}-{n}",
                created_by=owner,
            )
            for customer in customers
            for n in range(profile.payments_per_customer)
        ],
        "payment entries",
    )
    return owner


# ============================================================================== results
@dataclass
class Measurement:
    """One timed operation and its verdict against a frozen threshold."""

    label: str
    seconds: float
    rows: int
    budget: float
    verdict: str
    samples: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "label": self.label,
            "seconds": round(self.seconds, 4),
            "rows": self.rows,
            "budget_seconds": self.budget,
            "verdict": self.verdict,
        }
        if self.samples:
            payload["samples"] = [round(sample, 4) for sample in self.samples]
        return payload


def _rows_of(result: Any) -> int:
    for attribute in ("rows", "metrics", "entries"):
        value = getattr(result, attribute, None)
        if value is not None:
            return len(value)
    try:
        return len(result)
    except TypeError:
        return 0


def _percentile(samples: list[float], percentile: int) -> float:
    """Nearest-rank percentile — an **observed** sample, never an interpolated fiction.

    `statistics.quantiles` interpolates, which invents a value that no run produced. For a
    latency budget the honest answer is a measurement someone actually took.
    """
    ordered = sorted(samples)
    rank = math.ceil(percentile / 100 * len(ordered))
    return ordered[max(rank, 1) - 1]


# ================================================= NFR-PER-003 / FR-RPT-015 — the reports
def _report_cases(owner: User, profile: Profile) -> list[tuple[str, Callable[[], Any]]]:
    """Every report the product exposes. **All of them, or the stage proves nothing.**

    `sync_health` and the customer statement post-date M7 and were never timed. A budget
    that skips a report is a budget the newest report is exempt from.
    """
    today = date.today()
    year = (today - timedelta(days=365), today)
    five = (today - timedelta(days=365 * profile.years), today)
    a_customer = Customer.objects.filter(code__startswith="PERF-C-").first()

    def sync_health_endpoint() -> Any:
        # Timed the way the endpoint pays for it: `fleet_status` is fetched by the view's
        # own `parameters()` before `sync_health` is called (api/v1/report_views.py).
        rows = sync_selectors.fleet_status(date_from=five[0], date_to=five[1])
        return reports.sync_health(owner, device_rows=rows, date_from=five[0], date_to=five[1])

    cases: list[tuple[str, Callable[[], Any]]] = [
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
        ("returns (5y)", lambda: reports.returns_report(owner, date_from=five[0], date_to=five[1])),
        ("receivables ageing", lambda: reports.receivables_ageing(owner)),
        (
            "top customers (5y)",
            lambda: reports.top_customers(owner, date_from=five[0], date_to=five[1]),
        ),
        (
            "order pipeline (5y)",
            lambda: reports.order_pipeline(owner, date_from=five[0], date_to=five[1]),
        ),
        ("sync health (5y)", sync_health_endpoint),
        ("dashboard", lambda: reports.dashboard(owner)),
    ]
    if a_customer is not None:
        cases.append(
            (
                "customer statement (5y)",
                lambda: reports.statement_table(a_customer, date_from=five[0], date_to=five[1]),
            )
        )
    return cases


def measure_reports(owner: User, profile: Profile) -> list[Measurement]:
    """NFR-PER-003 / FR-RPT-015 — every report inside 10 seconds over five years."""
    _log()
    _log(
        "NFR-PER-003 / FR-RPT-015 — reports, budget "
        f"{REPORT_BUDGET_SECONDS:.0f}s each, five years of history"
    )
    _log(f"{'report':<26} {'seconds':>9}  {'rows':>7}  result")
    _log("-" * 62)

    results: list[Measurement] = []
    for label, build in _report_cases(owner, profile):
        started = clock.perf_counter()
        outcome = build()
        elapsed = clock.perf_counter() - started
        verdict = "OK" if elapsed < REPORT_BUDGET_SECONDS else "BREACH"
        results.append(
            Measurement(label, elapsed, _rows_of(outcome), REPORT_BUDGET_SECONDS, verdict)
        )
        _log(f"{label:<26} {elapsed:>9.3f}  {_rows_of(outcome):>7}  {verdict}")
    _log("-" * 62)
    return results


# ========================================== NFR-PER-001 — interactive S1 at the 95th
def _interactive_cases(owner: User) -> list[tuple[str, Callable[[], Any]]]:
    """`S1` back-office operations, as the screens actually perform them.

    **`S1` is the back-office and `S4` is the retailer portal** (`02` §115). `S4` is
    Edition 1b (`00` §19.1, M12) and does not exist in this tree, so NFR-PER-001's `S4`
    half is **not measurable at V1** — recorded as unmeasurable rather than assumed to pass.

    Every list screen paginates through `webadmin.master_views._page`, so one screen costs a
    COUNT plus one page of rows. Timing the unpaginated queryset would measure something no
    user ever waits for.
    """
    a_customer = Customer.objects.filter(code__startswith="PERF-C-").first()
    an_order = SalesOrder.objects.filter(order_number__startswith="PERF-O-").first()

    def page(queryset: Any) -> Any:
        paginator = Paginator(queryset, S1_PAGE_SIZE)
        return list(paginator.get_page(1).object_list), paginator.count

    cases: list[tuple[str, Callable[[], Any]]] = [
        ("S1 customer list", lambda: page(customer_selectors.search_customers(owner))),
        ("S1 product list", lambda: page(catalogue_selectors.search_products())),
        ("S1 stock list", lambda: page(stock_selectors.stock_on_hand())),
        ("S1 order list", lambda: page(order_selectors.search_orders(owner))),
        ("S1 invoice list", lambda: page(billing_selectors.search_invoices(owner))),
        ("S1 delivery list", lambda: page(fulfilment_selectors.search_deliveries(owner))),
        ("S1 payment list", lambda: page(receivables_selectors.search_payments(owner))),
        ("S1 negative stock badge", lambda: stock_selectors.negative_stock().count()),
    ]
    if an_order is not None:
        cases.append(("S1 order detail", lambda: order_selectors.get_order_for(owner, an_order.pk)))
    if a_customer is not None:
        # The order-capture path: FR-ORD-007's credit figures are computed per customer.
        cases.append(("S1 available credit", lambda: order_selectors.available_credit(a_customer)))
        cases.append(
            (
                "S1 customer statement",
                lambda: receivables_selectors.customer_statement(a_customer),
            )
        )
    return cases


def measure_interactive(owner: User) -> list[Measurement]:
    """NFR-PER-001 — `S1` interactive operations, p95 within 2 seconds at the envelope."""
    _log()
    _log(
        f"NFR-PER-001 — interactive S1, p{INTERACTIVE_PERCENTILE} budget "
        f"{INTERACTIVE_BUDGET_SECONDS:.0f}s, {INTERACTIVE_REPETITIONS} samples each"
    )
    _log(f"{'operation':<26} {'p95':>9}  {'median':>8}  {'max':>8}  result")
    _log("-" * 68)

    results: list[Measurement] = []
    for label, call in _interactive_cases(owner):
        samples: list[float] = []
        for _ in range(INTERACTIVE_REPETITIONS):
            started = clock.perf_counter()
            call()
            samples.append(clock.perf_counter() - started)
        p95 = _percentile(samples, INTERACTIVE_PERCENTILE)
        verdict = "OK" if p95 < INTERACTIVE_BUDGET_SECONDS else "BREACH"
        results.append(
            Measurement(label, p95, 0, INTERACTIVE_BUDGET_SECONDS, verdict, samples=samples)
        )
        _log(
            f"{label:<26} {p95:>9.3f}  {statistics.median(samples):>8.3f}  "
            f"{max(samples):>8.3f}  {verdict}"
        )
    _log("-" * 68)
    _log(
        "    S4 (retailer portal) is Edition 1b (`00` §19.1, M12) and does not exist here. "
        "NFR-PER-001's S4 half is NOT MEASURABLE at V1."
    )
    return results


# ============================== NFR-SCA-003 — no worse than linear in retained history
#: History windows, in years. The exponent is fitted across the widest pair; the middle
#: point is printed so a reviewer can see whether growth is smooth or a cliff.
LINEARITY_WINDOWS = (1, 3, 5)


def _linearity_cases(owner: User) -> list[tuple[str, Callable[[int], Any]]]:
    """Only reports parameterised **by history window** can answer this question.

    `stock_position`, `receivables_ageing` and `dashboard` take no date range — their cost
    scales with master data, not with retained history — so this instrument cannot assess
    them and says so rather than scoring them.
    """
    today = date.today()

    def window(years: int) -> tuple[date, date]:
        return today - timedelta(days=365 * years), today

    return [
        (
            "sales (day)",
            lambda years: reports.sales_report(
                owner, date_from=window(years)[0], date_to=window(years)[1]
            ),
        ),
        (
            "sales (customer)",
            lambda years: reports.sales_report(
                owner, date_from=window(years)[0], date_to=window(years)[1], group_by="customer"
            ),
        ),
        (
            "top customers",
            lambda years: reports.top_customers(
                owner, date_from=window(years)[0], date_to=window(years)[1]
            ),
        ),
        (
            "order pipeline",
            lambda years: reports.order_pipeline(
                owner, date_from=window(years)[0], date_to=window(years)[1]
            ),
        ),
        (
            "returns",
            lambda years: reports.returns_report(
                owner, date_from=window(years)[0], date_to=window(years)[1]
            ),
        ),
        (
            "stock variance",
            lambda years: reports.stock_variance(
                owner, date_from=window(years)[0], date_to=window(years)[1]
            ),
        ),
    ]


def measure_linearity(owner: User) -> tuple[list[dict[str, Any]], int]:
    """NFR-SCA-003 — fit `time ~ history ** k` and hold `k` at the frozen line of 1.0."""
    _log()
    _log(
        "NFR-SCA-003 — growth exponent k in time ~ history**k across "
        f"{LINEARITY_WINDOWS} years. Linear is k <= {LINEAR_EXPONENT:.1f}"
    )
    header = "  ".join(f"{years}y".rjust(8) for years in LINEARITY_WINDOWS)
    _log(f"{'query':<22} {header}  {'k':>6}  result")
    _log("-" * 72)

    rows: list[dict[str, Any]] = []
    breaches = 0
    for label, build in _linearity_cases(owner):
        timings: dict[int, float] = {}
        for years in LINEARITY_WINDOWS:
            started = clock.perf_counter()
            build(years)
            timings[years] = clock.perf_counter() - started

        narrow, wide = LINEARITY_WINDOWS[0], LINEARITY_WINDOWS[-1]
        if timings[narrow] < LINEARITY_NOISE_FLOOR_SECONDS:
            verdict, exponent = "NOT ASSESSABLE", None
        else:
            exponent = math.log(timings[wide] / timings[narrow]) / math.log(wide / narrow)
            if exponent <= LINEAR_EXPONENT:
                verdict = "OK"
            elif exponent <= LINEAR_EXPONENT + LINEARITY_NOISE_ALLOWANCE:
                verdict = "WARN"
            else:
                verdict = "BREACH"
                breaches += 1

        measured = "  ".join(f"{timings[years]:>8.3f}" for years in LINEARITY_WINDOWS)
        shown = f"{exponent:>6.2f}" if exponent is not None else "     -"
        _log(f"{label:<22} {measured}  {shown}  {verdict}")
        rows.append(
            {
                "label": label,
                "seconds_by_years": {str(y): round(timings[y], 4) for y in LINEARITY_WINDOWS},
                "exponent": round(exponent, 4) if exponent is not None else None,
                "linear_exponent": LINEAR_EXPONENT,
                "noise_allowance": LINEARITY_NOISE_ALLOWANCE,
                "verdict": verdict,
            }
        )
    _log("-" * 72)
    _log(
        f"    k above {LINEAR_EXPONENT:.1f} is reported WARN; only k above "
        f"{LINEAR_EXPONENT + LINEARITY_NOISE_ALLOWANCE:.2f} fails, and that margin is a "
        "measurement-noise allowance, not a relaxation of NFR-SCA-003."
    )
    _log(
        "    stock position, receivables ageing and dashboard take no date range: their "
        "cost scales with master data, not history. NOT ASSESSABLE by this instrument."
    )
    return rows, breaches


# ================================================================================= main
def _stage(measurements: list[Measurement]) -> StageResult:
    """A timed stage, reduced to what `perf_verdicts` needs."""
    if not measurements:
        return StageResult(ran=False)
    worst = max(measurements, key=lambda m: m.seconds)
    return StageResult(
        ran=True,
        total=len(measurements),
        breached=tuple(m.label for m in measurements if m.verdict == "BREACH"),
        worst_label=worst.label,
        worst_seconds=worst.seconds,
    )


def _linearity_stage(rows: list[dict[str, Any]]) -> StageResult:
    """The linearity stage. **`NOT ASSESSABLE` is carried, not silently counted as fine.**

    A query with no date parameter cannot be scaled by retained history, so folding it into
    a pass would claim coverage the instrument does not have — which is how two thirds of
    NFR-SCA-003's sample would disappear into a green line.
    """
    if not rows:
        return StageResult(ran=False)
    return StageResult(
        ran=True,
        total=len(rows),
        breached=tuple(r["label"] for r in rows if r["verdict"] == "BREACH"),
        not_assessable=tuple(r["label"] for r in rows if r["verdict"] == "NOT ASSESSABLE"),
    )


def _dataset_matches(profile: Profile) -> bool:
    """A dataset built for another profile must not be silently measured as this one."""
    return (
        Invoice.objects.filter(invoice_number__startswith="PERF-INV-").count() == profile.invoices
        and Customer.objects.filter(code__startswith="PERF-C-").count() == profile.customers
        and Product.objects.filter(code__startswith="PERF-P-").count() == profile.products
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Performance and scalability evidence for NFR-PER-001/003/005 and "
        "NFR-SCA-001/003.",
    )
    parser.add_argument("--profile", choices=sorted(PROFILES), default="dr8")
    parser.add_argument(
        "--json",
        default=None,
        metavar="PATH",
        help="Write machine-checkable evidence. `-` writes it to stdout, which is how it "
        "escapes the read-only `ops/` mount inside the container.",
    )
    parser.add_argument(
        "--stage",
        choices=("all", "reports", "interactive", "linearity"),
        default="all",
        help="Run one stage. The release gate needs all of them.",
    )
    options = parser.parse_args(argv)
    profile = PROFILES[options.profile]

    _log(f"==> database {guard_database()} (disposable; `make perf` recreates it each run)")
    _log(f"==> profile {profile.name}: {profile.note}")
    _log(
        f"    customers {profile.customers:,} · products {profile.products:,} · "
        f"invoices {profile.invoices:,} · years {profile.years}"
    )
    if profile.name != "dr8":
        _log("    WARNING: below the DR-8 ceilings — cannot evidence NFR-PER-001 or NFR-SCA-001.")

    build_seconds = 0.0
    if _dataset_matches(profile):
        _log("--> dataset already present at this profile; measuring without regenerating.")
        owner = User.objects.filter(roles__code="OWNER").first()
        if owner is None:
            raise SystemExit("Seed an OWNER before running this harness.")
    else:
        started = clock.perf_counter()
        owner = synthesise(profile)
        build_seconds = clock.perf_counter() - started
        _log(f"--> dataset built in {build_seconds:.1f}s")

    reports_out: list[Measurement] = []
    interactive_out: list[Measurement] = []
    linearity_out: list[dict[str, Any]] = []
    linearity_breaches = 0

    if options.stage in ("all", "reports"):
        reports_out = measure_reports(owner, profile)
    if options.stage in ("all", "interactive"):
        interactive_out = measure_interactive(owner)
    if options.stage in ("all", "linearity"):
        linearity_out, linearity_breaches = measure_linearity(owner)

    at_envelope = profile.name == "dr8"
    verdicts = evaluate(
        reports=_stage(reports_out),
        interactive=_stage(interactive_out),
        linearity=_linearity_stage(linearity_out),
        at_envelope=at_envelope,
        report_budget_seconds=REPORT_BUDGET_SECONDS,
        interactive_budget_seconds=INTERACTIVE_BUDGET_SECONDS,
        interactive_percentile=INTERACTIVE_PERCENTILE,
    )
    blocking = failing(verdicts)
    total = (
        sum(m.verdict == "BREACH" for m in reports_out)
        + sum(m.verdict == "BREACH" for m in interactive_out)
        + linearity_breaches
    )

    _log()
    _log("==> requirement verdicts")
    for verdict in verdicts:
        _log(f"    {verdict}")
    _log()
    _log(f"==> {total} breach(es); {len(blocking)} requirement(s) failing")

    if options.json is not None:
        document = json.dumps(
            {
                "measured_at": timezone.now().isoformat(),
                "profile": {
                    "name": profile.name,
                    "customers": profile.customers,
                    "products": profile.products,
                    "invoices": profile.invoices,
                    "years": profile.years,
                    "at_dr8_envelope": at_envelope,
                },
                "dataset_build_seconds": round(build_seconds, 1),
                "thresholds": {
                    "report_budget_seconds": REPORT_BUDGET_SECONDS,
                    "interactive_budget_seconds": INTERACTIVE_BUDGET_SECONDS,
                    "interactive_percentile": INTERACTIVE_PERCENTILE,
                    "linear_exponent": LINEAR_EXPONENT,
                },
                "reports": [m.as_dict() for m in reports_out],
                "interactive": [m.as_dict() for m in interactive_out],
                "linearity": linearity_out,
                "verdicts": [verdict.as_dict() for verdict in verdicts],
                "breaches": total,
                "failing_requirements": [verdict.requirement for verdict in blocking],
            },
            indent=2,
        )
        if options.json == "-":
            # `_EVIDENCE_STREAM`, not `sys.stdout` — stdout was swapped to stderr above so
            # that library logging cannot precede the opening brace.
            print(document, file=_EVIDENCE_STREAM, flush=True)
            _log("==> evidence written to stdout")
        else:
            Path(options.json).write_text(document, encoding="utf-8")
            _log(f"==> evidence written to {options.json}")

    # **Driven by the requirement verdicts, not by a breach counter.** A gap in the evidence
    # — PARTIAL, BLOCKED, NOT MEASURED — is not a violation, and only a violation may stop
    # the run. `total` is reported for the operator; it decides nothing.
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
