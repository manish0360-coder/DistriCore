# Design Note — TD-30: the factory must build users the way production does

| Field | Value |
| --- | --- |
| Document ID | `TD-30_Factory_Creation_Path_Note` |
| Version | 1.0.0 |
| Status | **Approved scope — implementing** |
| Date | 2026-08-08 |
| Closes | **TD-30** (creation half, structurally; role half, by argument — see §3) |
| ADR required | **No.** Test infrastructure. No production behaviour changes |

---

## 1. What is wrong

`factory.django.DjangoModelFactory._create` calls `Manager.create()`. `UserManager._create`
— which holds the write-path rules — is never reached. So **no user in 703 tests has ever
been built the way production builds one.**

It hid two defects in a row:

| Defect | Why the suite could not see it |
| --- | --- |
| Phone normalisation (§10 of `M7_Verification_Report`) | Factory phones were already canonical (`+9198765…`), so a missing write-path rule changed nothing |
| Owner bootstrap deadlock (§11) | Factory users arrived **with roles**, so the absence of any path to the first role changed nothing |

A clean install could fail while the suite stayed green, and did, for eight milestones.

---

## 2. The fix

```python
@classmethod
def _create(cls, model_class, *args, **kwargs):
    password = kwargs.pop("password", None)
    return model_class.objects.create_user(*args, password=password, **kwargs)
```

`password` moves from a `post_generation` hook to a plain declaration so it reaches
`create_user` as an argument rather than being written over the top afterwards.

**Blast radius, counted rather than estimated: six call sites.** None passes `phone=`; one
passes `password=`; no test asserts anything about password state.

One behaviour changes, and it changes towards production: a factory user with no password
currently ends up with an empty `password` string, and will now hold an **unusable** hash —
which is what `create_user` does for a retailer who authenticates by OTP, and what its
docstring already says.

---

## 3. The role half: closed by argument, not by routing

TD-30 names two things. `UserFactory(roles=[...])` also writes `UserRole` directly, which
`grant_role` and `bootstrap_owner` are the only production writers of.

**Routing it was considered and rejected.** `grant_role` requires an OWNER actor, so every
fixture would need one in scope, and the first owner in each test would need
`bootstrap_owner` — which refuses when an active owner exists. Fixtures would become
order-dependent, and authorisation concerns would be pushed into every test that merely
needs a salesman.

**What actually removed the blind spot is already done.** The role paths now have direct,
dedicated coverage that does not go through the factory at all:

| Path | Covered by |
| --- | --- |
| `grant_role` | `test_authorization_matrix.py` — including that only an OWNER may call it |
| `bootstrap_owner` | `test_identity_bootstrap.py` — 17 tests, **including the deadlock itself** |

The factory's `roles=` shortcut is a **fixture convenience**, not a claim about production,
and it is now labelled as one in the code. A test pins that distinction: a factory user with
no roles cannot reach the admin.

> **Stated plainly so nobody later reads "TD-30 closed" as "both halves routed":** the
> creation half is closed *structurally* — it cannot regress without the tests failing. The
> role half is closed *by coverage elsewhere* — a discipline, which is weaker. If the
> fixture layer is ever reworked, routing roles through the services is the right thing to
> do then.

---

## 4. Files that will change

| # | File | Change |
| --: | --- | --- |
| 1 | `backend/tests/factories.py` | `_create` routes through `create_user`; `password` becomes a declaration |
| 2 | `backend/tests/unit/test_factories.py` | **New** — the guard tests |
| 3 | `backend/tests/integration/test_webadmin.py` | One docstring now says something untrue |
| 4 | `backend/tests/unit/test_identity_bootstrap.py` | Same |

**No production file changes.** `identity/managers.py`, `identity/services.py` and every
authorisation predicate are untouched.

Items 3 and 4 are corrections, not scope creep: both docstrings currently assert that
`UserFactory` *"bypasses `UserManager._create`"*, which stops being true the moment item 1
lands. A comment that describes the opposite of the code is worse than no comment.

---

## 5. Guard tests

| # | Asserts |
| --: | --- |
| 1 | **The factory normalises a non-canonical phone** — the property that would have caught the first defect. If `_create` is ever bypassed again, this fails |
| 2 | A factory user with no password holds an **unusable** hash, matching `create_user` |
| 3 | A factory user built with a password authenticates through `authenticate_password` |
| 4 | A factory user with **no roles cannot reach the admin** — pinning `roles=` as a shortcut rather than a claim |
| 5 | `UserFactory` and `create_user` produce the same stored phone for the same input |

Test 1 is the load-bearing one. It is the smallest statement of "the factory takes the
production path", and it fails immediately if a future factory refactor reverts to
`Manager.create()`.

---

*No ADR. No production behaviour change. Implementation follows immediately; stop at
`make verify`.*
