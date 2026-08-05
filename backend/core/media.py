"""Media upload and retrieval (04 T-25, NFR-SEC-006).

One upload path, one validation routine, one authorisation check. Files are never
served from the filesystem — always through an authorised view, because delivery and
visit photographs are commercial evidence, not public assets.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from core.exceptions import DomainError, ValidationFailed
from core.models import MediaFile
from core.storage import get_media_storage

logger = logging.getLogger("districore.media")

# Content types accepted on upload. Sniffed, not trusted from the client header.
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

# Magic bytes, so a .php renamed to .jpg is rejected on content rather than on name.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),
)


class MediaTooLarge(DomainError):
    code, title, status = "MEDIA_TOO_LARGE", "File is too large", 413


class MediaTypeUnsupported(DomainError):
    code, title, status = "MEDIA_TYPE_UNSUPPORTED", "Unsupported file type", 422


def sniff_content_type(head: bytes) -> str | None:
    """Identify a file from its leading bytes.

    The Content-Type header is supplied by the client and therefore is not evidence.
    """
    for signature, content_type in _SIGNATURES:
        if head.startswith(signature):
            if content_type == "image/webp" and b"WEBP" not in head[:16]:
                continue
            return content_type
    return None


def store_upload(*, actor: Any, upload: UploadedFile, purpose: str) -> MediaFile:
    """Validate and persist an uploaded file."""
    if purpose not in MediaFile.Purpose.values:
        raise ValidationFailed(
            "Unknown media purpose.",
            errors=[{"field": "purpose", "code": "INVALID", "message": str(purpose)}],
        )

    size = upload.size or 0
    if size <= 0:
        raise ValidationFailed(
            "The file is empty.",
            errors=[{"field": "file", "code": "EMPTY", "message": "0 bytes"}],
        )
    if size > settings.MAX_UPLOAD_BYTES:
        raise MediaTooLarge(
            f"Maximum upload size is {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )

    upload.seek(0)
    head = upload.read(32)
    upload.seek(0)
    content_type = sniff_content_type(head)
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise MediaTypeUnsupported("Only JPEG, PNG and WebP images are accepted.")

    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)

    # Relative path, never absolute: the media root must be able to move (EP-J).
    now = datetime.now(UTC)
    relative = (
        f"{purpose.lower()}/{now:%Y/%m}/{uuid.uuid4().hex}{ALLOWED_IMAGE_TYPES[content_type]}"
    )
    stored_path = get_media_storage().save(relative, upload)

    media = MediaFile.objects.create(
        storage_path=stored_path,
        original_filename=(upload.name or "")[:255],
        content_type=content_type,
        size_bytes=size,
        sha256=digest.hexdigest(),
        purpose=purpose,
        uploaded_by=actor if getattr(actor, "pk", None) else None,
    )
    logger.info(
        "media_stored",
        extra={"media_id": media.pk, "purpose": purpose, "size_bytes": size},
    )
    return media


def open_media(media: MediaFile) -> tuple[Any, str]:
    """Open a stored file for streaming through an authorised view."""
    storage = get_media_storage()
    if not storage.exists(media.storage_path):
        raise ValidationFailed(
            "The stored file is missing.",
            errors=[{"field": "media", "code": "MISSING", "message": media.storage_path}],
        )
    return storage.open(media.storage_path, "rb"), media.content_type


def absolute_media_path(media: MediaFile) -> Path:
    """Resolved path on disk. For operations only — never exposed to a client."""
    return Path(settings.MEDIA_ROOT) / media.storage_path
