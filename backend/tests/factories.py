"""Test data construction.

Hand-built fixtures rot and become a maintenance tax; factories do not (00 §3.3).
"""

from __future__ import annotations

import factory
from django.utils import timezone

from identity.models import OtpRequest, Role, User, UserRole


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
