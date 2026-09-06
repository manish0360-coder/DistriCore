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

import enum
from dataclasses import dataclass, field
from datetime import date
from typing import Any


class ColumnKind(enum.Enum):
    """What a column's values *mean* — not how any one surface renders them.

    **TD-36 is why this is a kind rather than a flag.** ``numeric: bool`` said only that a
    value was a number, and three consumers needed three different answers from it: the
    screen wanted alignment, the CSV writer wanted to know whether to apply its formula
    guard, and ``api.v1.report_views._as_json`` needed to know whether the value crosses the
    wire as a string (`05` **AD-02**) or as a JSON integer. A boolean cannot answer the
    third: ``rank``, ``oldest_days`` and the sync counters are numbers that are **not**
    money or quantity, and stringifying them would break AD-02's intent in the opposite
    direction.

    So the column carries its meaning once and each surface derives its own behaviour:

    * ``TEXT``     — a label, code, date or free string. Formula-guarded in CSV.
    * ``COUNT``    — a whole number of *things*: orders, documents, days, a rank, a
      per-status operation count. Exact in JSON already, so it stays a JSON integer.
    * ``MONEY``    — `04` §1.6 ``NUMERIC(14,2)``.
    * ``QUANTITY`` — `04` §1.6 ``NUMERIC(14,3)``.
    * ``RATE``     — a percentage at two places (``core.fields.to_percent``).

    The last three are `Decimal`, and a `Decimal` rendered as a JSON number becomes an
    IEEE-754 double. That is the defect TD-36 records; the kind is what lets the delivery
    layer prevent it without a per-report branch.

    **This enum says nothing about the wire.** The mapping from kind to wire form lives in
    the API layer, where it belongs — `reporting` owns what a number *is*, not how it
    travels.
    """

    TEXT = "TEXT"
    COUNT = "COUNT"
    MONEY = "MONEY"
    QUANTITY = "QUANTITY"
    RATE = "RATE"


@dataclass(frozen=True)
class Column:
    """One column of a report.

    ``kind`` is not decoration. It selects the alignment on screen, it decides whether the
    CSV writer applies its formula guard — a guard that must never touch a negative number,
    whose leading ``-`` is arithmetic rather than injection — and it decides the JSON wire
    form (`05` AD-02).
    """

    key: str
    label: str
    kind: ColumnKind = ColumnKind.TEXT

    @property
    def numeric(self) -> bool:
        """Right-align on screen; skip the CSV formula guard.

        **Derived, never stored.** It was a constructor argument until TD-36, and a stored
        flag beside a stored kind is two sources of truth that drift the first time someone
        edits one of them. Every existing caller keeps working and the CSV output is
        byte-identical, because this returns exactly what ``numeric=True`` used to mean.
        """
        return self.kind is not ColumnKind.TEXT


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
