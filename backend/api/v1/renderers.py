"""Content negotiation for `?format=csv` (05 §9.11, FR-RPT-012).

**Why this file has to exist.** `format` is not an ordinary query parameter to DRF — it is
`URL_FORMAT_OVERRIDE`, and `DefaultContentNegotiation.select_renderer` filters the view's
renderer list down to those whose ``format`` matches it. With `JSONRenderer` as the only
configured renderer, `?format=csv` filters that list to nothing and
``filter_renderers`` raises **``Http404``**.

That is why every report endpoint answered 404 rather than 406: negotiation happens in
``APIView.initial()``, so the view never ran and the endpoint looked missing rather than
unacceptable. Registering a renderer whose ``format`` is ``"csv"`` is what makes the frozen
`?format=csv` contract negotiable at all.

**It renders a string the domain already produced.** ``reporting.csv.render`` is the one
CSV mechanism (I-5, M7-2); a second implementation here — one that walked the rows itself —
would be precisely the duplication that lets an export drift from its screen.
"""

from __future__ import annotations

from typing import Any

from rest_framework.renderers import BaseRenderer


class CsvRenderer(BaseRenderer):
    """Passes through CSV text produced by ``reporting.csv.render``."""

    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"

    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: dict[str, Any] | None = None,
    ) -> str:
        """``data`` is already CSV text. Anything else is a programming error, not input.

        Returning ``str(data)`` rather than raising keeps a mistake here from turning into
        a 500 on an owner's export, while still producing something obviously wrong rather
        than something plausibly wrong.
        """
        return data if isinstance(data, str) else str(data)
