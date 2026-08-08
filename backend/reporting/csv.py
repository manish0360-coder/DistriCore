"""CSV rendering — **one mechanism, every report** (M7 task 2, I-5, M7-2).

There is exactly one writer here and it takes a ``ReportTable``. No report brings its own
exporter, because the moment two exporters exist the screen and the export can disagree,
and the export is the artefact that leaves the building.

**The header block is part of the contract.** FR-RPT-012 makes every report exportable, and
M7-1 makes the definition of a figure irreversible; a CSV that carries the numbers without
the definition is how a figure becomes folklore. Period, definition and footnotes are
written above the column row so the file explains itself to a reader who has never seen the
screen it came from.

Stdlib ``csv`` resolves absolutely under Python 3, so this module's name does not shadow it.
"""

from __future__ import annotations

import csv as _csv
import io
from datetime import date
from decimal import Decimal
from typing import Any

from reporting.tables import Column, ReportTable

#: Characters that make a spreadsheet treat a cell as a formula rather than as text.
#: The owner opens these files in Excel; a text cell that begins with one of these is a
#: code-execution vector (OWASP CSV injection), and the data can come from a customer name
#: or a reason code the owner typed. Applied to TEXT columns only — a numeric column's
#: leading "-" is arithmetic, and quoting it would corrupt the figure it protects.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _format(value: Any) -> str:
    """Canonical string form. Decimals keep their scale; ``None`` is empty, never "None"."""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _cell(value: Any, column: Column) -> str:
    text = _format(value)
    if column.numeric:
        return text
    if text.startswith(_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def _one_line(text: str) -> str:
    """Collapse to a single line of single spaces.

    A header line is a comment, and a comment that contains a newline stops being one — it
    becomes a data row halfway down the file. Most of these sentences are constants, but
    the statement's title carries a customer's shop name, which is typed by a human.
    """
    return " ".join(str(text).split())


def header_lines(table: ReportTable) -> list[str]:
    """The self-describing block above the column row.

    Exposed separately so the screen can render the same sentences the export carries. The
    two must not drift: a definition shown on screen and absent from the file is the same
    defect as two implementations of one number, one layer up.
    """
    lines = [table.title]
    if table.date_from is not None or table.date_to is not None:
        start = _format(table.date_from) or "the beginning"
        end = _format(table.date_to) or "today"
        # M7-3: both ends inclusive, on business dates, never timestamps.
        lines.append(f"Period: {start} to {end} (both dates included)")
    if table.as_of is not None:
        lines.append(f"As at: {_format(table.as_of)}")
    if table.group_by:
        lines.append(f"Grouped by: {table.group_by}")
    if table.definition:
        lines.append(table.definition)
    lines.extend(table.notes)
    return [_one_line(line) for line in lines]


#: Marks a line as prose rather than data. Written verbatim, never through the CSV writer.
COMMENT_PREFIX = "# "


def render(table: ReportTable) -> str:
    """A ``ReportTable`` as CSV text.

    Rows are written in the order the selector produced them. Sorting here would make the
    export disagree with the screen for no benefit, which is precisely what I-5 forbids.

    **The header block is written verbatim, not through the CSV writer.** Passing it
    through quoted every sentence that contained a comma — and the sales definition
    contains three — so the line began with ``"`` instead of ``#`` and stopped being
    recognisable as a comment to anything reading the file back. Header lines are prose,
    not a one-column row, and ``_one_line`` has already made them safe to write directly.
    """
    buffer = io.StringIO()
    writer = _csv.writer(buffer, lineterminator="\n")

    for line in header_lines(table):
        buffer.write(f"{COMMENT_PREFIX}{line}\n")
    if table.columns:
        writer.writerow([column.label for column in table.columns])

    for row in table.rows:
        writer.writerow([_cell(row.get(column.key), column) for column in table.columns])

    if table.total is not None:
        writer.writerow([_cell(table.total.get(column.key), column) for column in table.columns])

    return buffer.getvalue()


def filename(table: ReportTable) -> str:
    """A stable, sortable download name. The period is in the name, not only in the file."""
    parts = [table.key]
    if table.date_from is not None or table.date_to is not None:
        parts.append(f"{_format(table.date_from) or 'start'}_{_format(table.date_to) or 'today'}")
    elif table.as_of is not None:
        parts.append(_format(table.as_of))
    return "-".join(parts) + ".csv"
