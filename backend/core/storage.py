"""Storage seam (EP-J).

Media paths are always relative and access is always mediated by an authorised view
(04 T-25, NFR-SEC-006). Because of those two properties, moving to object storage in
Edition 2 is a settings change rather than a data migration.

M0 defines the seam only. Upload handling arrives with media in M1.
"""

from __future__ import annotations

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage


def get_media_storage() -> Storage:
    """The single place the storage backend is resolved."""
    return FileSystemStorage(location=str(settings.MEDIA_ROOT))
