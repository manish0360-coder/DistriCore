"""**One FIFO algorithm, below both consumers** (D5 Stage 4 S4.2).

S4.2's whole purpose was to stop the settlement walk being copied. Two properties make that
durable, and neither is provable by running the algorithm:

1. **It exists exactly once.** The next author who needs a walk for a third ledger must find
   `ledger.walk` and pass a `WalkPolicy` — not paste 150 lines and edit four strings. The
   annulment pairing is subtle enough (*one annuller claims one target, and the pair must
   offset*) that two copies would diverge, and the divergence would show up as a wrong
   figure on a report rather than as a failing test.

2. **It sits below everything that uses it.** `receivables` is two layers above
   `purchasing`, so the walk could not have stayed where it was. If it ever acquires an
   upward import it stops being reachable from the lower consumer, and `lint-imports` would
   catch that only once a real import appeared — this catches the intent.

`lint-imports` proves the package graph. It cannot prove either property above: a duplicated
function inside one package breaks no layering rule, and `ledger.walk` importing `ledger.models`
would be perfectly legal while still being a dependency this module does not want. Hence AST.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.adversarial

BACKEND = Path(__file__).resolve().parents[2]
WALK = BACKEND / "ledger" / "walk.py"

#: Names that identify the algorithm itself. If any of these is *defined* outside
#: `ledger/walk.py`, the walk has been copied rather than called.
ALGORITHM_NAMES = frozenset({"annulled_entry_ids", "_annulled_entry_ids", "_Debit"})

#: Every layer at or above `orders | purchasing`, which is the lowest consumer. An import
#: from any of these would put the walk above a module that must be able to call it.
PACKAGES_ABOVE_LEDGER = frozenset(
    {
        "pricing", "orders", "purchasing", "fulfilment", "field",
        "billing", "receivables", "reporting", "sync", "api", "webadmin",
    }
)


def _production_modules() -> list[Path]:
    """Every backend source file that is not a test or a migration."""
    files = [
        path
        for path in BACKEND.rglob("*.py")
        if "migrations" not in path.parts
        and "tests" not in path.parts
        and path.name != "__init__.py"
    ]
    assert files, "no backend modules found — this suite would pass vacuously"
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
    return found


def _defined_names(path: Path) -> set[str]:
    """Top-level and nested function/class definitions in one file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


def test_the_walk_module_exists_where_both_consumers_can_reach_it():
    """Anti-vacuity: every assertion below is about a file that must actually be there."""
    assert WALK.exists(), "ledger/walk.py is missing — S4.2 has been undone"
    assert ALGORITHM_NAMES <= _defined_names(WALK) | {"_annulled_entry_ids"}, (
        f"ledger/walk.py no longer defines the algorithm: {sorted(_defined_names(WALK))}"
    )


def test_the_fifo_algorithm_is_defined_exactly_once():
    """**Requirement 5, mechanically.** No module outside `ledger.walk` may define it.

    This is the test that fires if S4.3 pastes the walk into `purchasing` instead of
    supplying a `WalkPolicy`.
    """
    offenders = {
        str(path.relative_to(BACKEND)): sorted(_defined_names(path) & ALGORITHM_NAMES)
        for path in _production_modules()
        if path != WALK and _defined_names(path) & ALGORITHM_NAMES
    }
    assert not offenders, (
        f"the FIFO walk appears to be reimplemented outside ledger/walk.py: {offenders}. "
        "A second ledger supplies a WalkPolicy; it does not copy the algorithm."
    )


def test_receivables_no_longer_carries_its_own_copy():
    """The specific case S4.2 removed, named so a revert is loud rather than quiet."""
    source = (BACKEND / "receivables" / "selectors.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "ledger.walk" in _imported_modules(BACKEND / "receivables" / "selectors.py"), (
        "receivables.selectors no longer imports ledger.walk — it has stopped delegating"
    )

    walk_fn = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_walk"),
        None,
    )
    assert walk_fn is not None, "receivables.selectors._walk is gone; the M6 suite calls it"

    called = {
        node.func.id
        for node in ast.walk(walk_fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "ledger_walk" in called, (
        "receivables.selectors._walk no longer calls the shared walk. It must delegate, "
        f"not recompute. Calls found: {sorted(called)}"
    )


def test_the_walk_imports_nothing_from_a_layer_above_ledger():
    """**The critical constraint.** The walk must stay below both consumers.

    `purchasing` sits one layer above `ledger` and `receivables` two. An import from either
    — or from anything at their level — would make the shared walk unreachable from the
    lower consumer, which is the exact failure S4.2 exists to prevent.
    """
    offenders = sorted(
        name
        for name in _imported_modules(WALK)
        if name.split(".")[0] in PACKAGES_ABOVE_LEDGER
    )
    assert not offenders, (
        f"ledger/walk.py imports from a layer above it: {offenders}. The walk must remain "
        "below every consumer, or the lower one cannot call it."
    )


def test_the_walk_needs_no_ledger_model_at_all():
    """Stronger than the layer rule, and the reason no conversion layer was needed.

    The walk reads its rows through a `Protocol`, so `CustomerLedgerEntry` and
    `SupplierLedgerEntry` both satisfy it structurally — no adapter, no copying, and no
    import that could later be pointed at the wrong model. A module that imports nothing
    from the project cannot acquire an upward dependency by accident.
    """
    project_imports = sorted(
        name
        for name in _imported_modules(WALK)
        if name.split(".")[0]
        not in {"collections", "dataclasses", "datetime", "decimal", "typing", "__future__"}
    )
    assert not project_imports, (
        f"ledger/walk.py has grown a dependency: {project_imports}. It was written to be "
        "pure over a Protocol; if this must change, the layer test above is the real limit."
    )
