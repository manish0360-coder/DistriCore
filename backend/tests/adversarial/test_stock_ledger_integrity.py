"""Adversarial suite for the stock ledger (00 §6.4, 02 §25.2).

These verify properties ordinary tests cannot: append-only enforcement at every layer,
and concurrency correctness under real parallel writers. NFR-INT-002 and NFR-INT-003 are
the requirements; a green happy-path suite is not evidence for either.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import connection, connections, transaction

from inventory.models import ReasonCode, StockMovement, StockMovementImmutable
from inventory.selectors import on_hand_for
from inventory.services import adjust_stock, receive_stock

pytestmark = [pytest.mark.django_db, pytest.mark.adversarial]


@pytest.fixture
def movement(owner, product, receipt_reason):
    return receive_stock(
        actor=owner, product=product, quantity=Decimal("100"), reason_code=receipt_reason
    )


# --------------------------------------------------------------------- append-only
def test_instance_save_is_refused(movement):
    movement.quantity = Decimal("999.000")
    with pytest.raises(StockMovementImmutable):
        movement.save()


def test_instance_delete_is_refused(movement):
    with pytest.raises(StockMovementImmutable):
        movement.delete()


def test_queryset_update_is_refused(movement):
    with pytest.raises(StockMovementImmutable):
        StockMovement.objects.filter(pk=movement.pk).update(quantity=Decimal("1"))


def test_queryset_delete_is_refused(movement):
    with pytest.raises(StockMovementImmutable):
        StockMovement.objects.filter(pk=movement.pk).delete()


def test_database_trigger_refuses_update_via_raw_sql(movement):
    """The last line of defence: the database says no even when the code asks."""
    with pytest.raises(Exception) as exc_info:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE stock_movement SET quantity = 1 WHERE id = %s", [movement.pk])
    assert "append-only" in str(exc_info.value).lower()


def test_database_trigger_refuses_delete_via_raw_sql(movement):
    with pytest.raises(Exception) as exc_info:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM stock_movement WHERE id = %s", [movement.pk])
    assert "append-only" in str(exc_info.value).lower()


def test_balance_survives_every_attack(movement, product):
    for attack in (
        lambda: StockMovement.objects.filter(pk=movement.pk).update(quantity=Decimal("1")),
        lambda: StockMovement.objects.filter(pk=movement.pk).delete(),
    ):
        with pytest.raises(StockMovementImmutable):
            attack()
    assert on_hand_for(product) == Decimal("100.000")


# --------------------------------------------------------------------- constraints
def test_check_constraint_rejects_a_movement_with_neither_source_nor_reason(product, location):
    """BR-007 / M2-8 in the database, bypassing the service layer entirely."""
    from django.db.utils import IntegrityError

    from inventory.services import default_lot_for

    lot = default_lot_for(product)
    with pytest.raises(IntegrityError) as exc:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO stock_movement
                      (product_id, location_id, lot_id, quantity, movement_type,
                       source_document_type, source_document_id, reason_code_id,
                       occurred_at, notes, created_at)
                    VALUES (%s, %s, %s, 5, 'ADJUSTMENT', '', NULL, NULL, now(), '', now())
                    """,
                    [product.pk, location.pk, lot.pk],
                )
    assert "ck_stock_movement_has_source" in str(exc.value)


def test_check_constraint_rejects_a_negative_receipt(product, location, receipt_reason):
    """M2-11 sign-per-type, enforced by the database."""
    from django.db.utils import IntegrityError

    from inventory.services import default_lot_for

    lot = default_lot_for(product)
    with pytest.raises(IntegrityError) as exc:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO stock_movement
                      (product_id, location_id, lot_id, quantity, movement_type,
                       source_document_type, source_document_id, reason_code_id,
                       occurred_at, notes, created_at)
                    VALUES (%s, %s, %s, -5, 'RECEIPT', '', NULL, %s, now(), '', now())
                    """,
                    [product.pk, location.pk, lot.pk, receipt_reason.pk],
                )
    assert "ck_stock_movement_sign_per_type" in str(exc.value)


def test_check_constraint_rejects_half_a_source_reference(product, location, receipt_reason):
    from django.db.utils import IntegrityError

    from inventory.services import default_lot_for

    lot = default_lot_for(product)
    with pytest.raises(IntegrityError) as exc:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO stock_movement
                      (product_id, location_id, lot_id, quantity, movement_type,
                       source_document_type, source_document_id, reason_code_id,
                       occurred_at, notes, created_at)
                    VALUES (%s, %s, %s, 5, 'RECEIPT', 'DELIVERY', NULL, %s, now(), '', now())
                    """,
                    [product.pk, location.pk, lot.pk, receipt_reason.pk],
                )
    assert "ck_stock_movement_source_pair" in str(exc.value)


# --------------------------------------------------------------------- concurrency
@pytest.mark.django_db(transaction=True)
def test_concurrent_movements_do_not_lose_updates(django_db_setup, django_db_blocker):
    """NFR-INT-002.

    A stored quantity would lose updates here: each writer reads the same balance and
    overwrites the other. Appends cannot — there is no shared mutable cell to race for,
    which is why the ledger is concurrency-safe by construction rather than by defence.
    """
    from core.permissions import Role
    from identity.models import Role as RoleModel
    from tests.factories import ProductFactory, UserFactory

    with django_db_blocker.unblock():
        for code in Role.ALL:
            RoleModel.objects.get_or_create(
                code=code, defaults={"name": code.title(), "is_system": True}
            )
        owner = UserFactory(roles=[Role.OWNER])
        product = ProductFactory()
        reason = ReasonCode.objects.get(code="COUNT_ADJ")

    threads_count = 10
    per_thread = Decimal("7")
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            adjust_stock(actor=owner, product=product, quantity=per_thread, reason_code=reason)
        except BaseException as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"concurrent writers failed: {errors[:3]}"
    assert StockMovement.objects.filter(product=product).count() == threads_count
    assert on_hand_for(product) == per_thread * threads_count  # 70.000, never less

    # transaction=True tests are cleaned by TRUNCATE, which does not fire row-level
    # triggers — so append-only enforcement and test teardown coexist (design review §5.1).


def test_derived_balance_equals_the_sum_of_rows(owner, product, receipt_reason, damage_reason):
    """NFR-INT-003: reconciliation over a randomised sequence."""
    import random

    both = ReasonCode.objects.get(code="COUNT_ADJ")
    expected = Decimal("0.000")
    random.seed(20260805)
    for _ in range(40):
        amount = Decimal(random.randint(1, 500)) / Decimal("10")
        if random.random() < 0.5:
            receive_stock(actor=owner, product=product, quantity=amount, reason_code=receipt_reason)
            expected += amount
        else:
            adjust_stock(actor=owner, product=product, quantity=-amount, reason_code=both)
            expected -= amount

    from django.db.models import Sum

    ledger_sum = StockMovement.objects.filter(product=product).aggregate(t=Sum("quantity"))["t"]
    assert on_hand_for(product) == ledger_sum
    assert on_hand_for(product) == expected.quantize(Decimal("0.001"))
