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
from inventory.models import ReasonCode


class RoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Role
        django_get_or_create = ("code",)

    code = "OWNER"
    name = "Owner"
    is_system = True


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    phone = factory.Sequence(lambda n: f"+9198765{n:05d}")
    full_name = factory.Faker("name")
    language = "hi"
    is_active = True

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        if create and extracted:
            obj.set_password(extracted)
            obj.save(update_fields=["password"])

    @factory.post_generation
    def roles(obj, create, extracted, **kwargs):
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

    code = factory.Sequence(lambda n: f"C-{n:04d}")
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
