"""The one CSV mechanism (M7 task 2, I-5, M7-2).

These tests need no database. The renderer takes a ``ReportTable`` and returns text; if it
ever needed a query, I-5 would already be broken.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from reporting import csv as report_csv
from reporting.tables import Column, ColumnKind, ReportTable


def _table(**overrides) -> ReportTable:
    defaults = {
        "key": "sales",
        "title": "Sales",
        "columns": (
            Column("label", "Date"),
            Column("sales", "Sales", kind=ColumnKind.MONEY),
        ),
        "rows": (
            {"label": date(2026, 8, 1), "sales": Decimal("2400.00")},
            {"label": date(2026, 8, 2), "sales": Decimal("-200.00")},
        ),
        "total": {"label": "Total", "sales": Decimal("2200.00")},
        "definition": "Sales = taxable value, net of credit notes.",
        "date_from": date(2026, 8, 1),
        "date_to": date(2026, 8, 31),
    }
    return ReportTable(**{**defaults, **overrides})


def test_the_header_carries_the_definition_into_the_file():
    """M7-1: a figure whose meaning lives only on the screen becomes folklore when emailed."""
    output = report_csv.render(_table())
    assert "# Sales = taxable value, net of credit notes." in output


def test_a_definition_containing_commas_stays_a_comment():
    """The regression that broke I-5.

    Header lines were written through the CSV writer, which quotes any field containing a
    comma — and the real sales definition contains three. The line then began with ``"``
    instead of ``#``, so nothing reading the file back could tell prose from data.
    """
    table = _table(definition="Sales = taxable value, net of credit notes, ex-GST.")
    first = report_csv.render(table).splitlines()[0]
    assert first.startswith(report_csv.COMMENT_PREFIX)
    for line in report_csv.render(table).splitlines():
        assert not line.startswith('"#'), line


def test_a_header_line_cannot_smuggle_a_row_break():
    """A shop name is typed by a human, and the statement puts it in the title."""
    table = _table(title="Statement\nfor\r\nSharma Stores")
    rendered = report_csv.render(table).splitlines()
    assert rendered[0] == "# Statement for Sharma Stores"


def test_the_header_states_that_both_dates_are_included():
    """M7-3. The owner reconciles by hand; an ambiguous bound invalidates the exercise."""
    assert "2026-08-01 to 2026-08-31 (both dates included)" in report_csv.render(_table())


def test_rows_and_total_render_in_column_order():
    body = report_csv.render(_table()).splitlines()
    assert body[-4] == "Date,Sales"
    assert body[-3] == "2026-08-01,2400.00"
    assert body[-2] == "2026-08-02,-200.00"
    assert body[-1] == "Total,2200.00"


def test_decimals_keep_their_scale():
    """A trailing zero is not noise — 04 §1.6 makes the string form canonical."""
    assert "2400.00" in report_csv.render(_table())


def test_a_negative_number_is_not_quoted():
    """The formula guard must never touch arithmetic.

    A leading "-" on a numeric column is a negative figure. Quoting it to defend against
    CSV injection would corrupt the very number the guard exists to protect.
    """
    assert "'-200.00" not in report_csv.render(_table())


def test_a_text_cell_that_looks_like_a_formula_is_neutralised():
    """The owner opens these in Excel, and a customer name is caller-supplied text."""
    table = _table(rows=({"label": "=cmd|'/c calc'!A1", "sales": Decimal("1.00")},), total=None)
    line = report_csv.render(table).splitlines()[-1]
    assert line.startswith("'=cmd"), "the leading = was left executable"


def test_every_formula_prefix_is_neutralised():
    """`=` is the obvious one; `+`, `@` and a leading tab are the ones that get forgotten."""
    for hostile in ("=1+1", "+1", "@SUM(A1)", "\t=1"):
        table = _table(rows=({"label": hostile, "sales": Decimal("1.00")},), total=None)
        cell = report_csv.render(table).splitlines()[-1]
        assert cell.startswith(("'", '"\'')), hostile


def test_none_renders_empty_never_the_word_none():
    table = _table(rows=({"label": None, "sales": None},), total=None)
    assert report_csv.render(table).splitlines()[-1] == ","


def test_screen_and_file_read_from_the_same_header_lines():
    """I-5 at the header level: the screen renders exactly what the file carries."""
    table = _table()
    rendered = report_csv.render(table)
    for line in report_csv.header_lines(table):
        assert f"# {line}" in rendered


def test_the_filename_carries_the_period():
    assert report_csv.filename(_table()) == "sales-2026-08-01_2026-08-31.csv"


def test_an_as_at_report_names_the_instant_instead():
    table = _table(date_from=None, date_to=None, as_of=date(2026, 8, 8), key="stock-position")
    assert report_csv.filename(table) == "stock-position-2026-08-08.csv"
    assert "# As at: 2026-08-08" in report_csv.render(table)


def test_an_empty_report_still_carries_its_header_and_columns():
    """A period with no activity is an answer, not a blank file."""
    output = report_csv.render(_table(rows=(), total=None))
    assert "# Sales" in output
    assert output.strip().endswith("Date,Sales")


# ------------------------------------------------------------------------ the shared shape
def test_cells_pairs_every_value_with_its_column():
    """The screen aligns on ``Column.numeric``, so the pairing must survive to the template."""
    rows = _table().cells()
    assert len(rows) == 2
    assert [column.key for column, _ in rows[0]] == ["label", "sales"]
    assert rows[0][1] == (_table().columns[1], Decimal("2400.00"))


def test_total_cells_is_empty_rather_than_none_when_there_is_no_total():
    """A template iterating ``None`` is a 500; iterating an empty tuple is a blank row."""
    assert _table(total=None).total_cells() == ()


def test_a_balance_report_is_point_in_time_and_a_period_report_is_not():
    assert not _table().is_point_in_time
    assert _table(date_from=None, date_to=None, as_of=date(2026, 8, 8)).is_point_in_time


def test_a_missing_key_renders_blank_rather_than_raising():
    """A total that omits a dimension column is normal — see every report's total row."""
    table = _table(rows=({"sales": Decimal("1.00")},), total=None)
    assert report_csv.render(table).splitlines()[-1] == ",1.00"
