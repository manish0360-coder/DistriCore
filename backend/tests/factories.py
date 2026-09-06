"""Test data construction.

Hand-built fixtures rot and become a maintenance tax; factories do not (00 §3.3).
"""

from __future__ import annotations

from decimal import Decimal

import factory
from django.utils import timezone

from catalogue.models import Product
from customers.models import Customer, Zone
from identity.models import OtpRequest, Role, User, UserRole
from inventory.models import ReasonCode, StockLocation


class RoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Role
        django_get_or_create = ("code",)

    code = "OWNER"
    name = "Owner"
    is_system = True


class UserFactory(factory.django.DjangoModelFactory):
    """Builds users **through the manager production uses** (TD-30).

    ``DjangoModelFactory`` calls ``Manager.create()`` by default, which never reaches
    ``UserManager._create`` and therefore never applies the write-path rules. That gap hid
    two defects in a row — phone numbers stored uncanonicalised, and the owner-bootstrap
    deadlock — because factory phones were already canonical and factory users already had
    roles. **A clean install could fail while the suite stayed green, and did.**
    """

    class Meta:
        model = User
        skip_postgeneration_save = True

    phone = factory.Sequence(lambda n: f"+9198765{n:05d}")
    full_name = factory.Faker("name")
    language = "hi"
    is_active = True
    #: A plain declaration rather than a `post_generation` hook, so it reaches
    #: `create_user` as an argument instead of being written over the top afterwards.
    #: ``None`` means an unusable hash — what production gives a retailer who logs in by
    #: OTP alone.
    password = None

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """The single line that makes this factory faithful.

        Anything that reverts this to ``Manager.create()`` is reintroducing the blind
        spot; ``tests/unit/test_factories.py`` fails immediately if it does.
        """
        password = kwargs.pop("password", None)
        return model_class.objects.create_user(*args, password=password, **kwargs)

    @factory.post_generation
    def roles(obj, create, extracted, **kwargs):
        """**A fixture convenience, not a claim about production.**

        Production grants roles through `identity.services.grant_role` (which requires an
        OWNER) or `bootstrap_owner` (which does not, and refuses once one exists). Routing
        this through them would make every fixture that merely needs a salesman carry an
        owner, and would make fixtures order-dependent.

        Those two paths are covered directly instead — `test_authorization_matrix.py` and
        `test_identity_bootstrap.py`, the latter including the deadlock itself. See
        `docs/TD-30_Factory_Creation_Path_Note.md` §3.
        """
        if not create:
            return
        for code in extracted or []:
            role, _ = Role.objects.get_or_create(
                code=code, defaults={"name": code.title(), "is_system": True}
            )
            UserRole.objects.get_or_create(app_user=obj, role=role)
        obj.__dict__.pop("_role_codes", None)


class OtpRequestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OtpRequest

    phone = "+919876500000"
    code_hash = "unusable"
    purpose = OtpRequest.Purpose.LOGIN
    expires_at = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(minutes=10))


class ZoneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Zone

    name = factory.Sequence(lambda n: f"Zone {n}")
    road_name = "Station Road"
    pin_code = "800001"
    city = "Patna"


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Customer

    # **`C-T`, not `C-`, and the prefix is the fix.**
    #
    # `factory.Sequence`'s counter is global to the pytest process and does not reset per
    # test, so `C-{n:04d}` walks the same namespace two fixtures hard-code from:
    # `credit_customer` pins **C-0142** (the M7 design review's worked scenario) and
    # `other_zone_customer` pins **C-9999**. The 143rd anonymous customer in a session
    # therefore collided with C-0142 on `customer_code_key` — a latent, order-dependent
    # failure that fired the moment TD-36's new cases pushed the counter past 142.
    #
    # Reserving a prefix the hand-written codes do not use makes the collision structurally
    # impossible instead of merely unlikely, and keeps C-0142 traceable to the corpus.
    # `test_the_factory_cannot_collide_with_a_hand_written_code` holds it.
    code = factory.Sequence(lambda n: f"C-T{n:04d}")
    shop_name = factory.Faker("company")
    phone = factory.Sequence(lambda n: f"+9188888{n:05d}")
    billing_address = "Main Bazaar, Patna"


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    code = factory.Sequence(lambda n: f"P-{n:04d}")
    name = factory.Faker("word")
    selling_price = Decimal("100.00")
    tax_rate_percent = Decimal("18.00")
    hsn_code = "34012000"
    pack_size = 12


class ReasonCodeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReasonCode
        django_get_or_create = ("code",)

    code = "DAMAGE"
    name = "Damaged goods"
    direction = "OUT"
    is_restockable = False


class StockLocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StockLocation
        django_get_or_create = ("code",)

    code = "MAIN"
    name = "Main Warehouse"
    is_default = True
