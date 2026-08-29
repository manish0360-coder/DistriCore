"""Structural contracts for `purchasing` (D5).

**`status` is the state machine, and a state machine that anything may assign is not one.**
`ALLOWED_TRANSITIONS` plus `_transition` are the specification (`04` T-30.1); a service that
wrote `status` directly would bypass both the map and the audit row that goes with it, and
would do so invisibly — the resulting order would simply be in a state nothing recorded it
entering.

Enforced here rather than in Dart or by review because it needs a parser, not a compiler, and
because `make verify` is the only authority (N-12). Same construction as
`test_reporting_boundary.py`, which asserts `reporting` owns nothing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.adversarial

BACKEND = Path(__file__).resolve().parents[2]
PURCHASING = BACKEND / "purchasing"

#: The one function permitted to assign `status`. Named rather than inferred so that renaming
#: it is a deliberate act that fails this test.
TRANSITION = "_transition"


def _assignments_to_status(tree: ast.AST) -> list[tuple[str, int]]:
    """Every `<something>.status = …`, with the enclosing function's name."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            targets: list[ast.expr] = []
            if isinstance(inner, ast.Assign):
                targets = list(inner.targets)
            elif isinstance(inner, ast.AugAssign | ast.AnnAssign):
                targets = [inner.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr == "status":
                    found.append((node.name, inner.lineno))
    return found


def test_only_the_transition_function_assigns_status():
    """A caller that could set `status` would hold the state machine."""
    source = (PURCHASING / "services.py").read_text(encoding="utf-8")
    offenders = [
        f"{name}:{line}"
        for name, line in _assignments_to_status(ast.parse(source))
        if name != TRANSITION
    ]
    assert not offenders, (
        f"`status` is assigned outside `{TRANSITION}`: {offenders}. Every status change must "
        "go through the transition guard so that `ALLOWED_TRANSITIONS` is enforced and the "
        "audit row is written with it."
    )


def test_the_transition_function_exists_and_does_assign_status():
    """Anti-vacuity. If `_transition` were renamed or stopped writing `status`, the test above
    would pass while guarding nothing."""
    source = (PURCHASING / "services.py").read_text(encoding="utf-8")
    assignments = _assignments_to_status(ast.parse(source))
    assert any(name == TRANSITION for name, _ in assignments), (
        f"`{TRANSITION}` no longer assigns `status` — this suite would pass vacuously."
    )


def test_purchasing_writes_no_stock_movement():
    """**Stage 3's contract, asserted from Stage 2 so it can never be broken quietly.**

    D-PUR-7: goods receipt will call `inventory.services.receive_stock`, never write a
    `StockMovement` itself. Today `purchasing` imports no `inventory` at all, and this asserts
    that the day it does, it does so through the service.
    """
    offenders = []
    for path in PURCHASING.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("inventory.models"):
                    offenders.append(f"{path.name}: from {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("inventory.models"):
                        offenders.append(f"{path.name}: import {alias.name}")
    assert not offenders, (
        f"`purchasing` imports inventory models directly: {offenders}. Stock moves through "
        "`inventory.services.receive_stock` and its `source_document_type` contract (D-PUR-7), "
        "never by writing `StockMovement` from another app."
    )


# ------------------------------------------------------------ goods receipt (D5 Stage 3)


LEDGER_REGISTRY = "ledger.services"
STOCK_REGISTRY = "inventory.services"


def _registry_writes(source: str) -> set[str]:
    """Which `SOURCE_DOCUMENT_REGISTRY` aliases this module assigns into.

    Matches `<alias>[<anything>] = …`, and resolves the alias back to the module it was
    imported from, so a rename of the local alias cannot make this test blind.
    """
    tree = ast.parse(source)
    alias_to_module: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "SOURCE_DOCUMENT_REGISTRY":
                    alias_to_module[alias.asname or alias.name] = node.module

    written: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                module = alias_to_module.get(target.value.id)
                if module is not None:
                    written.add(module)
    return written


def test_goods_receipt_is_registered_in_both_source_document_registries():
    """**Two dictionaries that happen to share a name**, and the hazard is real.

    `inventory.services.SOURCE_DOCUMENT_REGISTRY` governs `stock_movement`;
    `ledger.services.SOURCE_DOCUMENT_REGISTRY` governs the two ledgers. A `GoodsReceipt`
    registered in only one would be refused by `_resolve_source` in the other — at runtime, on
    the first real receipt, not here.
    """
    written = _registry_writes((PURCHASING / "registry.py").read_text(encoding="utf-8"))
    assert written == {STOCK_REGISTRY, LEDGER_REGISTRY}, (
        f"`purchasing/registry.py` writes to {sorted(written)}. A goods receipt moves stock "
        "AND raises a liability, so it must be registered in both registries."
    )


def test_the_supplier_payment_source_type_is_exactly_payment():
    """**S4.3 U-1 — the equality `ledger.walk` depends on, pinned in the registry.**

    `annulled_entry_ids` only accepts an annullable target where
    `entry.entry_type == entry.source_document_type`. A supplier payment's ledger entry has
    `entry_type = "PAYMENT"`, so registering the model as anything else — `"SUPPLIER_PAYMENT"`
    is the tempting name — breaks that equality.

    **The breakage is silent.** No exception, no failing import: the reversal `ADJUSTMENT`
    simply finds no target, nothing is annulled, and the reversal becomes an ordinary
    positive debit dated the day of the reversal. Settled receipts then reappear as *new*
    debt instead of at their original ages — the M6 §5A defect, on the payables side, in a
    tool whose only purpose is to show which debt is oldest.
    """
    source = (PURCHASING / "registry.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    assigned: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned[target.id] = str(node.value.value)

    assert assigned.get("SUPPLIER_PAYMENT_SOURCE_TYPE") == "PAYMENT", (
        "SupplierPayment must register as exactly \"PAYMENT\" so that "
        "`entry_type == source_document_type` holds and `ledger.walk` can annul a reversal. "
        f"Found: {assigned.get('SUPPLIER_PAYMENT_SOURCE_TYPE')!r}"
    )
    assert "SupplierPayment" in source, "SupplierPayment is no longer registered at all"


def test_the_registry_module_is_imported_at_app_ready():
    """Registration that nothing imports is registration that never happens."""
    source = (PURCHASING / "apps.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    ready = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "ready"
        ),
        None,
    )
    assert ready is not None, "`PurchasingConfig.ready` is gone; nothing imports the registry."
    imports = {
        alias.name
        for node in ast.walk(ready)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "registry" in imports, (
        "`PurchasingConfig.ready` no longer imports `registry`, so `GoodsReceipt` would not be "
        "a permitted source document in either registry."
    )


def test_purchasing_writes_no_ledger_entry_directly():
    """The payable goes through `ledger.services.record_supplier_entry`, the single write path.

    `SupplierLedgerEntry` may be imported for its `Type` enum — the service needs the code —
    but `purchasing` must never construct or `.create()` one. That would bypass the sign
    rules, the source-document registry and the zero check in one step.
    """
    offenders = []
    for path in PURCHASING.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # `SupplierLedgerEntry(...)`
            if isinstance(func, ast.Name) and func.id == "SupplierLedgerEntry":
                offenders.append(f"{path.name}:{node.lineno} SupplierLedgerEntry(...)")
            # `SupplierLedgerEntry.objects.create(...)`
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "create"
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "objects"
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "SupplierLedgerEntry"
            ):
                offenders.append(f"{path.name}:{node.lineno} SupplierLedgerEntry.objects.create")
    assert not offenders, (
        f"`purchasing` writes supplier ledger entries directly: {offenders}. "
        "`ledger.services.record_supplier_entry` is the only write path (BR-005)."
    )


def test_the_goods_receipt_transaction_is_atomic():
    """Stock, payable and lifecycle commit together or not at all.

    A `create_goods_receipt` without `@transaction.atomic` could leave stock that arrived with
    no payable behind it, or a payable for stock nobody has — the one outcome the business
    cannot absorb, and one that no unit test would notice on a passing run.
    """
    tree = ast.parse((PURCHASING / "services.py").read_text(encoding="utf-8"))
    target = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "create_goods_receipt"
        ),
        None,
    )
    assert target is not None, "`create_goods_receipt` is gone; this contract guards nothing."
    decorators = {ast.unparse(d) for d in target.decorator_list}
    assert "transaction.atomic" in decorators, (
        f"`create_goods_receipt` is decorated with {sorted(decorators)}. It must be "
        "`@transaction.atomic`: it writes a receipt, stock movements, a supplier ledger entry "
        "and a lifecycle transition, and a partial failure would be silent corruption."
    )


def test_the_over_receipt_tolerance_is_not_hard_coded():
    """BD-2's ruling, verbatim: *do not hard-code 5%*.

    The tolerance is `BusinessProfile.over_receipt_tolerance_percent` and nothing else. This
    asserts that `services.py` reads it from the profile rather than carrying a literal that
    an owner cannot change.
    """
    source = (PURCHASING / "services.py").read_text(encoding="utf-8")
    assert "over_receipt_tolerance_percent" in source, (
        "`purchasing.services` no longer reads the configured tolerance."
    )
    assert "get_business_profile" in source, (
        "`purchasing.services` no longer reads `BusinessProfile`, so the tolerance cannot be "
        "the configured one."
    )
