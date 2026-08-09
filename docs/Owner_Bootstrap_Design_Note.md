# Design Note — Owner Bootstrap (FR-IAM-014)

| Field | Value |
| --- | --- |
| Document ID | `Owner_Bootstrap_Design_Note` |
| Version | **1.1.0** |
| Status | **§6 ruled. Frozen — awaiting §3 approval to implement. No code written** |
| Date | 2026-08-08 |
| Closes | **FR-IAM-014** (priority `S`, v1.0, never built) |
| Satisfies | **FR-IAM-005**, `00` §20.3 criterion 2 |
| ADR required | **No** — see §5 |

---

## 0. The defect, in one line

`grant_role` requires an OWNER to act; a fresh database has none; therefore **no user can ever
be granted the first role through any supported interface.**

Verified, not assumed:

| Check | Result |
| --- | --- |
| Non-test writers of `UserRole` | **One** — `identity/services.py:217`, inside `grant_role` |
| `grant_role`'s first statement | `require_roles(actor, Role.OWNER)` |
| Production callers of `grant_role` | **None.** It is called only from `tests/adversarial/test_authorization_matrix.py` |
| Custom management commands | **None exist** |
| Fixtures / `loaddata` / seed scripts | **None** |
| `create_superuser` grants a role | **No** — it writes `app_user` only |

The only exit today is a raw `INSERT` into `user_role` — **an unaudited write into
authorisation data**, which is the precise thing ADR-0003 exists to prevent.

---

## 1. Why this is the correct architectural solution

### 1.1 It closes an ADR-0003 hole rather than opening one

ADR-0003's Consequences say emergency data fixes *"go through service functions or a
documented `psql` runbook, both of which are the correct paths anyway."* A management
command that calls a **service function** is the first of those two, made repeatable.

The command is a third delivery surface after `api` and `webadmin`, and it obeys the same
rule they do: **parse and delegate.** Every rule — the refusal predicate, the grant, the
audit — lives in `identity/services.py` (N-01). Nothing in the command touches a model.

**ADR-0003 is not violated. It is enforced.** Today's only bootstrap is a raw SQL insert
that writes no audit row; after this change there is no reason to reach for one.

### 1.2 It satisfies FR-IAM-014 as written, including the clause that gets forgotten

> *"The system MUST support a break-glass procedure for recovering `OWNER` access, and
> **every use of it MUST be audited as a distinct high-severity event**."*

Two clauses. The second needs a design decision, because **`audit_log` has no `severity`
column** — the only way an event can be "distinct" and high-severity is for its `action`
code to be recognisably its own thing.

So: a new `AuditLog.Action.OWNER_BOOTSTRAP`. Reusing `ROLE_GRANT` and hiding the difference
in `after_state` JSON would make break-glass use findable only by JSON containment, which is
not "distinct" in the sense a security reviewer means.

**This is a routine change here, not a novel one.** `core/migrations/0003` and `0004` are
both `AlterField` migrations that added action codes. The generated migration is
state-only — `choices` is not a database constraint on PostgreSQL.

### 1.3 The refusal predicate is what makes it break-glass rather than an escalation tool

> Refuse if **any active OWNER exists.**

*Active*, not *any*. If the sole owner has been deactivated, that **is** the recovery case
FR-IAM-014 describes, and a guard on "any OWNER" would lock the business out of its own
system permanently.

Stated plainly: someone with shell access could deactivate the owner and then bootstrap
themselves. Shell access already implies database access, so this guard prevents accident,
not a determined operator. It is a usability guard with an audit trail, and the audit trail
is the actual control.

### 1.4 It makes an existing Definition of Done true for the first time

`00` §20.3 criterion 2 — *"A user can log in by OTP on mobile and by password on web"* —
has **never been satisfiable on a clean machine** through the supported path. It passed at
M0 because the suite grants roles through `UserFactory(roles=[...])`, which at the time of
writing was a creation path production did not use (TD-30).

> **Corrected 2026-08-08, after TD-30 closed.** The factory now builds users through
> `UserManager.create_user`. Its `roles=` shortcut still writes `UserRole` directly and
> remains a fixture convenience — see `docs/TD-30_Factory_Creation_Path_Note.md` §3, which
> records why that half was closed by direct coverage rather than by routing.

---

## 2. Why the other options remain rejected

| Option | Rejected because |
| --- | --- |
| **A** — `create_superuser` grants OWNER | Conflates a **framework flag** with a **business role**. ADR-0003 deliberately left `is_superuser` meaningless — it feeds only `has_perm`/`has_module_perms`/`is_staff`, none of which DistriCore consults. It would also write an authorisation grant with **no audit row**, and BR-002 requires one for every role change |
| **C** — let `grant_role` self-bootstrap when no OWNER exists | Permanently weakens the guard on the most security-critical service in the system to solve a **once-per-database** problem. The condition would then be evaluated on every ordinary grant forever |
| **D** — data migration granting OWNER | A migration would be making an **authorisation decision**. On a fresh database there is no user to grant to; on an existing one, only a human can say which account is the owner. Same reasoning that made `identity/0004` refuse to merge colliding phone numbers |

**A is the one worth restating**, because it is the tempting one: it is three lines and it
makes the symptom go away. It also silently makes "can run `manage.py createsuperuser`"
equivalent to "has full authority over the business", with nothing in the audit trail
recording when that happened.

---

## 3. Files that will change

| # | File | Change |
| --: | --- | --- |
| 1 | `backend/core/models.py` | Add `OWNER_BOOTSTRAP` to `AuditLog.Action` |
| 2 | `backend/core/migrations/0005_alter_auditlog_action_bootstrap.py` | **Generated**, state-only `AlterField`. Precedent: `0003`, `0004` |
| 3 | `backend/identity/services.py` | Add `bootstrap_owner(*, phone, ...)`. `grant_role` **unchanged** |
| 4 | `backend/identity/management/__init__.py` | New, empty |
| 5 | `backend/identity/management/commands/__init__.py` | New, empty |
| 6 | `backend/identity/management/commands/bootstrap_owner.py` | New. Argument parsing and delegation only |
| 7 | `Makefile` | `superuser` target documents the two-step sequence; add `make owner` |
| 8 | `backend/tests/unit/test_identity_bootstrap.py` | New — §4's regression suite |
| 9 | `backend/tests/integration/test_webadmin.py` | Add `00` §20.3 criterion 2 as an executable test |
| 10 | `docs/runbooks/first-owner.md` | New — the documented recovery procedure FR-IAM-014 requires |
| 11 | `PROJECT_STATE.md`, `CHANGELOG.md` | Record after verification |

**Not changing:** `grant_role`, `require_roles`, `has_role`, `role_codes`, `UserManager`,
`webadmin/views.py`, or any authorisation predicate. The authorization model is correct;
it was missing an entry point, not a rule.

**Layering.** Django requires management commands to live inside an installed app, so the
command sits in `identity`. It imports `identity.services` and `django.core.management` —
no delivery-layer import, so contract 2 is unaffected and `lint-imports` needs no change.

---

## 4. Regression tests

| # | Asserts |
| --: | --- |
| 1 | `create_superuser` alone **cannot** sign in to webadmin — pins current behaviour as correct-by-policy, so nobody later "fixes" it by granting OWNER implicitly |
| 2 | `bootstrap_owner` grants OWNER and web login then succeeds — `00` §20.3 criterion 2 |
| 3 | `bootstrap_owner` **refuses when an active OWNER exists** |
| 4 | It **proceeds when the only OWNER is inactive** — the recovery case |
| 5 | The grant writes one `OWNER_BOOTSTRAP` audit row, with `granted_by` NULL and `actor_user` NULL |
| 6 | FR-IAM-005: any user who can reach the admin holds at least one role |
| 7 | **The deadlock itself** — with an empty `user_role` table, `grant_role` raises for every actor |

> **Test 7 is the one to insist on.** Without it, a later reader sees that `grant_role`
> "already does this", deletes `bootstrap_owner` as redundant, and restores the deadlock —
> with a green suite, because tests 2–5 would all still pass through the factory.

---

## 5. Irreversible decisions, and whether an ADR is needed

| # | Decision | Cost to reverse |
| --: | --- | --- |
| **B-1** | **`OWNER_BOOTSTRAP` as an audit action code** | **High.** `audit_log` is append-only (N-04). Once rows carry the code, renaming it orphans history. Cheap to add, impossible to rename cleanly |
| **B-2** | The bootstrap grant records `granted_by = NULL` | **Permanent per row**, and correct: nobody granted it. The column is already nullable |
| **B-3** | Refusal predicate = *active* OWNER exists | Low in code; it is a stated security posture, so changing it needs the same scrutiny as adopting it |

**Verdict: design note, no ADR.**

The test I applied — does this change a milestone boundary, add a table, or amend a recorded
decision? No, no, and no. It **implements** a requirement that has sat at priority `S`
unbuilt since `02` was written. Adding an audit action code follows a pattern already used
twice. And ADR-0003 already sanctions the CLI as the operational surface, so the command
formalises an existing decision rather than making a new one.

**What would need an ADR:** turning management commands into a general-purpose surface with
several commands writing domain data. One bootstrap command that calls one service does not.

---

## 6. `--reason` — **RULED optional, 2026-08-08**

> **Do not block recovery because an operator forgot a reason. The audit trail is the
> primary control, not mandatory free-text.**

Accepted, and it is the stronger position. A mandatory field on a break-glass path is a
field that fails closed at the worst possible moment: the business is locked out, and the
tool that exists to let them back in refuses over a text box. It would also be defeated
within a week by `--reason=recovery` in a saved shell command, at which point the control is
theatre and the audit row is worse than empty — it looks explained and is not.

| Situation | `--reason` | Behaviour |
| --- | --- | --- |
| **`FIRST_BOOT`** — no OWNER has ever existed | Not required | Proceeds |
| **`RECOVERY`** — users exist, no active OWNER | **Accepted, never required** | Proceeds either way |

---

## 7. The audit payload, specified

The mode is **classified by the service, from the database — never passed in by the
caller.** A caller-supplied label would be a security record asserting whatever the operator
typed.

```
mode = FIRST_BOOT   if no UserRole row for OWNER exists at all
       RECOVERY     if OWNER rows exist but no holder is active
```

One `AuditLog` row per successful bootstrap:

| Field | Value | Note |
| --- | --- | --- |
| `action` | **`OWNER_BOOTSTRAP`** | New code (B-1). Distinct from `ROLE_GRANT`, which is what makes it findable |
| `occurred_at` | *automatic* | `auto_now_add` on the model — **the timestamp requirement is already met and must not be duplicated** into `after_state` |
| `entity_type` / `entity_id` | `"user_role"` / the new link's pk | Matches `grant_role`'s existing shape |
| `actor_user` | **NULL** | Nobody authorised this. The truthful actor is "an operator with shell access", who is unidentifiable — recording a name would invent one |
| `surface` | `SYSTEM` | Already a valid choice; no model change |
| `after_state` | see below | |

```jsonc
{
  "mode": "FIRST_BOOT",      // or "RECOVERY" — the conclusion
  "role": "OWNER",
  "user_id": 1,              // the target user
  "phone_suffix": "4153",    // house style; user_id is the unambiguous identifier
  "users_existing": 0,       // ... and the FACTS the conclusion was drawn from
  "owner_rows_existing": 0,
  "inactive_owners": 0,
  "reason": ""               // whatever was given, or empty. Never blocks
}
```

### 7.1 Why the counts are recorded alongside the label

**One edge case makes `mode` debatable rather than wrong:** OWNER granted, later revoked —
`revoke_role` *deletes* the `UserRole` row — then bootstrapped. That reads as `FIRST_BOOT`
because no OWNER row survives, when in substance it is a recovery.

Answering it properly would mean querying the append-only `audit_log` for a historical
`ROLE_GRANT`, which couples this service to the audit trail's JSON shape for the sake of one
label in one row.

**Cheaper and more honest: record the facts the label was derived from.** A reviewer who
distrusts `mode` can read `users_existing` and `owner_rows_existing` and reach their own
conclusion. Recording the conclusion without the evidence is what makes an audit trail
unfalsifiable, and an unfalsifiable audit trail is not a control.

### 7.2 Test 5 of §4 is updated accordingly

It now asserts the row carries `action == OWNER_BOOTSTRAP`, `actor_user IS NULL`,
`granted_by IS NULL`, and a `mode` matching the database state it was derived from — with a
companion test covering the `RECOVERY` branch after the only owner is deactivated.

---

*No code has been written. §6 is ruled and §7 is specified. Implementation begins on
approval of §3's file list.*
