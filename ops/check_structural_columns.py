#!/usr/bin/env python3
"""Structural-enabler gate (ADR-0004, N-10, E-06).

Fails CI if a migration creates ``stock_movement`` without ``location_id`` and
``lot_id``. These two columns are the entire cost of keeping multi-warehouse and
batch tracking as Edition 2 configuration exercises rather than re-architectures.

Adding them after stock history exists means re-keying the largest table in the
system and every balance query over it (E-06: High). This check exists so the
obligation is enforced by CI rather than remembered by a person.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED = ("location", "lot")
TARGET = "stock_movement"
ROOT = Path(__file__).resolve().parent.parent / "backend"


def main() -> int:
    creators = []
    for path in ROOT.rglob("migrations/*.py"):
        text = path.read_text(encoding="utf-8")
        if f'name="{TARGET}"' in text or f"name='{TARGET}'" in text or "StockMovement" in text:
            if "CreateModel" in text:
                creators.append((path, text))

    if not creators:
        print(f"ok: no migration creates {TARGET} yet (expected before M2)")
        return 0

    failed = False
    for path, text in creators:
        block = re.split(r"CreateModel", text, maxsplit=1)[1]
        missing = [c for c in REQUIRED if f'"{c}"' not in block and f"'{c}'" not in block]
        if missing:
            failed = True
            print(f"FAIL {path}: {TARGET} missing structural column(s): {', '.join(missing)}")
            print("      See ADR-0004, 00 §15.3, E-06. This is not optional.")
        else:
            print(f"ok: {path} carries {', '.join(REQUIRED)}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
