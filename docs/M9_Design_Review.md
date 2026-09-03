# M9 — Sync: Design Review

| Field | Value |
| --- | --- |
| Document ID | `M9_Design_Review` |
| Version | **1.3.0** |
| Status | **Signed — R-1…R-5, T-3 and FR-SYN-009 all ruled 2026-08-21, recorded as D-M9-1…D-M9-7. Authority for `02` §18.1 S-1…S-5 (applied) and S-6 (authorised, unwritten). D-M9-8 ruled 2026-08-25 — authority for the `M8_Design_Review` §5.6 cipher amendment (applied, v1.8.0); opens TD-42…TD-45.** |
| Date | 2026-08-21 |
| Milestone | M9 — Sync (`00` §19.1) |
| Scope | Push receiver · mobile drain · server sync status · pull and device cache · **the Edition-1 conflict model** |
| Effort | 2.0 units (`00` §19.1) |
| Depends on | `00` v1.0.0 · `01` v0.2.0 · `02` v0.2.0 · `02A` v0.2.0 · `03` v0.1.0 · `04` v0.1.0 · `05` v0.1.0 · `M8_Design_Review` v1.6.1 |

> Durable record of the M9 design decisions (`00` §10, ADR-0005 §10).
>
> **Written after implementation, and that is a departure worth naming.** M2, M3, M5, M6, M7
> and M8 each had a design review *before* their milestone was built. M9 did not: four
> increments were implemented, verified and committed against decisions frozen in
> conversation and recorded — where they were recorded at all — inside `05` §11.1 and §11.5
> as dated clarification blocks. This document exists because the corpus needs an authority
> the `02` amendment register can cite, and because two decisions (D-M9.4-6, D-M9.4-7) were
> found cited by identifier in shipped source while existing in no document at all.
>
> **No ADR is proposed.** M9 changes no milestone boundary and adds no table. §6 resolves a
> specification conflict by applying the corpus's own declared division of authority, not by
> creating new authority.
>
> **One clause of one ADR is amended, and only from v1.3.0.** D-M9-8 (2026-08-25) replaces the
> cipher named in `M8_Design_Review` §5.6. **That ADR's conclusion — Drift — is untouched**, as
> is every word of its reasoning; what changes is the implementation behind `PRAGMA key`. The
> sentence above read *"reverses no architecture decision"* through v1.2.0 and was true then.
> It is qualified rather than deleted, because it was accurate when written.

### Change log

| Version | Date | Change |
| --- | --- | --- |
| 1.0.0 | 2026-08-21 | Issued and signed. **D-M9-1 … D-M9-5** — the Edition-1 conflict model. Authority for `02` §18.1 **S-1 … S-4**, which were applied the same day |
| **1.2.0** | **2026-08-21** | **§6 D-M9-7 added — FR-SYN-009 moves to `Rel = v2.0`, priority `M` and requirement text unchanged, nothing deleted.** Three Edition-1 prerequisites are deferred by `02A` and **each is sufficient alone**: the admin console (§7.12), the `SALESMGR`/`ADMIN` roles (§7.1 — Edition 1 has four, and neither is among them), and the registered `device` entity (§13.2, `04`). `03` §11.3 and `05` §11.5 recorded as **documentation inconsistencies, not counter-evidence**, and **not amended**. **OC-3 stays separate and Edition 1.** An independent Gemini review reaching the same conclusion is recorded as **corroboration, not authority**. **Authorises `02` S-6, which is not written here.** **Minor, not patch: a decision was added.** No API, schema, logic, code or test change |
| **1.1.0** | **2026-08-21** | **§6 D-M9-6 added — FR-SYN-008's *"count of unresolved conflicts"* is undefined and is replaced.** The smallest truthful V1 quantity is `sync_operation.status = 'REJECTED'`, already specified at `05` §11.5 as `rejected_count` and already displayed. `DEFERRED` is excluded from the **device-side** count because it auto-retries; it stays in the **owner's** exception list (`04` T-26). M8's *"failed count"* recorded as drift evidence, **not** authority. Proposed FR-SYN-008 wording: *"count of operations the server has rejected"*. **Authorises `02` S-5, which is not written here.** FR-SYN-009 untouched. **Minor, not patch: a decision was added** (`M8_Design_Review` 1.6.1's rule). No API, schema, logic, code or test change |
| **1.3.0** | **2026-08-25** | **§6 D-M9-8 added — the Edition-1 cipher is SQLite3MultipleCiphers, not SQLCipher.** Authority for the `M8_Design_Review` §5.6 amendment, applied the same day at v1.8.0. **`02` is not amended: FR-SYN-016 and NFR-SEC-008 name no cipher**, so the requirement is untouched and no `S-` row is authorised. **The preamble's *"reverses no architecture decision"* is qualified, not deleted.** Records the device proof — Pixel 8a API 34 emulator, `android-x64`, **not arm64 and not physical hardware** — and closes the encryption gate only; **`00` §19.2's durability gate stays open** (§9 item 5). Opens **TD-42…TD-45**; **TD-37 unchanged**. **Minor, not patch: a decision was added.** No API, schema, logic or requirement change; the code and gate it records were built under Changes 1–3 and are already verified |

---

## 1. The governing principle

**Version 1 sync is an outbox, not a reconciliation protocol.**

That sentence is `05` §11's, and everything in M9 follows from it. A device writes delivery
outcomes, visits, coordinates and photographs. It writes no order. Therefore it competes for
no shared resource, and therefore the hard half of offline synchronisation — revalidating a
stale commercial commitment against stock, credit, price and master data that have all moved
on — does not arise in Edition 1.

`02A` §5 states the consequence in a table this review will refer to repeatedly:

| | Baseline (offline order capture) | Edition 1 (offline status + activity) |
| --- | --- | --- |
| Conflict classes | 6 | **2** |
| Requiring human resolution | 4 | **0** |
| Conflict resolution console | Required | **Not required** |
| Exception order states | 3 | 0 |
| Sync mechanism | Bidirectional reconciliation protocol | **Durable outbox with idempotent replay** |

**The whole of §6 is the consequence of the two zeroes in that column.**

---

## 2. Authority

### 2.1 Where this document's authority comes from

`02A`'s header states its own scope, and it is the rule this review applies:

> **`02A` "Governs":** *"Edition membership of every feature. **Architecture, database and API
> documents derive their scope from this document.**"*
>
> **`02A` "Standing":** *"The Vision and Requirements Specification define **what the product
> is**. This document defines **what is built first, and what is sold later**. **It does not
> add requirements**; it **partitions** the confirmed ones and, where the new Edition 1
> direction departs from the frozen baseline, **records the departure explicitly rather than
> absorbing it silently** (C-1, C-3)."*

That divides authority cleanly and without a tie-break rule:

| Document | Owns |
| --- | --- |
| **`02`** | Requirement **content** and **priority**. A requirement is confirmed or it is not |
| **`02A`** | **Edition membership** — which release builds a confirmed requirement |
| **`03` · `04` · `05`** | **Shape** — structure, schema, wire contract. They derive their *scope* from `02A` |

**"Later document wins" is not a rule in this project and is not used here.** M7 §2 phrased
its own precedence that way — *"`02A` §13 is later, was explicitly approved, and `04` was
designed from its outcome — so it governs"* — and reached the right answer for a reason it
did not quite state. `02A` governs because it says it governs, over a named domain, and
because `04` and `05` are instructed by that same clause to derive from it. Being later is
incidental.

### 2.2 The amendment pattern this review is written to feed

`02A` cannot silently change `02`'s `Rel` column; its own standing clause forbids absorbing a
departure silently. The corpus has therefore performed this operation seven times, always the
same way:

| Step | Precedent |
| --- | --- |
| 1. `02A` supersedes on edition membership | `02A` §13.2 vs `02` FR-REC-004/006/008 |
| 2. A review flags that `02` still reads `M, v1.0` | `M6_Verification_Report` §8.2: *"`02A` §13.2 supersedes them, but **the next person to read `02` cold will conclude that Edition 1 allocates payments to invoices.** Owner: Product Architect"* |
| 3. `02` is amended **in place**; nothing is deleted | `02` §20.1 preamble: *"Nothing here was deleted. A requirement moved to v2.0 is still a requirement"* |
| 4. The requirement line is annotated and re-released | `02` FR-REC-004: *"…**[B-1 — superseded in v1.0 by FR-REC-016]** \| M \| **v2.0**"* |
| 5. A register row names the authority | `02` §20.1 A-1…A-7, each citing `02A` §x · M7 §y |

**Step 5 is why this document exists.** Every A-register row cites a design review as
co-authority. There was no M9 design review, so the register could not be extended, so the
departure recorded in `05` §11.4 has stood unrecorded in `02` for the whole of M8 and M9.

---

## 3. Scope, and what M9 actually shipped

`00` §19.1 defines M9 as *"Sync — push/pull, idempotency, ordering, sync status"*, 2.0 units,
depending on M8. **`00` defines no sub-milestones.** `M9.1`–`M9.4` below are working labels
for four commits, not roadmap entries. **There is no M9.5.**

Commit identifiers read from `.git/logs/HEAD`; subjects verbatim.

| Label | Commit | Subject | Delivered | Contract |
| --- | --- | --- | --- | --- |
| **M9.1** | `1a26781` | `feat(sync): add backend sync receiver` | `POST /sync/push`; `sync_operation` (`04` T-26); dedicated `field` app (D-M9.1-2); the five-value server status vocabulary | `05` §11.2, PU-1…PU-4 |
| **M9.2** | `ffd2702` | `feat(mobile): add sync engine` | Mobile `SyncEngine` — single-flight drain, batch claim/settle, `IN_FLIGHT` recovery, launch-time trigger | `05` §11.2, §11.4 |
| **M9.3** | `e26aa87` | `feat(sync): add server sync status` | `GET /sync/status`; the server's view rendered beside the local queue | `05` §11.5, D-M9.3-1/2 |
| **M9.4** | `bf94b8e` | `feat(sync): add offline pull and cache` | `GET /sync/pull` with an opaque `page_token`; Drift v2→v3 device cache; `PullService`; cache-first delivery and customer rounds; ordered start-up chain | `05` §11.1, D-M9.4-1…8 |

A fifth commit, `85d1670 docs: reconcile project state after M9`, reconciled
`PROJECT_STATE.md`, `NEXT_TASK.md` and `CHANGELOG.md` with the committed history. *(Reported
by the maintainer; it postdates the reflog read above.)*

**Decisions already recorded in `05`, and not re-litigated here:** D-M9.1-1 (`DELIVERY_COMPLETE`
canonical), D-M9.1-2 (`field` app), D-M9.3-1 (`device_id` from the JWT), D-M9.3-2 (`rejected[]`
carries four fields), D-M9.4-1…D-M9.4-8. This review governs **only** the conflict model.

---

## 4. Evidence

Everything in this section is a quotation or an observed absence. Nothing is inferred.

### 4.1 What `02` requires

| Ref | Text | Pri | Rel |
| --- | --- | :-: | :-: |
| **FR-SYN-005** | *"`CORE` MUST classify every rejected transaction into a §5.3 class and persist it as a `SyncConflict` in `PENDING_RESOLUTION`."* | M | v1.0 |
| **FR-SYN-006** | *"A transaction MUST NOT be discarded under any circumstance, **including malformed payloads, which MUST be quarantined and reported** rather than dropped."* | M | v1.0 |
| **FR-SYN-013** | *"Conflicts MUST be resolvable on `S1` with sufficient context to decide: captured values, current values, customer, salesman and capture time."* | M | v1.0 |
| **FR-SYN-014** | *"Resolution of a conflict MUST be audited with resolver, decision and timestamp."* | M | v1.0 |
| **BR-014** | *"**No transaction is discarded.** A transaction that fails server-side validation is persisted as a `SyncConflict` in `PENDING_RESOLUTION`, never dropped."* | — | — |
| **BR-015** | *"**Conflict resolution is explicit, never automatic**, except for the deterministic classes in §5.3."* | — | — |

**None of these appears in `02` §20.1's amendment register (A-1 … A-7).** The register has been
used seven times and was never applied here.

`02` §5.3, the taxonomy FR-SYN-005 refers to, is prefaced *"Detected by `CORE` at sync time.
Every class has a defined, testable outcome"*:

| Class | Condition | Automatic? |
| --- | --- | :-: |
| `SC-DUPLICATE` | Client identifier already accepted | **Yes** |
| `SC-STOCK` | **Ordered quantity** exceeds available stock | No |
| `SC-CREDIT` | **Order** breaches credit limit | No |
| `SC-PRICE` | `quotedUnitPrice` differs from recomputed | No — **order** held in `PRICE_VARIANCE` |
| `SC-MASTER` | Customer/product deactivated since last sync | No — **order** held in `MASTER_STALE` |
| `SC-SEQUENCE` | Depends on a prior transaction not yet accepted | **Yes** |

`02` §4.1 lists the synchronisation entities as *"`SyncBatch`, `SyncTransaction`,
`SyncConflict`"*. **None of the three has a table in `04`.**

### 4.2 What `02A` says

- §5: *"In Edition 1, salesmen no longer capture orders … **None of them contend for a shared
  resource** … The conflict taxonomy collapses from six classes to two."*
- §5, the table reproduced in §1 above: human resolution **4 → 0**, console **Required → Not
  required**.
- §5: *"**The upgrade path is intact.** Adding field order capture in Edition 2 means adding
  the four missing conflict classes and a resolution console **on top of** an outbox that
  already exists."*
- §6.2: field order capture *"with full conflict resolution"* is an **Edition 2** addition.
- §7.12: *"Conflict resolution console \| M \| H \| **2** \| N \| — \| **Not needed in
  Edition 1**."*
- §13 — the Edition-1 re-validation — **does not mention conflicts at all.** Its retained list
  names *"Offline outbox and idempotent replay · Master-data pull · Sync status visibility"*.

### 4.3 What `04` says

`04` T-26 `sync_operation`:

- *"**Why it exists.** BR-012, BR-013, **BR-014**, E-09, **FR-SYN-003…006**."* — a range that
  includes FR-SYN-005.
- Status vocabulary: `RECEIVED`, `ACCEPTED`, `DUPLICATE`, `DEFERRED`, `REJECTED`. **No
  `PENDING_RESOLUTION`.** No resolution state, no resolver column, no audit FK.
- `payload` — *"**Retained only for `REJECTED`** — the BR-014 evidence"*.
- `ck_sync_operation_rejected` — a rejection cannot exist without a reason.
- `ix_sync_operation_status`, partial, `WHERE status IN ('DEFERRED','REJECTED')` — described
  verbatim as *"**the owner's exception list**"*.
- *"**Nothing is ever discarded** (BR-014). A malformed or rejected operation is stored with
  its payload and **surfaced to the owner**. **This is the table that makes 'no transaction is
  ever lost' true rather than aspirational.**"*
- *"**Future evolution.** Edition 2 adds `ORDER_CREATE` and the four conflict classes as new
  `status` values plus a **`conflict_type` column**. The table, the key and the ordering
  guarantee are unchanged."*

### 4.4 What `05` and `03` say

- `05` §11 preamble: *"Per ADR-013, Version 1 sync is an outbox, not a reconciliation
  protocol."*
- `05` §11.4: *"**Only the two automatic classes exist in Version 1. No conflict resolution
  console is built, because none is needed** — a direct consequence of DV-1 removing field
  order capture (`02A` §5)."*
- `05` §11.2 status table: `REJECTED` → *"**Keep. Never delete.** Flag to the user; the server
  has stored it for the owner (BR-014)."*
- `05` specifies **no conflict endpoint, no resolution action and no resolution audit.**
- `03` §6.2: *"**No transaction is discarded (BR-014).** A malformed or rejected operation is
  stored server-side with its error and **surfaced to the owner**."*
- `M8_Design_Review` §3.5, *"Deliberately absent, with authority"*: *"Conflict resolution \|
  `02A` §5 — zero classes need human resolution."*

### 4.5 Repository-wide search

| Term | Occurrences |
| --- | --- |
| `SyncConflict` | **2, both in `02`** — §4.1 entity list, BR-014 |
| `PENDING_RESOLUTION` | **1, in `02`** — BR-014 |
| `FR-SYN-005` / `013` / `014` | **1 each, all in `02`.** Not cited by `04`, `05` or any code |
| `BR-014` | **16**, including four in shipped code and tests |

**BR-014 is load-bearing in production code. `SyncConflict` and `PENDING_RESOLUTION` exist in
one document and nowhere else in the repository.**

### 4.6 What the implementation actually does

`backend/sync/services.py` sets `status=REJECTED`, `error_code` (truncated to 50),
`error_detail`, `payload`, `processed_at`. Rejections arise from an unknown `operation_type`,
a validation failure, or an out-of-scope delivery. **No classification into any `SC-*` class
occurs, and no code references `SC-DUPLICATE` or `SC-SEQUENCE` by name.**

---

## 5. Inference

Labelled, because none of it is written in the corpus.

| # | Inference | Basis |
| --: | --- | --- |
| **I-1** | `02` §5.3, §5.2 and §18 were written against the **pre-DV-1 baseline**, in which salesmen captured orders offline | `02A` §5 names §5.3, the exception states and the console as consequences of that capability |
| **I-2** | `04` and `05` treat `sync_operation.status='REJECTED'` as the Edition-1 discharge of BR-014 | `04` T-26's requirement list and *"the owner's exception list"*. **Neither document says *"this replaces `SyncConflict`"***; that identification is made here for the first time |
| **I-3** | FR-SYN-013 and FR-SYN-014 have no subject in Edition 1, because nothing requires human resolution | Their own traces (BR-015, FR-ORD-034, BR-002) point at the four order-borne classes. Neither requirement is textually conditioned on order capture |
| **I-4** | `SyncBatch` and `SyncTransaction` were superseded by `04`'s modelling in the same way `SyncConflict` was | All three are absent from `04` and nobody has ever treated the first two as defects. **Not stated anywhere** |

---

## 6. Decisions

Accepted as Product Architect ruling on **2026-08-21**. Identifiers `D-M9-1` … `D-M9-5`.

### D-M9-1 — `02` owns requirement content and priority; `02A` governs Edition-1 membership

**`02A` §5 / DV-1 is authoritative for the Edition-1 conflict model.** `05` §11.4, `04` T-26
and `M8_Design_Review` §3.5 correctly derive from it — that is what `02A`'s "Governs" clause
instructs them to do.

**And `02A` cannot amend `02`.** Its standing clause explicitly forbids absorbing a departure
silently. FR-SYN-005/013/014 remain confirmed requirements until `02` says otherwise, in
`02`, in the form §2.2 records.

> **The defect is procedural, not architectural.** Nothing built in M8 or M9 is wrong. What
> is wrong is that a departure `02A` obliged someone to record was never recorded — so `02`
> still reads `M, v1.0` and a reader coming to it cold concludes that Edition 1 ships a
> conflict resolution console. **That is the precise failure `M6_Verification_Report` §8.2
> named about FR-REC-004, one milestone earlier, and it was allowed to recur.**

### D-M9-2 — `sync_operation` is the Edition-1 persistence vehicle. No separate `SyncConflict` table.

FR-SYN-005's persistence clause is discharged by `sync_operation.status = 'REJECTED'` with
retained `payload` and a non-empty `error_code`. **No `SyncConflict` table is required, and
none may be added on the strength of FR-SYN-005.**

Three reasons, in order of weight:

1. **`04` claimed it explicitly, and `04` holds modelling authority.** T-26 names
   FR-SYN-003…006 and BR-014 among its reasons for existing, and calls itself *"the table
   that makes 'no transaction is ever lost' true rather than aspirational"*. `02` says what
   must be guaranteed; `04` says what shape holds it.
2. **`SyncConflict` is a name in a conceptual entity list, not a schema mandate.** `02` §4.1
   lists three synchronisation entities and **`04` models none of them by name**. Binding
   `04` to that list would oblige `SyncBatch` and `SyncTransaction` too.
3. **A `PENDING_RESOLUTION` state would have no exit.** `02A` §5 sets human-resolvable classes
   to **zero** in Edition 1. A state that no actor and no transition can remove a record from
   is not a safeguard — it is an unbounded queue nobody reads, which is *worse* for BR-014
   than the status field, not better.

**Scope of this decision:** it settles FR-SYN-005's *persistence* clause only. The
*classification* clause is D-M9-3.

### D-M9-3 — The conflict taxonomy and FR-SYN-006 quarantine are two paths. **This distinction is being drawn here, not quoted.**

**State the honest position first.** `02` does not say anywhere that FR-SYN-005 and
FR-SYN-006 describe different categories of failure. FR-SYN-005 says *"every rejected
transaction"*, without qualification, and if that phrase is read literally it obliges the
server to classify an unknown `operation_type` into a taxonomy containing no class that
describes it. **That obligation is unsatisfiable as written, and no document in the corpus
acknowledges it.** This decision resolves it; it does not discover a resolution already
present.

**The reading adopted.** `02` §5.3 is prefaced *"Detected by `CORE` at sync time"*, and every
one of its six classes describes a transaction that is **well-formed and authorised but
contends with server state that has moved on** — stock, credit, price, master data, ordering,
or a prior acceptance. The rejections the implementation actually produces are a different
kind of event: **malformed, invalid or unauthorised input**, which contends with nothing.

`02` already carries a separate requirement for that kind, in the same table:

> **FR-SYN-006** *(M, v1.0)* — *"A transaction MUST NOT be discarded under any circumstance,
> **including malformed payloads, which MUST be quarantined and reported** rather than
> dropped."*

**Ruling:**

| Event | Requirement | Edition-1 mechanism |
| --- | --- | --- |
| Well-formed; contends with server state | **FR-SYN-005** → a §5.3 class | Two automatic classes only (`02A` §5) |
| Malformed / invalid / unauthorised | **FR-SYN-006** → quarantine **and report** | `status='REJECTED'` + retained `payload` + `error_code` (`04` T-26) |

**FR-SYN-005 applies only to conflict-class failures.** In Edition 1 both surviving classes
are automatic, so nothing is left unclassified.

**`error_code` carries the quarantine reason and is not, and must not become, an `SC-*`
value.** No new class is invented here, and none is authorised to be invented.

> **Consequence: the code was already right, and the requirement text was the thing that was
> wrong.** This decision creates no engineering work. It creates an amendment.
>
> **One clause of FR-SYN-006 is genuinely unmet: *"and reported."*** See D-M9-5.

### D-M9-4 — FR-SYN-013 and FR-SYN-014 move to `Rel = v2.0`

FR-SYN-013's subject is *"Conflicts … resolvable on `S1`"*, tracing **BR-015** — *"except for
the deterministic classes in §5.3"* — and **FR-ORD-034**, an order requirement. Its subject is
therefore exactly the four non-deterministic, order-borne classes. FR-SYN-014's subject is
*"**Resolution** of a conflict"*.

In Edition 1 there are zero human-resolvable conflicts. **Neither requirement has a subject.**

**They are not waived and are not deleted.** They move to v2.0 annotated in place, priority
unchanged, in the form `02` used for FR-REC-004 — *"a requirement moved to v2.0 is still a
requirement"*. They return with the capability that creates their subject, which `02A` §5 and
`04` T-26's *"Future evolution"* both already commit to.

### D-M9-5 — Owner-facing rejection reporting is an **unmet v1.0 requirement**. No API shape is specified.

**This is the one place where the Edition-1 model is genuinely short**, and four documents say
so independently:

| Source | Says |
| --- | --- |
| `02` **FR-SYN-006** *(M, v1.0, **not** superseded by `02A` — it concerns malformed payloads, not order conflicts)* | *"quarantined **and reported**"* |
| `04` T-26 index | the partial index is *"**the owner's exception list**"* |
| `04` T-26 rules | *"stored with its payload and **surfaced to the owner**"* |
| `03` §6.2 | *"stored server-side with its error and **surfaced to the owner**"* |

**`05` §11.5's `rejected[]` does not satisfy this.** D-M9.3-1 scopes that endpoint to the
caller's own `device_id`, taken from the JWT — so it reports to the **device user**, never to
the owner on `S1`. An index exists for a reader that does not exist.

**Ruling: the requirement stands and is unmet.** `05` specifies no endpoint, no screen, no
fields and no scoping for it.

> **No endpoint, serializer, table, screen or field is proposed, named or implied by this
> document.** Inventing one would repeat exactly the failure `SyncConflict` represents — a
> name written in one document that nothing else honours. **The owner view is blocked on a
> contract amendment to `05`, which is a Product Architect deliverable.**

### D-M9-6 — FR-SYN-008's *"count of unresolved conflicts"* is undefined and is replaced

*Added in v1.1.0, 2026-08-21. Authorises `02` amendment **S-5**, which is **not yet written**.*

#### 1. Why the phrase is undefined

`02` FR-SYN-008 *(M, v1.0)* requires the device to display *"last successful sync time, count
of pending transactions, and **count of unresolved conflicts**."* The phrase occurs **twice in
the entire repository** — FR-SYN-008 and FR-SYN-009 — and **is defined nowhere**.

- Both requirements trace **§5.4** only, which reads in full: *"Nothing fails silently (Vision
  §12.4). Sync state MUST be visible to the device user and to `SALESMGR`/`ADMIN` in `S1`."*
  §5.4 defines no term. Neither requirement traces §5.3, BR-014 or BR-015.
- `05` §11.5 — the endpoint that answers FR-SYN-008 — **does not contain the word
  "conflict"**. It defines `pending_count`, `deferred_count` and `rejected_count` by
  `sync_operation.status`, and nothing else.
- `04` T-26 never uses the phrase. Its nearest countable artefact is the partial index on
  `('DEFERRED','REJECTED')`, which it calls *"the **owner's** exception list"*.
- The closest thing to a definition is **BR-015** — *"Conflict resolution is explicit, never
  automatic, **except for the deterministic classes in §5.3**"* — from which an *unresolved*
  conflict is one awaiting an explicit human step. **BR-015 is not among FR-SYN-008's
  traces**, so reading it in borrows a definition the requirement never claimed.

**The decisive evidence is behavioural, not textual: the phrase has already been silently
replaced twice by people trying to build against it** — by `M8_Design_Review` §3 (*"failed
count"*, §4 below) and by the shipped device screen, which binds `server.rejected` to a widget
keyed `sync.conflicts` and renders *"No conflicts"*. **A term that every implementer
substitutes is not a requirement; it is a gap with a `MUST` in front of it.** Neither
substitution has any authority, and this decision adopts neither.

#### 2. Why `REJECTED` is the smallest truthful Version-1 quantity

The quantity is **the number of operations this device sent that the server refused
terminally** — `sync_operation.status = 'REJECTED'`. It is established in three frozen places,
and this decision creates none of them:

| Source | Text |
| --- | --- |
| `05` §11.5 | `` `rejected_count` \| `status = 'REJECTED'` `` |
| `05` §11.2 | `REJECTED` \| *"Failed validation"* \| *"**Keep. Never delete.** **Flag to the user**; the server has stored it for the owner (BR-014)"* |
| `04` T-26 | `REJECTED` in the status CHECK; `ck_sync_operation_rejected` forbids a rejection without a reason; `payload` *"Retained only for `REJECTED` — the BR-014 evidence"* |

**`05` §11.2 already obliges the client to flag it to the device user.** That is the corpus
authorising the display, independent of what the field is called — precisely the authority
*"unresolved conflicts"* never supplied. FR-SYN-008's third slot has therefore always had a
real referent; only its name was missing.

It also preserves §5.4's intent better than any alternative. A `REJECTED` operation is the one
server verdict a field user can **neither fix nor wait out**: it is terminal, never retried,
and carries a mandatory reason. That is exactly what *"nothing fails silently"* is for.

#### 3. Why `DEFERRED` is excluded from the **device-side** count

**`DEFERRED` resolves itself.** `05` §11.4 maps `SC-SEQUENCE` — one of the two surviving V1
classes — onto `DEFERRED`, and `05` §11.2's client action is *"Keep; retry next sync."* Putting
it in front of a salesman would report a problem where none exists, and there is no action the
salesman could take if they believed it.

**It is not excluded everywhere — it is excluded from *this* audience.** `04` T-26's index
spans `('DEFERRED','REJECTED')` and is named *"the **owner's** exception list"*. For the owner,
a `DEFERRED` that never clears is a real signal; for the device user it is noise. **Two
audiences, two sets**, and that distinction is why this decision governs FR-SYN-008 and
explicitly not FR-SYN-009 (§6 below) or D-M9-5's owner view.

> **Observed while auditing, recorded rather than fixed:** `deferred_count` is decoded into
> `ServerSyncStatus.deferred` and **never rendered**. Under this decision that is correct for
> the device screen; it is noted so a later reader does not mistake it for an oversight.

#### 4. Why M8's *"failed count"* is drift evidence, not authority

`M8_Design_Review` §3 records *"Last sync, pending count, **failed count** (FR-SYN-008)"*.

**Useful as corroboration.** A second reader, one milestone earlier and independently, also
found *"unresolved conflicts"* unusable and reached for a word meaning *"the server would not
take it."* Two independent substitutions of the same requirement is the strongest evidence
that the phrase was never implementable.

**Not adopted, and not normative.** *"Failed"* implies a malfunction; a rejection is a
**decision the server made and recorded with a mandatory reason**. *"Failed"* would also be
naturally read to include transport failure — `Offline`, a timeout — which is neither
`REJECTED` nor a server verdict at all. And it appears in a **design review's summary table**,
which has no authority to reword `02`. **That it did so in passing is itself a finding**, of
the same class as `SyncConflict` and D-M9.4-6/7: a term changed somewhere the amendment
register cannot see.

#### 5. The proposed replacement

> **FR-SYN-008** — *"The device MUST display its last successful sync time, count of pending
> transactions, and **count of operations the server has rejected**."*

Every word is already frozen vocabulary: *"operations"* is `05` §11.2's array and `04` T-26's
table; *"rejected"* is a status value in `04` T-26, `05` §11.2 and `05` §11.5; *"count of"* is
carried over verbatim. **No new noun is introduced.**

*"Refused by the server"* was considered and is the better UI phrasing — it is what the screen
already says — but *"refused"* is not a frozen status word, and a requirement should name the
status. **The softer word belongs in interface copy, not in `02`.**

Priority `M` and release `v1.0` are **both preserved**. Nothing is deleted.

#### 6. FR-SYN-009 is separate, and stays unresolved

**No part of this decision applies to FR-SYN-009.** It is a different surface (`S1`), different
actors (`SALESMGR`, `ADMIN`) and different granularity (*"per device"*), and it is unmet on
**all three** of its fields — not merely the third. Its blocker is the absence of any `S1` sync
surface: no `webadmin` view, no endpoint, no selector, no test. `03`'s observability section
places it in the back-office — *"Sync status per device visible in the admin
(FR-SYN-009)"* — while `05` §11.5 claims it in a caption and **D-M9.3-1** — `device_id` from the JWT,
*"never from the request"* — makes that endpoint structurally incapable of describing another
device.

**Fixing FR-SYN-008's terminology leaves FR-SYN-009 exactly as it was.** It remains §9 item 2,
`M`/`v1.0`, unamended, requiring its own ruling — and that ruling is entangled with D-M9-5 /
OC-3, because both need the same `S1` surface.

#### 7. No API, schema or logic change follows

**The existing `rejected_count` is reused unchanged.** No field is added, renamed or retyped;
`05` §11.5 does not change; `04` T-26 does not change; `backend/sync/selectors.py` does not
change. The number is already on the device screen — `server.rejected` — and is already
correct.

**What does follow, and only after `02` S-5 is written**, is a label. The screen currently
renders that number under widget key `sync.conflicts` as *"No conflicts"*, asserting an
equation no document makes and which **D-M9-3 arguably contradicts**, having placed `REJECTED`
in FR-SYN-006 quarantine rather than the §5.3 taxonomy. **That change is display text, and it
is deliberately downstream of the amendment, not part of this decision.**

> **A second defect will need fixing in the same edit, and is not a terminology question.**
> When the server is unreachable the screen renders the title *"No conflicts"* — a definite
> claim about a quantity it did not measure — three lines below its own comment stating that
> *"showing a zero would be a number nobody measured"*. **That is a P-8 violation** and it
> stands independently of what the field ends up being called.

#### 8. What this decision authorises

**`02` amendment S-5**, and nothing else. Recorded in §11. **S-5 is not written by this
document and must not be inferred from it** — the wording in §5 above is a proposal for the
amendment pass, which is a separate turn.

### D-M9-7 — FR-SYN-009 moves to `Rel = v2.0`

*Added in v1.2.0, 2026-08-21. Authorises `02` amendment **S-6**, which is **not yet written**.*

#### 1. The requirement, and what it asks Edition 1 for

`02` FR-SYN-009 *(M, v1.0, surface `S1`, trace §5.4)*:

> *"`SALESMGR` and `ADMIN` MUST be able to view, per device: last sync time, pending
> transaction count and unresolved conflicts."*

It asks for four things Edition 1 does not have: an **admin console**, the **`SALESMGR`**
role, the **`ADMIN`** role, and a **registered device** to view *"per"*.

#### 2. Three independent Edition-1 exclusions, each sufficient on its own

| # | Prerequisite | Where `02A` defers it | Corroborated by |
| --: | --- | --- | --- |
| 1 | **Admin console** | §7.12 (M-15 Sync): *"Sync status visible to user \| … \| Ed **1** \| Y \| **Admin console (2)**"* — the same row that places the device-facing view in Edition 1 places the console in Edition 2 | — |
| 2 | **`SALESMGR` / `ADMIN` roles** | §7.1: *"Four fixed roles … **Four roles cover every confirmed user**"*; §2.2 names them Owner, Salesman, Delivery, Retailer | `backend/core/permissions.py` — `OWNER`, `SALESMAN`, `DELIVERY`, `RETAILER`. **Neither actor FR-SYN-009 names exists** |
| 3 | **Registered device** | §13.2, recorded in `04`: *"`device` \| Registered device records \| **Device registration demoted (`02A` §13.2)** … \| **Edition 2**"* | `sync_operation.device_id` is `VARCHAR(64)`, **not a foreign key**. Nothing enumerates devices; `04` future-evolution confirms *"Edition 2 adds `device` as a table"* |

**This is not a judgement call in the way D-M9-3 was.** D-M9-3 chose between two coherent
readings of an ambiguous corpus. Here there are three recorded deferrals, made by the document
that governs edition membership, which `02` was never told about — the same cause and the same
shape as S-1 … S-4.

#### 3. The two documents that appear to say otherwise are inconsistencies, not counter-evidence

- **`03` §11.3** — *"Sync status per device visible in the admin (FR-SYN-009)."* `03` derives
  its scope from `02A` by `02A`'s own Governs clause, so where it asserts a capability §7.12
  defers, **`03` is the document out of step.**
- **`05` §11.5** — captioned *"Nothing fails silently (FR-SYN-008/009)"*, while **D-M9.3-1**
  freezes `device_id` as *"taken from the authenticated JWT claim, **never from the request**"*.
  The endpoint cannot describe any device but the caller's; the caption over-claims.

**Neither is evidence that the Edition-2 prerequisites belong in Edition 1.** Both are
documentation inconsistencies of the class this review exists to record. **Neither is amended
here** — `03` and `05` are outside this decision's scope and are listed in §8.

#### 4. What is preserved

- **Priority `M` is unchanged.**
- **The requirement text is unchanged.** Only the `Rel` column moves.
- **Nothing is deleted.** `02` §18.1's preamble governs: *"A requirement moved to v2.0 is still
  a requirement; a reader must be able to see it was considered and deferred rather than
  forgotten."* Same treatment as FR-SYN-013/014 (S-2), FR-REC-004 (B-1) and FR-RPT-006 (A-3).
- **It returns with the capability that creates its subject** — the Edition-2 admin console,
  the wider role set and the `device` table. `04` T-26's *"Future evolution"* and `02A` §7.12
  already commit to all three, so this is a deferral onto an existing plan, not an open end.

> **A side benefit worth recording.** FR-SYN-009 carries the same undefined phrase — *"unresolved
> conflicts"* — that D-M9-6 removed from FR-SYN-008. Moving the requirement to v2.0 disposes of
> that phrase without having to define it for a surface Edition 1 will not build. **After S-5
> and S-6, `02` contains no live Edition-1 use of the term.**

#### 5. OC-3 is separate, is Edition 1, and is not discharged by this decision

**The back-office half of §5.4 is not abandoned by moving FR-SYN-009.** *"Nothing fails
silently"* has an Edition-1 asker — the **OWNER**, the only internal administrator the edition
has — and an Edition-1 data source, `sync_operation`. That obligation is already open as
**OC-3** under FR-SYN-006's *"quarantined **and reported**"* (D-M9-5).

**Same surface, different requirements. They must not be merged:**

| | OC-3 | FR-SYN-009 |
| --- | --- | --- |
| Surface | `S1` | `S1` |
| Actor | **OWNER** — exists | `SALESMGR` / `ADMIN` — do not exist in Edition 1 |
| Scope | Exceptions: `REJECTED` rows, reason and identity | Per-device status: last sync, pending count, conflicts |
| Edition | **1 — unmet, and owed** | **2, under this decision** |
| Blocker | `05` specifies no shape (D-M9-5) | The `device` table, the console and the roles |

Merging them would drag an Edition-2 dependency into an Edition-1 deliverable. **One `05`
amendment can specify OC-3 alone; FR-SYN-009's per-device grouping cannot be built before the
`device` table exists.**

**Minimum Edition-1 capability, stated so it is not over-built:** an owner-readable list of
`sync_operation` rows in `REJECTED`, with reason and operation identity, on `S1`. **Nothing
about devices, nothing about roles that do not exist, no per-device counts.** That is OC-3, and
its shape is still unspecified and still not proposed here.

#### 6. FR-SYN-009 is not implemented in M9, and none is required

**No API, schema, code or test change follows from this decision.** M9 implements
`GET /sync/status` caller-scoped (D-M9.3-1) and nothing else; there is no `S1` sync surface, and
this decision creates no obligation to build one. **FR-SYN-009 leaves Edition 1 unbuilt, by
ruling, and that is the whole of its effect.**

#### 7. Independent review — supporting evidence, not authority

An independent review by Gemini reached Option C separately: FR-SYN-009 stays priority `M` and
moves to `v2.0`; Edition 1 lacks the admin console, the `SALESMGR`/`ADMIN` roles and the
registered device entity; `03` §11.3 and `05` §11.5 are documentation inconsistencies rather
than evidence that the prerequisites belong in Edition 1; OC-3 remains separate and Edition 1;
no API, schema or code is required.

**This is recorded as corroboration, and it is not the authority for this decision.** The
authority is the Product Architect ruling of 2026-08-21 accepting Option C, resting on `02A`
§7.12, §7.1 and §13.2 as quoted in §2 above. Two readers agreeing is evidence that the reading
is available to a careful reader; it is not evidence that it is correct, and it confers no
standing the corpus does not already give `02A`. *(Same treatment as `M7_Design_Review` §17,
where an independent review produced findings that were then evaluated on their own merits
rather than adopted.)*

#### 8. What this decision authorises

**`02` amendment S-6**, and nothing else. Recorded in §11. **S-6 is not written by this
document.** `03` §11.3 and `05` §11.5 remain inconsistent and are recorded in §8 as open
contract work — **they are not amended here.**

---

### D-M9-8 — The Edition-1 cipher is SQLite3MultipleCiphers, not SQLCipher. §5.6 is amended, not reversed.

**Ruled 2026-08-25.** Authority for the `M8_Design_Review` §5.6 amendment, applied the same day
at v1.8.0. **This is the only decision in this document that touches an ADR**, and it touches
one clause of one.

#### 1. The requirement is unchanged and receives no amendment

`02` says this, and only this:

> `FR-SYN-016` | Local device storage MUST be encrypted at rest. | `M` | `v1.0`
>
> `NFR-SEC-008` | Device local storage MUST be encrypted at rest (FR-SYN-016). | *Device
> inspection test*

**Neither names a cipher, a library or an algorithm.** SQLCipher appears nowhere in `02`; it
appears in the *design*. So no `S-` row is authorised here and `02` §18.1 is not opened. That
distinction is the whole shape of this decision: what changed was never a requirement.

#### 2. Three layers, deliberately kept apart

| Layer | Statement | Status |
| --- | --- | --- |
| **Requirement** | the device database is encrypted at rest | **binding** — FR-SYN-016, NFR-SEC-008, unamended |
| **Implementation** | `sqlite3: source: sqlite3mc`, selected by the `package:sqlite3` build hook | **frozen for V1** — this decision |
| **Observation** | `PRAGMA cipher` → `chacha20`; `PRAGMA sqlite_version` → `3.53.4` | **recorded, not binding** |

**The observation is deliberately not promoted to a requirement.** `chacha20` is
SQLite3MultipleCiphers' current default. Pinning it would turn a routine library upgrade into
an apparent security regression, and would put the same claim in a fourth place — the pubspec
hook, `connection.dart`'s probe, the structural contract, and then here. An assertion repeated
in four places is one that gets deleted rather than updated.
`make mobile-device-encryption` therefore **records** the cipher and **asserts only that one is
present**.

#### 3. Why SQLCipher was not carried forward — three findings, in order of discovery

**(a) It was never actually in use.** `sqlcipher_flutter_libs` exposes `openCipherOnAndroid()`
for `open.overrideFor`, an API `package:sqlite3` 3.x **removed**. No call site was possible in
the pinned versions. The APK built 2026-08-24 carried `lib/x86_64/libsqlite3.so` — upstream
SQLite, no codec — beside 13.8 MiB of `libsqlcipher.so` across three ABIs that nothing could
open, with `native_assets.json` resolving `package:sqlite3` to the former.

> **`PRAGMA key` against upstream SQLite is an unrecognised pragma. It does not fail; it is
> ignored.** The outbox was written in cleartext for a milestone, and no test in the repository
> could see it. This is recorded plainly because the *shape* of the defect — a dependency that
> looked like a satisfied requirement — is the reusable lesson, not the cipher.

**(b) `source: sqlcipher` was tried first, and does not run in the pinned environment.** The
build hook selected it correctly; its Linux prebuilt, rebuilt in `sqlite3` 3.5.2, requires
`GLIBC_2.38`, and `docker/flutter.Dockerfile` is `debian:bookworm-slim` — **GLIBC 2.36**. 151
of 317 tests died in `dlopen` before reaching any assertion.

**(c) `source:` is a single global value.** Per-OS selection is unimplemented upstream
(`simolus3/sqlite3.dart#346`, open, no linked PR), so one library must serve both the
verification container and the Android target. `sqlite3mc` does. That it also means **CI runs
the same engine the device runs** is the stronger reason: the fail-closed guard in
`connection.dart` now executes on the host, where nothing previously could.

#### 4. Why this was free now, and will not be later

§5.6 warns that the choice is *"irreversible in the sense that matters: changing it after M9
means migrating outboxes on devices in the field."*

**There are no devices in the field.** The one emulator database was plaintext and had to be
cleared regardless. §5.6's condition never triggered — which is precisely why this was settled
before M11 rather than discovered after it. Drift documents a `VACUUM INTO` + `PRAGMA rekey`
path for migrating an existing plaintext database; **it was deliberately not built**, because
building a migration for a population that does not exist is speculative code.

#### 5. What is unchanged

The key source is unchanged: **the Android keystore, via `PlatformDatabaseKey`**, minted once
per install with `Random.secure()` and never cleared on sign-out (§8.3 — the outbox must
outlive the session). `DatabaseKeyProvider`, its seam and its behaviour are untouched. So is
Drift, so is the schema, so is every migration.

#### 6. Verification — stated without overstating it

| | |
| --- | --- |
| Target | **Pixel 8a API 34 emulator, `android-x64`** |
| **Not covered** | **`arm64`, and physical hardware of any kind** (TD-45) |
| Artefact | `lib/x86_64/libsqlite3mc.so` present; `libsqlite3.so` and `libsqlcipher.so` absent |
| `PRAGMA cipher` | `chacha20` |
| `PRAGMA sqlite_version` | `3.53.4` |
| Correct key | reopened the database and recovered the row and payload |
| Wrong key | a real read threw `SqliteException`, `resultCode = 26` (`SQLITE_NOTADB`), non-destructively |
| Bytes on disk | no `SQLite format 3\0` header and no plaintext marker, in the database **or** the WAL; ordinary `sqlite3` refuses the file |
| Falsifiability | the same scanner is run against a deliberately unencrypted database and must find those markers |
| Gate | `make mobile-device-encryption` |
| Host suites | `make verify` VERIFIED · 829 backend tests · 94.54% · `make mobile-verify` 317 |

**The encryption gate is closed. The M8 → M9 durability gate is not.** `00` §19.2 requires
*"Outbox survives kill, restart and storage exhaustion"*; `make mobile-device-kill` and
`make mobile-device-storage` exist and have **no recorded run**. §9 item 5 stays open and is
**not** closed by this decision. Nothing here may be cited as evidence for it.

#### 7. Technical debt opened

**TD-37 is unchanged and remains open.** TD-42 is strictly stronger and does not replace it.

| # | Item | Why it is debt rather than a decision |
| --- | --- | --- |
| **TD-42** | **No Android SDK or JDK in the pinned toolchain image.** `grep -inE "android\|jdk\|sdkmanager\|adb" docker/flutter.Dockerfile` returns nothing, so every Android artefact is produced by an **unpinned host toolchain** that `make verify` cannot see, and no device gate can run in CI. **Amended 2026-09-01:** the second half of this — *"no shell where both `make` and `flutter` work"* — is **no longer true**. `make` in WSL reaches the Windows Flutter launcher through `scripts/win-flutter.sh`, and `make mobile-device-kill` passed that way (`M8_Design_Review` §5.6.1). The **first** half stands unchanged: the pinned image still carries no Android SDK or JDK, so device gates remain host-dependent and cannot run in CI | a gap in the gate with a known fix nobody has costed |
| **TD-43** | **`PRAGMA key = '$key'` is unescaped string interpolation** in `connection.dart`. Safe today only because `PlatformDatabaseKey._mint()` emits 64 hexadecimal characters — safe by accident, not by construction | latent; not currently reachable |
| **TD-44** | **`libsqlite3-0` in `docker/flutter.Dockerfile` is very likely unnecessary** since `package:sqlite3` 3.x bundles its own library through the build hook. Its justifying comment is already false | removal needs an image rebuild and a full gate run to disprove |
| **TD-45** | **`arm64` and physical hardware are unproven.** The encryption gate covers `android-x64` on an emulator only | a coverage gap, not a defect |

#### 8. What this decision authorises

**The `M8_Design_Review` §5.6 amendment, and nothing else.** No `02` amendment, no API change,
no schema change, no requirement change. The production changes it *records* — the build hook,
the fail-closed guard, the structural contract, the permanent gate and the removal of
`sqlcipher_flutter_libs` — were implemented and verified before this document was written; this
records them, it does not authorise them.

---

## 7. Explicitly preserved

Stated positively so that no future reader mistakes this review for a licence to build.

| # | Preserved | Authority |
| --: | --- | --- |
| **P-M9-1** | **No `SyncConflict` schema is created.** No table, no model, no migration, no `PENDING_RESOLUTION` status value | D-M9-2 |
| **P-M9-2** | **No conflict resolution console exists in Edition 1.** Zero classes require human resolution | `02A` §5 · `05` §11.4 · `M8_Design_Review` §3.5 · D-M9-4 |
| **P-M9-3** | **`sync_operation` is unchanged.** Columns, constraints, indexes and status vocabulary stand exactly as `04` T-26 defines them | D-M9-2 |
| **P-M9-4** | **`POST /sync/push`, `GET /sync/status` and `GET /sync/pull` remain valid as shipped.** No endpoint, payload, field or status value changes | D-M9-1 |
| **P-M9-5** | **The mobile drain, cache and start-up chain remain valid as shipped** (M9.2, M9.4) | D-M9-1 |
| **P-M9-6** | **`conflict_type` and the four human classes remain Edition 2**, as new `status` values on the existing table | `04` T-26 *"Future evolution"* · EP-5 |
| **P-M9-7** | **`error_code` is a quarantine reason, never an `SC-*` class** | D-M9-3 |

**No production code, test, schema, API or contract changes as a consequence of this review.**

---

## 8. Open contract work

Work this review creates. **All of it is documentation; none of it is code.**

| # | Work | Owner | Blocks |
| --: | --- | --- | --- |
| **OC-1** | Amend `02` per §11 — S-1…S-4 | Product Architect | The corpus reading correctly |
| **OC-2** | Amend `05` §11.4 to cite FR-SYN-005/013/014 and the A-rows, so it stops appearing to contradict `02` unilaterally | Product Architect | — |
| **OC-3** | **Specify the owner-facing rejection view in `05`** (D-M9-5). Shape unspecified, deliberately | Product Architect | Any implementation of FR-SYN-006's *"reported"* clause |
| **OC-4** *(v1.2.0)* | **`03` §11.3 asserts *"Sync status per device visible in the admin (FR-SYN-009)"***, a capability `02A` §7.12 places in Edition 2. `03` derives its scope from `02A`, so `03` is the document out of step. **Not amended by D-M9-7** | Product Architect | — |
| **OC-6** *(v1.3.0)* | **Register TD-42…TD-45 in `PROJECT_STATE.md`'s technical-debt table**, where TD-1…TD-41 are held. D-M9-8 opens them; this document is not their register. Also: `PROJECT_STATE.md` and `NEXT_TASK.md` each still describe the §5.6 ADR as *"Drift + SQLCipher"* | Engineering | An accurate debt register |
| **OC-5** *(v1.2.0)* | **`05` §11.5's caption *"Nothing fails silently (FR-SYN-008/009)"* over-claims.** After S-5 the FR-SYN-008 half is genuine; the FR-SYN-009 half is unreachable by D-M9.3-1's JWT scoping and, after S-6, no longer an Edition-1 obligation. **Not amended by D-M9-7**; naturally pairs with OC-2 | Product Architect | — |

> **OC-3 is the only item that creates future engineering work**, and it cannot start until
> `05` describes what is to be built.
>
> **Adjacent, deliberately not merged:** FR-SYN-009 (`SALESMGR`/`ADMIN` per-device view, §9)
> needs the same `S1` surface. Specifying the two together would be cheaper than specifying
> them twice. **That is a sequencing observation, not part of any ruling here.**

---

## 9. M9 open items not addressed by this review

**None of these is resolved, deferred, waived or superseded by this document.** They are
listed so that no reader mistakes the conflict ruling for a complete M9 closure. Detail and
evidence are in `PROJECT_STATE.md` *"Open at M9"*.

| # | Item | State |
| --: | --- | --- |
| 1 | **FR-RPT-009** — sync health report, placed *at M9* by `02` ruling A-5 and `M7_Design_Review` §C-4. No implementation; **no endpoint in `05`** | Open |
| ~~2~~ | ~~**FR-SYN-009** — `SALESMGR`/`ADMIN` per-device view~~ | **RULED — D-M9-7 (v1.2.0).** Moves to `Rel = v2.0`; leaves Edition 1 unbuilt. `02` amendment **S-6** authorised and unwritten. **The `03` §11.3 and `05` §11.5 inconsistencies it exposed remain open** — §8 OC-4, OC-5 |
| 3 | **FR-SYN-007 remainder / stock snapshot** — D-M9.4-2 implements customers and deliveries only; D-M9.4-1 records the stock snapshot as an unclosed contract gap | Open — recorded gap |
| 4 | **Orphaned `RECEIVED` recovery** — `05` §11.5 deferred it *"to M9.4/M10"*; M9.4 shipped without it | Open |
| 5 | **M8 → M9 gate** (`00` §19.2, M8 task 10) | **No recorded evidence of this gate was found in the repository** — an absence of an artefact, not proof that nothing was run |
| 6 | **M9 → M10 gate** — *"adversarial sync suite passes: zero loss, zero duplicates"* | **The suite does not exist** — `backend/tests/adversarial/` holds 13 suites, none for sync |
| 7 | **TD-41 / FR-SYN-010** — launch-only sync trigger; no connectivity mechanism in the frozen mobile stack | Open |

---

## 10. Irreversible decisions — signed

| # | Decision | Why it is hard to undo |
| --: | --- | --- |
| **M9-1** | **`sync_operation` is the single server-side record of a device write, and its `client_uuid` unique constraint is the idempotency guarantee** | Every accepted operation in production is keyed by it. Changing the vehicle later means migrating live evidence of transactions already applied |
| **M9-2** | **No `SyncConflict` table in Edition 1** (D-M9-2) | Adding one later is cheap; *removing* one after it has accumulated rows is a migration of records the business was told were never lost |
| **M9-3** | **The four human conflict classes and `conflict_type` are Edition 2 `status` values on the existing table** (`04` T-26) | This is EP-C's *extension-not-rewrite* claim made concrete. A different Edition-2 shape breaks it |
| **M9-4** | **`error_code` is a free quarantine reason, not a class enumeration** (D-M9-3) | Once field devices have shipped against it, constraining it is a wire-contract change (C-7) |

---

## 11. Amendments this review authorises

**This document is the design-review authority cited by `02` §18.1 rows S-1 … S-4.** Content
below is the *substance* to be recorded; the exact wording belongs to whoever writes the
amendment.

> **Renumbered from `A-8…A-11`, 2026-08-21.** This section originally named the rows
> `A-8…A-11`, which was wrong on two counts and was caught while applying them. `02` keeps
> **per-block amendment logs with per-block prefixes** — `A-` is §20.1's Reporting series
> (A-1…A-7, every one an FR-RPT line) and `B-` is §14.1's Receivables series (B-1, B-2). Four
> synchronisation amendments belong in a **new §18.1** under their own prefix. `A-8` would
> also have collided with an unrelated namespace: FR-REC-010 already traces an **assumption**
> called `A-7`. **The substance of the four rows is unchanged; only their identifiers and
> their location are.**

| Row | Change to `02` | Cites |
| --- | --- | --- |
| **S-1** | **FR-SYN-005** — annotate in place: in Edition 1 the §5.3 taxonomy reduces to the two automatic classes; the persistence clause is discharged by `04` T-26; `SyncConflict` (§4.1) is a conceptual entity name, not a schema mandate. **`Rel` unchanged at v1.0** | `02A` §5 · `04` T-26 · M9 §6 D-M9-2 |
| **S-2** | **FR-SYN-013** and **FR-SYN-014** → `Rel = **v2.0**`, annotated in place, priority unchanged, nothing deleted | `02A` §5, §6.2, §7.12 · `04` T-26 *"Future evolution"* · M9 §6 D-M9-4 |
| **S-3** | **BR-014** — annotate that the Edition-1 vehicle is `sync_operation` with retained `payload`, not a `SyncConflict` table. **The guarantee is unchanged; only the named artefact** | `04` T-26 · `03` §6.2 · M9 §6 D-M9-2 |
| **S-4** | **§5.3** — record that four classes are Edition 2 per `02A` §5, and that **FR-SYN-006's quarantine path is distinct from this taxonomy** | `02A` §5 · M9 §6 D-M9-3 |
| **S-5** *(v1.1.0)* | **FR-SYN-008** — replace the undefined *"count of unresolved conflicts"* with *"count of operations the server has rejected"*, annotated in place. **`M` and `v1.0` both preserved**, nothing deleted. Maps to the existing `rejected_count`; **no API, schema or logic change**. **FR-SYN-009 is not touched by this row** | `05` §11.2, §11.5 · `04` T-26 · M9 §6 D-M9-6 |
| **S-6** *(v1.2.0, **not yet written**)* | **FR-SYN-009 → `Rel = v2.0`**, annotated in place. **Priority `M` and the requirement text are unchanged; nothing is deleted.** Edition 1 has no admin console (`02A` §7.12), no `SALESMGR` or `ADMIN` role (§7.1 — four fixed roles) and no registered `device` entity (§13.2, `04`). Returns in Edition 2 with all three. **OC-3 remains a separate, unmet Edition-1 requirement** and is not discharged by this row; **no API, schema, code or test change follows** | `02A` §7.12, §7.1, §13.2 · `04` (`device` — Edition 2) · M9 §6 D-M9-7 |

> **S-1 … S-4 were applied to `02` on 2026-08-21 and are recorded at `02` §18.1. S-5 was
> applied the same day. S-6 is authorised and unwritten** — the wording above is a proposal
> for a separate amendment pass, and must not be treated as though it were already in `02`.

**`02` §18.1's preamble governs all six:** *"Nothing here was deleted. A requirement moved to
v2.0 is still a requirement; a reader must be able to see it was considered and deferred
rather than forgotten."* §18.1 carries that sentence in its own right; §20.1's identical
preamble governs the Reporting series and not these rows.

---

## 12. Risks

| # | Risk | Mitigation |
| --: | --- | --- |
| **AR-M9-1** | **A future reader takes D-M9-3 as licence to reject anything and call it quarantined.** BR-014's guarantee is that nothing is lost, not that rejection is cheap | P-M9-7 and the `ck_sync_operation_rejected` constraint: a rejection without a reason is refused by the database |
| **AR-M9-2** | **D-M9-5 stays open indefinitely**, because it is documentation work blocking documentation work | OC-3 has a named owner. It is also the only unmet v1.0 requirement in the conflict model, which makes it a go-live item, not a nicety |
| **AR-M9-3** | **Edition 2 builds the four classes somewhere other than `sync_operation.status`**, breaking EP-C | M9-3 recorded as irreversible |
| **AR-M9-4** | **The same procedural failure recurs.** It has now happened twice — FR-REC-004 at M6, FR-SYN-005 at M8/M9 | Recorded in §13. The structural answer would be a check that every `M`/`v1.0` requirement is either implemented or carries an A-row; none exists today |

---

## 13. Self-critique

**1. This review is late, and lateness is the finding.** Every prior milestone froze its
design before implementation. M9 did not, and the cost is visible: two decisions were cited
by identifier in shipped source (`cached_round.dart` → D-M9.4-6, `bootstrap.dart` →
D-M9.4-7) while existing in no document, and were only caught by a pre-commit audit. A
review written first would have produced the A-rows before `05` §11.4 needed them.

**2. The corpus contradiction was visible from M8 and nobody looked.** `M8_Design_Review`
§3.5 lists *"Conflict resolution — `02A` §5 — zero classes need human resolution"* under
*"deliberately absent, with authority"*. It cited the authority correctly and did not check
whether `02` had been told. The same document did that check properly for two *other*
conflicts (§3.4.1 TD-36, §3.4.2 OI-7), which makes the omission harder to excuse, not easier.

**3. D-M9-3 is the weakest decision here, and it should be read as a ruling rather than a
finding.** The FR-SYN-005 / FR-SYN-006 split is coherent and it fits every observed fact —
but `02` does not state it, and a different reader could reasonably have concluded that
FR-SYN-005's *"every rejected transaction"* means exactly what it says and that Edition 1
therefore owes a class for validation failures. **The corpus was genuinely ambiguous and this
document removes the ambiguity by choosing.**

**4. `M6_Verification_Report` §8.2 predicted this exact failure and it recurred anyway.** It
wrote: *"the next person to read `02` cold will conclude that Edition 1 allocates payments to
invoices."* Substitute *"ships a conflict resolution console"* and the sentence is this
review's §6 D-M9-1. A lesson recorded once and not made structural is a lesson that gets
learned twice.

**5. What this review does not know.** Whether the M8 → M9 gate was ever executed. The
repository holds no artefact either way, and §9 item 5 states that as an absence rather than
as a negative claim.

---

## 14. Sign-off

| Item | State |
| --- | --- |
| R-1 … R-5 accepted as Product Architect ruling | ✔ 2026-08-21 |
| Recorded here as **D-M9-1 … D-M9-5** | ✔ |
| **T-3 ruling accepted; recorded as D-M9-6** | ✔ **2026-08-21, v1.1.0** |
| **FR-SYN-009 ruled (Option C); recorded as D-M9-7** | ✔ **2026-08-21, v1.2.0** — independent Gemini review recorded as **corroboration, not authority** |
| Authority for `02` §18.1 rows **S-1 … S-4** | ✔ §11 — **applied to `02`** |
| Authority for `02` §18.1 row **S-5** | ✔ §11 — **applied to `02`** |
| Production code, tests, schema, API changed by this review | **None** |
| `02`, `04`, `05` amended by this review | **None** — §8 records the work; §11 records its substance |
| Owner-facing rejection view implemented | **No.** D-M9-5 and OC-3. No shape specified, none proposed |
| **FR-SYN-009 implemented in M9** | **No, and none is required.** D-M9-7 moves it to `v2.0`; it leaves Edition 1 unbuilt |
| **`02` amended for S-6** | **No.** Authorised by D-M9-7, not written |
| **`03` §11.3 / `05` §11.5 reconciled** | **No.** OC-4 and OC-5, opened by D-M9-7, not amended by it |
| **`sync.conflicts` label approved** | **No.** D-M9-6 §7 — downstream of S-5, not part of this decision |
| M9 closed by this review | **No.** §9 lists seven items untouched by it |

> **What this document settles:** the Edition-1 conflict model, and the authority to amend
> `02` accordingly.
>
> **What it does not settle:** whether M9 is finished. §9 is the answer to that, and it is
> still seven items long.
