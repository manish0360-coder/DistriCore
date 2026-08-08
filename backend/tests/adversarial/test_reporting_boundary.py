"""**The M7 boundary, proven rather than trusted** (M7 §8.1, M7-4, M7-5).

`03` §2.1 gives `reporting` the entry *"owns nothing — read-only queries"*. That is a
sentence in a document. These tests are the reason it will still be true at M12.

Three properties, and each has a distinct failure mode:

* **No writer may be imported.** A report with a side effect is not a report, and the
  first step towards one is `from x import services`.
* **No model may be imported.** Reaching a model directly is how a report acquires its own
  interpretation of a business rule — the D-3 violation that produces two implementations
  of one number (§1.1).
* **No stored state.** No `models.py`, no `services.py`, no migrations. `reporting` must
  remain the one module that could be deleted without changing a stored fact.

`lint-imports` proves the layering. It cannot prove any of the above, because forbidding
`reporting -> *.services` while allowing `reporting -> *.selectors` is a distinction
between submodules of the same package. Hence AST.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.adversarial

MODULE = Path(__file__).resolve().parents[2] / "reporting"


def _source_files() -> list[Path]:
    files = sorted(MODULE.glob("*.py"))
    assert files, "reporting package not found — this suite would pass vacuously"
    return files


def _imported_modules(path: Path) -> set[str]:
    """Every module name this file imports, however it spells the import."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            # `from billing import selectors` — the interesting name is the attribute.
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_reporting_imports_no_service_module():
    """M7-5. A reader that can reach a writer will eventually be asked to use it."""
    offenders = {
        path.name: sorted(name for name in _imported_modules(path) if name.endswith(".services"))
        for path in _source_files()
    }
    assert not any(offenders.values()), f"reporting imported a service module: {offenders}"


#: The domain packages whose ``models`` modules are off limits. Django's own
#: ``django.db.models`` is the ORM's expression API — ``Sum``, ``Count``, ``QuerySet`` —
#: and using it is how one arranges rows. The rule is about *our* tables, not about SQL.
DOMAIN_PACKAGES = (
    "core", "identity", "catalogue", "customers", "inventory", "ledger",
    "pricing", "orders", "fulfilment", "billing", "receivables",
)


def test_reporting_imports_no_model_module():
    """D-3. A report that touches a domain model has stopped arranging and started deriving."""
    offenders = {
        path.name: sorted(
            name
            for name in _imported_modules(path)
            if name.endswith(".models") and name.split(".")[0] in DOMAIN_PACKAGES
        )
        for path in _source_files()
    }
    assert not any(offenders.values()), f"reporting imported a model module: {offenders}"


def test_reporting_declares_no_models_services_or_migrations():
    """M7-4. The absence is the design; a later addition must be a deliberate one."""
    forbidden = [name for name in ("models.py", "services.py") if (MODULE / name).exists()]
    assert not forbidden, f"reporting must own nothing, found: {forbidden}"
    assert not (MODULE / "migrations").exists(), "reporting must not own a migration"


def test_reporting_defines_no_django_model():
    """Belt and braces: a model declared inside selectors.py would pass the file check."""
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {ast.unparse(base) for base in node.bases}
            assert not any("Model" in base for base in bases), (
                f"{path.name}:{node.name} looks like a Django model inside reporting"
            )


def test_reporting_is_not_an_installed_app():
    """It has nothing to install. Being absent from INSTALLED_APPS is the proof."""
    from django.conf import settings

    assert not any(app.startswith("reporting") for app in settings.INSTALLED_APPS)


def test_every_domain_selector_reporting_uses_still_exists():
    """Names, not just modules.

    A renamed selector elsewhere would surface as a mid-request ``AttributeError`` on an
    owner screen. This turns that into a red test at the boundary that owns the coupling.
    """
    from billing import selectors as billing_selectors
    from inventory import selectors as inventory_selectors
    from orders import selectors as order_selectors
    from receivables import selectors as receivable_selectors

    expected = {
        billing_selectors: ("issued_invoices", "visible_credit_notes"),
        inventory_selectors: ("stock_on_hand", "variance_by_reason"),
        order_selectors: ("visible_orders", "awaiting_dispatch"),
        receivable_selectors: (
            "receivables_position",
            "visible_customers_for_receivables",
            "search_payments",
        ),
    }
    missing = [
        f"{module.__name__}.{name}"
        for module, names in expected.items()
        for name in names
        if not hasattr(module, name)
    ]
    assert not missing, f"reporting depends on selectors that no longer exist: {missing}"
