"""Media validation (04 T-25, NFR-SEC-006)."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.exceptions import ValidationFailed
from core.media import (
    MediaTooLarge,
    MediaTypeUnsupported,
    open_media,
    sniff_content_type,
    store_upload,
)
from core.models import MediaFile
from inventory.services import create_reason_code

pytestmark = pytest.mark.django_db

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 48


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.mark.parametrize(
    ("head", "expected"),
    [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp"), (b"GIF89a", None)],
)
def test_content_type_is_sniffed_from_bytes(head, expected):
    """The Content-Type header is client-supplied and therefore is not evidence."""
    assert sniff_content_type(head) == expected


def test_stores_a_valid_image(owner):
    upload = SimpleUploadedFile("shop.jpg", JPEG, content_type="image/jpeg")
    media = store_upload(actor=owner, upload=upload, purpose=MediaFile.Purpose.PRODUCT_IMAGE)
    assert media.content_type == "image/jpeg"
    assert media.sha256
    assert media.uploaded_by == owner
    # Relative path, never absolute: the media root must be able to move (EP-J).
    assert not media.storage_path.startswith("/")
    assert media.storage_path.startswith("product_image/")


def test_a_renamed_executable_is_rejected_on_content(owner):
    """Extension and header both say image; the bytes do not."""
    upload = SimpleUploadedFile("evil.jpg", b"<?php echo 1; ?>", content_type="image/jpeg")
    with pytest.raises(MediaTypeUnsupported):
        store_upload(actor=owner, upload=upload, purpose=MediaFile.Purpose.PRODUCT_IMAGE)


def test_oversized_upload_is_rejected(owner, settings):
    settings.MAX_UPLOAD_BYTES = 32
    upload = SimpleUploadedFile("big.jpg", JPEG, content_type="image/jpeg")
    with pytest.raises(MediaTooLarge):
        store_upload(actor=owner, upload=upload, purpose=MediaFile.Purpose.PRODUCT_IMAGE)


def test_empty_upload_is_rejected(owner):
    upload = SimpleUploadedFile("empty.jpg", b"", content_type="image/jpeg")
    with pytest.raises(ValidationFailed):
        store_upload(actor=owner, upload=upload, purpose=MediaFile.Purpose.PRODUCT_IMAGE)


def test_unknown_purpose_is_rejected(owner):
    upload = SimpleUploadedFile("x.png", PNG, content_type="image/png")
    with pytest.raises(ValidationFailed):
        store_upload(actor=owner, upload=upload, purpose="WHATEVER")


def test_stored_file_can_be_reopened(owner):
    upload = SimpleUploadedFile("x.png", PNG, content_type="image/png")
    media = store_upload(actor=owner, upload=upload, purpose=MediaFile.Purpose.PRODUCT_IMAGE)
    handle, content_type = open_media(media)
    assert content_type == "image/png"
    assert handle.read().startswith(b"\x89PNG")


def test_missing_file_on_disk_is_reported(owner):
    media = MediaFile.objects.create(
        storage_path="product_image/gone.jpg",
        content_type="image/jpeg",
        size_bytes=10,
        purpose=MediaFile.Purpose.PRODUCT_IMAGE,
    )
    with pytest.raises(ValidationFailed):
        open_media(media)


def test_reason_codes_are_owner_maintained(owner):
    reason = create_reason_code(actor=owner, code="rat", name="Rat damage", direction="OUT")
    assert reason.code == "RAT"
    assert reason.is_system is False
