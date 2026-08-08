"""Reporting — the module that owns nothing (`03` §2.1, M7).

**A report computes nothing. It arranges, filters and totals figures the domain already
derives** (M7 §1).

There is no ``models.py``, no ``services.py`` and no migration here, and there must never
be one. ``reporting`` is the only module in DistriCore that could be deleted without
changing a single stored fact or a single business rule — which is the property that makes
it safe for it to read from every other module.

D-3 draws the line this module lives on:

* **Arranging** — filtering, grouping, counting, ordering, limiting and totalling rows of
  an *already-scoped queryset a domain selector returned*. Belongs here.
* **Deriving** — any figure needing a business rule: a balance, an on-hand quantity, an
  ageing, an exposure, anything reached by a walk or a sign convention. Belongs in the
  owning domain module, always, even when only a report wants it.

The test is not "does it contain arithmetic". It is: **would getting this wrong be a
business-rule defect, or a display defect?**
"""
