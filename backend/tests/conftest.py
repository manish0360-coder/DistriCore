"""Shared fixtures."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from core.permissions import Role
from identity.models import Role as RoleModel
from identity.sms import get_sms_provider
from tests.factories import UserFactory


@pytest.fixture
def seeded_roles(db):
    """The four system roles, as migration identity/0002 seeds them.

    Deliberately NOT autouse: a unit test of a pure function must run without a
    database (NFR-MNT-002). Fixtures that need roles depend on this one explicitly.
    """
    for code in Role.ALL:
        RoleModel.objects.get_or_create(
            code=code, defaults={"name": code.title(), "is_system": True}
        )


@pytest.fixture
def sms():
    provider = get_sms_provider()
    provider.sent.clear()
    return provider


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def owner(seeded_roles):
    return UserFactory(roles=[Role.OWNER], password="owner-password-123")


@pytest.fixture
def salesman(seeded_roles):
    """Holds SALESMAN and DELIVERY — one person, two roles (04 T-03)."""
    return UserFactory(roles=[Role.SALESMAN, Role.DELIVERY])


@pytest.fixture
def retailer(seeded_roles):
    return UserFactory(roles=[Role.RETAILER])


@pytest.fixture
def auth(api):
    """Authenticate the API client as a given user."""

    def _auth(user):
        from api.v1.auth_views import _issue_tokens

        tokens = _issue_tokens(user)
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")
        return api

    return _auth


@pytest.fixture
def zone(seeded_roles):
    from tests.factories import ZoneFactory

    return ZoneFactory()


@pytest.fixture
def customer(seeded_roles):
    from tests.factories import CustomerFactory

    return CustomerFactory()


@pytest.fixture
def product(seeded_roles):
    from tests.factories import ProductFactory

    return ProductFactory()


@pytest.fixture
def retailer_login(retailer, customer):
    """A retailer account bound to a shop — the AD-11 scoping case."""
    retailer.customer = customer
    retailer.save(update_fields=["customer"])
    retailer.__dict__.pop("_role_codes", None)
    return retailer


@pytest.fixture
def delivery_only(seeded_roles):
    """DELIVERY without SALESMAN — the narrower field role."""
    from core.permissions import Role
    from tests.factories import UserFactory

    return UserFactory(roles=[Role.DELIVERY])


@pytest.fixture
def location(db):
    """The single seeded location. Migration 0004 creates it; this fetches it."""
    from inventory.models import StockLocation

    return StockLocation.objects.get(is_default=True)


@pytest.fixture
def damage_reason(db):
    from inventory.models import ReasonCode

    return ReasonCode.objects.get(code="DAMAGE")


@pytest.fixture
def receipt_reason(db):
    from inventory.models import ReasonCode

    return ReasonCode.objects.get(code="PURCHASE_IN")


@pytest.fixture
def sales_return_reason(db):
    """The inbound code for goods coming back from a customer.

    Direction ``IN``: a physical sales return increases stock. ``DAMAGE`` is ``OUT`` and
    cannot express it — which is the reason-code direction rule (04 T-08) doing exactly
    its job. This is the code D-7's separation relies on: a credit note reverses money,
    and the goods come back through their own reason-coded movement.
    """
    from inventory.models import ReasonCode

    return ReasonCode.objects.get(code="SALES_RETURN")


@pytest.fixture
def profile(db):
    """The tier-3 configuration singleton, created on demand (M3-10)."""
    from core.services import get_business_profile

    return get_business_profile()


@pytest.fixture
def credit_customer(seeded_roles, profile):
    """A customer with a ten-thousand-rupee limit — the design review's C-0142."""
    from decimal import Decimal

    from tests.factories import CustomerFactory

    return CustomerFactory(code="C-0142", credit_limit_amount=Decimal("10000.00"))
