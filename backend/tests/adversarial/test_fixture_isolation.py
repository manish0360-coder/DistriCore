"""**A factory sequence must not walk a namespace a fixture hard-codes.**

Found by the first full `make verify` run of TD-36, as an *error* rather than a failure:

    test_a_retailer_cannot_dispatch
    duplicate key value violates unique constraint "customer_code_key"
    Key (code)=(C-0142) already exists.

`factory.Sequence`'s counter is **global to the pytest process** and does not reset between
tests. ``CustomerFactory`` generated ``C-{n:04d}``; ``credit_customer`` pins **C-0142** — the
M7 design review's worked scenario — and ``other_zone_customer`` pins **C-9999**. So the
143rd anonymous customer in a session was guaranteed to collide, and the only question was
which milestone would add the case that reached it. TD-36 added twenty-six.

**Nothing in TD-36 caused this**, and nothing before it was wrong either: the suite simply
had not yet been long enough. That is the property worth a contract — a latent collision that
depends on test *count* is invisible until it is expensive, and it reappears the moment
somebody adds a hand-written code back into the generated namespace.

**This suite needs no database.** It reasons about the sequence functions and the literals in
the test tree, so it cannot itself be the thing that runs out of numbers.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.adversarial

TESTS = Path(__file__).resolve().parent.parent

#: How far a single session could plausibly push a global counter. The real bound is the
#: number of objects the suite creates; 20 000 is far past it and costs nothing to check.
HORIZON = 20_000


def _factory_sequences() -> dict[str, str]:
    """``CustomerFactory`` -> ``"C-T{n:04d}"``, read from the source rather than assumed.

    Parsed with AST because the point is to notice a *change* to the format string. A test
    that restated the format would agree with itself for ever.
    """
    tree = ast.parse((TESTS / "factories.py").read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        for stmt in cls.body:
            if (
                isinstance(stmt, ast.Assign)
                and getattr(stmt.targets[0], "id", None) == "code"
                and isinstance(stmt.value, ast.Call)
                and getattr(stmt.value.func, "attr", None) == "Sequence"
            ):
                lam = stmt.value.args[0]
                assert isinstance(lam, ast.Lambda), f"{cls.name}: Sequence takes a lambda"
                found[cls.name] = ast.unparse(lam.body)
    return found


def _generated(expression: str, count: int) -> set[str]:
    """Every code the sequence would emit for ``n`` in ``range(count)``."""
    produce = eval(f"lambda n: {expression}")  # noqa: S307 — our own source, parsed above
    return {produce(n) for n in range(count)}


def _hand_written_codes() -> set[str]:
    """Every ``code="..."`` literal anywhere under ``tests/``.

    Deliberately broad. A collision does not care whether the literal is in a fixture, a
    service call or an assertion — it only cares that the string exists in a table with a
    unique index on it.
    """
    literals: set[str] = set()
    for path in TESTS.rglob("*.py"):
        if path.name == "factories.py":
            continue
        for match in re.finditer(r"""\bcode=["']([^"']+)["']""", path.read_text(encoding="utf-8")):
            literals.add(match.group(1))
    return literals


def test_the_factory_cannot_collide_with_a_hand_written_code():
    """**The contract.** No sequence may ever emit a code the suite also writes by hand."""
    hand_written = _hand_written_codes()
    assert hand_written, "no hand-written codes found — this contract would be vacuous"

    sequences = _factory_sequences()
    assert sequences, "no factory code sequences found — the AST reader has drifted"

    collisions = {
        name: sorted(_generated(expression, HORIZON) & hand_written)
        for name, expression in sequences.items()
    }
    offenders = {name: codes for name, codes in collisions.items() if codes}

    assert not offenders, (
        "a factory sequence walks a namespace the suite hard-codes, so the Nth anonymous "
        f"object will collide on a unique index: {offenders}. Reserve a prefix for the "
        "generated codes rather than moving the literal — the literals trace to the corpus."
    )


def test_the_customer_sequence_still_reaches_the_number_that_collided():
    """Anti-vacuity, and it names the exact failure.

    If the horizon above were too small, or the reader returned nothing, the contract would
    pass while checking a range the suite never reaches. This pins the one case that
    actually fired: the 143rd anonymous customer must no longer be ``C-0142``.
    """
    expression = _factory_sequences()["CustomerFactory"]
    produce = eval(f"lambda n: {expression}")  # noqa: S307

    assert produce(142) != "C-0142", "the 143rd anonymous customer still collides"
    assert produce(9999) != "C-9999", "other_zone_customer's code is still reachable"
    assert len({produce(n) for n in range(HORIZON)}) == HORIZON, "the sequence is not injective"


def test_the_contract_catches_the_collision_it_was_written_for():
    """Mutation. The rule must fail against the sequence that shipped before this fix.

    Without this, ``_generated`` could return an empty set and every assertion above would
    pass — the construction every adversarial suite in this tree uses.
    """
    old = '"C-" + f"{n:04d}"'  # what `factories.py` carried before this commit
    assert "C-0142" in _generated(old, HORIZON), "the reader cannot reproduce the old defect"
    assert "C-0142" in _hand_written_codes(), "C-0142 is no longer hand-written; revisit this"

    collisions = _generated(old, HORIZON) & _hand_written_codes()
    assert collisions >= {"C-0142", "C-9999"}, (
        f"the rule would not have caught the shipped collision: {sorted(collisions)}"
    )
