"""Page-number pagination for list endpoints (AD-10).

Sync uses a ``since`` cursor instead, because offset pagination silently skips rows
when the underlying set changes mid-pagination — the failure that loses a transaction.
"""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
