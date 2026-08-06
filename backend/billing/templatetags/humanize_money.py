"""Amount in words, in the Indian numbering system.

A GST invoice conventionally states the payable amount in words. Django's ``humanize``
uses the short scale (million, billion); Indian invoices use lakh and crore, so this is
not a formatting preference — an invoice reading "one million" where the trade expects
"ten lakh" invites a query.

Pure presentation: no rule here changes a stored value.
"""

from __future__ import annotations

from decimal import Decimal

from django import template

register = template.Library()

_ONES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

# Indian grouping: the last three digits, then pairs. 12,34,567 = twelve lakh ...
_SCALES: tuple[tuple[int, str], ...] = (
    (10_000_000, "crore"),
    (100_000, "lakh"),
    (1_000, "thousand"),
)


def _under_thousand(value: int) -> str:
    parts: list[str] = []
    if value >= 100:
        parts.append(f"{_ONES[value // 100]} hundred")
        value %= 100
        if value:
            parts.append("and")
    if value >= 20:
        tens = _TENS[value // 10]
        parts.append(f"{tens}-{_ONES[value % 10]}" if value % 10 else tens)
    elif value:
        parts.append(_ONES[value])
    return " ".join(parts)


def _in_words(value: int) -> str:
    if value == 0:
        return "zero"
    parts: list[str] = []
    for scale, name in _SCALES:
        if value >= scale:
            parts.append(f"{_in_words(value // scale)} {name}")
            value %= scale
    if value:
        parts.append(_under_thousand(value))
    return " ".join(parts)


@register.filter
def rupees_in_words(amount: Decimal | None) -> str:
    """``1840.80`` becomes ``Rupees one thousand eight hundred and forty and 80 paise only``."""
    if amount is None:
        return ""
    amount = Decimal(amount)
    negative = amount < 0
    amount = abs(amount)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)

    words = f"Rupees {_in_words(rupees)}"
    if paise:
        words += f" and {_in_words(paise)} paise"
    if negative:
        words = f"Minus {words[0].lower()}{words[1:]}"
    return f"{words} only".replace("  ", " ").capitalize()
