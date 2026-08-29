"""Owner supplier-payment screens (FR-PUR-012, D5 S4.3, surface `S1`).

The rules are asserted in `tests/unit/test_supplier_payment_services.py` and E3 in
`tests/adversarial/test_supplier_payment_idempotency.py`; these assert the delivery layer is
wired to them — and, crucially, that **the browser can actually reach the duplicate
protection**, which a service-level test cannot show.

Fixtures are model-level so `test_the_screens_require_a_login` receives an unauthenticated
client: pytest-django hands every test the same `client` instance, so a fixture that logs in
would mutate it.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

GO_LIVE = date(2026, 4, 1)
PAID_ON = "2026-08-02"

#: The hidden field the form must carry for E3 to work at all.
SUBMISSION_FIELD = re.compile(
    rb'name="submission_id"\s+value="([0-9a-fA-F-]{36})"'
)


@pytest.fixture
def signed_in(client, owner):
    client.post("/login/", {"phone": owner.phone, "password": "owner-password-123"})
    return client


@pytest.fixture
def supplier(owner):
    from purchasing.services import create_supplier, load_supplier_opening_balance

    made = create_supplier(
        actor=owner,
        code="acme",
        name="Acme Distributors",
        phone="+919876500011",
        billing_address="Industrial Estate",
    )
    load_supplier_opening_balance(
        actor=owner, supplier=made, amount="12500.00", entry_date=GO_LIVE
    )
    return made


def _submission_id(response) -> str:
    match = SUBMISSION_FIELD.search(response.content)
    assert match, "the payment form carries no submission_id — E3 is unreachable from the UI"
    return match.group(1).decode()


def _post(client, supplier, submission_id, **overrides):
    data = {
        "submission_id": submission_id,
        "amount": "2500.00",
        "payment_date": PAID_ON,
        "method": "BANK",
        "reference_number": "UTR-9911",
        "notes": "",
    }
    data.update(overrides)
    return client.post(f"/suppliers/{supplier.pk}/pay/record/", data)


def test_the_form_renders_the_position_and_mints_a_submission_id(signed_in, supplier):
    response = signed_in.get(f"/suppliers/{supplier.pk}/pay/")

    assert response.status_code == 200
    assert b"12500.00" in response.content, "the owner should see what is owed before paying"
    assert _submission_id(response)


def test_two_form_renders_mint_different_ids(signed_in, supplier):
    """**The mechanism, end to end.** A new render is a new logical payment attempt."""
    first = _submission_id(signed_in.get(f"/suppliers/{supplier.pk}/pay/"))
    second = _submission_id(signed_in.get(f"/suppliers/{supplier.pk}/pay/"))

    assert first != second


def test_owner_records_a_payment_and_lands_on_it(signed_in, supplier):
    from ledger.selectors import supplier_balance
    from purchasing.models import SupplierPayment

    submission_id = _submission_id(signed_in.get(f"/suppliers/{supplier.pk}/pay/"))
    response = _post(signed_in, supplier, submission_id)

    payment = SupplierPayment.objects.get()
    assert response.status_code == 302
    assert response.url == f"/supplier-payments/{payment.pk}/"
    assert supplier_balance(supplier) == Decimal("10000.00")


def test_resubmitting_the_same_form_pays_once(signed_in, supplier):
    """**The double-click, through the browser.** Two POSTs, one payment."""
    from ledger.selectors import supplier_balance
    from purchasing.models import SupplierPayment

    submission_id = _submission_id(signed_in.get(f"/suppliers/{supplier.pk}/pay/"))
    first = _post(signed_in, supplier, submission_id)
    second = _post(signed_in, supplier, submission_id)

    assert SupplierPayment.objects.count() == 1
    assert first.url == second.url, "the replay lands on the original payment"
    assert supplier_balance(supplier) == Decimal("10000.00")


def test_loading_the_form_again_permits_a_second_identical_payment(signed_in, supplier):
    """The other half: identical amount, date and supplier, but a fresh render."""
    from ledger.selectors import supplier_balance
    from purchasing.models import SupplierPayment

    for _ in range(2):
        submission_id = _submission_id(signed_in.get(f"/suppliers/{supplier.pk}/pay/"))
        _post(signed_in, supplier, submission_id)

    assert SupplierPayment.objects.count() == 2
    assert supplier_balance(supplier) == Decimal("7500.00")


def test_a_replay_with_a_changed_amount_is_refused_and_shown(signed_in, supplier):
    from ledger.selectors import supplier_balance
    from purchasing.models import SupplierPayment

    submission_id = _submission_id(signed_in.get(f"/suppliers/{supplier.pk}/pay/"))
    _post(signed_in, supplier, submission_id)
    response = _post(signed_in, supplier, submission_id, amount="9999.00")

    assert response.status_code == 302
    assert response.url == f"/suppliers/{supplier.pk}/pay/"
    assert SupplierPayment.objects.count() == 1
    assert supplier_balance(supplier) == Decimal("10000.00")
    # The refusal reaches the owner rather than vanishing.
    assert b"reverse that payment" in signed_in.get(response.url).content


def test_a_post_without_a_submission_id_is_refused(signed_in, supplier):
    from purchasing.models import SupplierPayment

    response = _post(signed_in, supplier, "")

    assert response.status_code == 302
    assert not SupplierPayment.objects.exists()


def test_the_detail_offers_reversal_and_performs_it(signed_in, supplier):
    from ledger.selectors import supplier_balance
    from purchasing.models import SupplierPayment

    submission_id = _submission_id(signed_in.get(f"/suppliers/{supplier.pk}/pay/"))
    _post(signed_in, supplier, submission_id)
    payment = SupplierPayment.objects.get()

    detail = signed_in.get(f"/supplier-payments/{payment.pk}/")
    assert b"Reverse payment" in detail.content

    signed_in.post(
        f"/supplier-payments/{payment.pk}/reverse/",
        {"reason": "Cheque bounced", "reversal_date": "2026-08-06"},
    )
    payment.refresh_from_db()
    assert payment.is_reversed
    assert supplier_balance(supplier) == Decimal("12500.00")
    assert b"Reverse payment" not in signed_in.get(f"/supplier-payments/{payment.pk}/").content


def test_the_list_renders_and_filters(signed_in, supplier):
    from purchasing.models import SupplierPayment

    submission_id = _submission_id(signed_in.get(f"/suppliers/{supplier.pk}/pay/"))
    _post(signed_in, supplier, submission_id)
    payment = SupplierPayment.objects.get()

    assert payment.payment_number.encode() in signed_in.get("/supplier-payments/").content
    assert (
        payment.payment_number.encode()
        in signed_in.get("/supplier-payments/?method=BANK").content
    )
    assert (
        payment.payment_number.encode()
        not in signed_in.get("/supplier-payments/?method=CASH").content
    )


def test_the_screens_require_a_login(client, supplier):
    for url in (
        "/supplier-payments/",
        f"/suppliers/{supplier.pk}/pay/",
    ):
        assert client.get(url).status_code == 302
