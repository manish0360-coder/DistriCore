"""The shared row shape every report produces (M7 task 2, I-5).

**One query, two renderings.** A report selector returns a ``ReportTable``; the screen and
the CSV are two views of that one object. Neither re-queries, so I-5 — *CSV content is
screen content, row for row and figure for figure* — holds by construction rather than by
discipline.

That is the whole reason this file exists. If each report returned its own shape, the CSV
renderer would need a branch per report, and the first divergence between screen and export
would be a one-line change nobody noticed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Column:
    """One column of a report.

    ``numeric`` is not decoration. It selects the alignment on screen, and it decides
    whether the CSV writer applies its formula guard — a guard that must never touch a
    negative number, whose leading ``-`` is arithmetic rather than injection.
    """

    key: str
    label: str
    numeric: bool = False


@dataclass(frozen=True)
class ReportTable:
    """A rendered report, before it is rendered.

    ``definition`` travels with the data deliberately (M7-1). A sales figure whose meaning
    lives only in someone's memory becomes folklore the first time it is emailed; a figure
    that carries its own definition into the CSV cannot.
    """

    key: str
    title: str
    columns: tuple[Column, ...]
    rows: tuple[dict[str, Any], ...] = ()
    definition: str = ""
    notes: tuple[str, ...] = ()
    total: dict[str, Any] | None = None
    date_from: date | None = None
    date_to: date | None = None
    as_of: date | None = None
    #: Filled by the selector when a grouping was applied, so the export names it.
    group_by: str = ""

    def column(self, key: str) -> Column | None:
        for column in self.columns:
            if column.key == key:
                return column
        return None

    @property
    def is_point_in_time(self) -> bool:
        """True for a balance report (stock, receivables), false for a period report.

        The screen needs this to choose between an "as at" field and a from/to pair. Asking
        the shape is better than assembling the same three-way condition in a template,
        where it cannot be unit-tested.
        """
        return self.as_of is not None and self.date_from is None and self.date_to is None

    def cells(self) -> tuple[tuple[tuple[Column, Any], ...], ...]:
        """Rows as ``(column, value)`` pairs, in column order.

        The screen needs each cell paired with its column to know whether to align it
        right. Doing that with a dictionary-lookup template filter would put an untested
        helper between the data and the page; a method on the shape itself keeps the
        pairing where the shape is defined, and Django templates unpack tuples natively.
        """
        return tuple(
            tuple((column, row.get(column.key)) for column in self.columns) for row in self.rows
        )

    def total_cells(self) -> tuple[tuple[Column, Any], ...]:
        if self.total is None:
            return ()
        return tuple((column, self.total.get(column.key)) for column in self.columns)


@dataclass(frozen=True)
class Metric:
    """One dashboard number (D-4).

    ``is_live`` marks a figure that describes *today* and is therefore **not reproducible**
    — ask again in an hour and it may differ. I-6 does not apply to it, and it is the reason
    the dashboard offers no CSV: a non-reproducible figure must not acquire the authority of
    a document.
    """

    key: str
    label: str
    value: Any
    caption: str = ""
    is_live: bool = False
    is_money: bool = True


@dataclass(frozen=True)
class Dashboard:
    """Exactly four numbers (D-4, M7-8). **Not exportable.**

    M7 called this "not an endpoint" as well. M8 §3.4.1 overturned the first half and kept
    the second: Owner Companion Mode needs the four numbers on a phone, and while three
    were already reachable from the report endpoints, ``collected_today`` was not — only a
    paginated payment list, which the device would have had to page and sum. The objection
    in M7 §8.2 was that a non-reproducible figure must not acquire the authority of a
    *document* — an argument about export, which still holds. See ``api.v1.report_views``.
    """

    metrics: tuple[Metric, ...] = field(default_factory=tuple)
    as_of: date | None = None
