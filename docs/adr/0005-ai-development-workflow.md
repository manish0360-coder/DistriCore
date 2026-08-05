# 0005 — AI-assisted development workflow

Status: **Proposed — requires ratification (§P.4)**
Date: 2026-08-05
Deciders: Founder, Chief Systems Engineer
Supersedes: none
Amends: `00_Engineering_Foundation.md` §P.5 (roles), adds §5a (session lifecycle)

---

## Executive Summary

The stated problem is "my Claude Pro account hits its weekly limit mid-milestone; should I
switch to a second account?"

**That is the wrong problem.** Three findings:

1. **Token quota is not the binding constraint on this project. Founder review capacity
   is.** You are the only human who can confirm that generated code is correct. Adding a
   second AI account doubles output and does not move review capacity at all. It converts a
   throughput problem into a queue of unreviewed work — which is worse, because unreviewed
   AI output looks finished.

2. **Two accounts to circumvent a per-account limit is a terms-of-service question, not an
   engineering one.** Anthropic ships Max tiers and purchasable usage credits precisely for
   sustained heavy use. Building the permanent workflow of a company you intend to scale on
   top of something that may violate a supplier's terms is a poor foundation. **Verify this
   with Anthropic before adopting it**; do not take my word or your own inference.

3. **The handoff problem is real but the proposed fix is wrong.** A hand-maintained
   `SESSION_CONTEXT.md` is a second source of truth that will drift from git. Your own
   constitution rates drifting documentation as worse than none (C-1, NFR-DOC-001). The
   correct fix is to make the gap smaller — **commit at task granularity, not milestone
   granularity** — and to *generate* the session brief from git rather than write it.

**Recommendation: one identity with elastic capacity, task-level git checkpoints, and a
generated session brief.** Not two accounts.

---

## 1. First-Principles Analysis

### 1.1 What actually limits output

| Resource | Elastic? | Cost to add |
| --- | --- | --- |
| AI tokens | **Yes** — Max tiers, usage credits, API billing | Money, linearly |
| AI wall-clock | Yes | Money |
| **Founder review capacity** | **No** | Cannot be bought |
| Founder decision capacity | No | Cannot be bought |
| Repository comprehensibility | Degrades with volume | Paid in discipline |

Only one row is inelastic and it is the one you cannot outsource. Every workflow below is
scored primarily on whether it respects that.

**Evidence from this project.** M0 and M1 each required four verification cycles before
passing. Every cycle was a real defect — including `verify_otp` silently discarding its own
security counter, which read correctly and would have passed any human review. The value
produced was not the code; it was the **verification that found the defects**. Doubling code
production without doubling verification capacity produces more undetected defects, not more
product.

### 1.2 What a session actually is

An AI session is three things bundled together, and they should be unbundled:

| Component | Should live in | Currently |
| --- | --- | --- |
| **Durable knowledge** — decisions, specs, architecture | Repository | Repository ✓ |
| **Work product** — code, tests, docs | Git | Git ✓ |
| **Working memory** — what I just tried, what failed, why | Session only | **Session only — this is the gap** |

Only the third is lost when a session ends. It is also the smallest and least valuable of the
three. The engineering answer is to **shrink it**, not to serialise it into a file.

Working memory shrinks toward zero as commit frequency rises. At milestone-level commits it
is hours of context. At task-level commits it is minutes. **Commit frequency is the real
handoff mechanism.**

### 1.3 The falsifiable test for a replaceable worker

> **Delete the entire conversation. Can a fresh session resume within ten minutes?**

DistriCore is close to passing. What it has: specification before code, mechanical
verification (`make verify`), enforced architecture (`import-linter`), ADRs, verification
reports, `PROJECT_STATE.md`.

What it lacks: **task-level granularity**. M1 was 92 tests, 5 tables, 3 modules and 8
endpoints in one unit. A session dying halfway through leaves a working tree no document
describes. That is the actual failure, and no scratchpad fixes it.

### 1.4 Why a hand-written session file rots

`SESSION_CONTEXT.md` would be written at the end of a session, by the party with the least
incentive to write it accurately (a session about to end), describing state that git already
knows (branch, diff, commits) plus state that changes every few minutes. It has every
property of documentation that drifts:

- duplicates a source of truth (git)
- has no verification gate
- is stale the moment it is written
- nothing fails when it is wrong

The one thing it would carry that git does not is **negative results** — "I tried X, it
failed because Y". That is genuinely valuable and genuinely absent. It deserves a file. It
does not deserve a file that also duplicates git.

---

## 2. Alternative Workflows

### A. Single Pro account

**Advantages.** Cheapest. One identity, one history, one billing relationship. No context
splitting. Simplest possible model.

**Disadvantages.** Hits weekly limits during sustained milestones — the observed problem.

**Failure mode.** Work stops mid-milestone. If the working tree is dirty and uncommitted,
the loss is real.

**Hidden cost.** Encourages large uncommitted batches, because the developer is racing the
quota. That is the *opposite* of the discipline this project needs.

**Verdict.** Correct model, insufficient capacity.

---

### B. Two Pro accounts on separate emails

**Advantages.** Immediate continuity. No new spend beyond a second subscription. Technically
trivial.

**Disadvantages.**
- **Terms-of-service exposure.** Using multiple accounts to circumvent a per-account limit is
  plausibly a violation. I cannot quote Anthropic's exact wording and will not pretend to —
  **you must verify.** A company that intends to raise money and hire cannot have a core
  process that may be non-compliant with a critical supplier.
- **No gain on the binding constraint.** Review capacity is unchanged.
- **Split conversation history.** Account B cannot see account A's threads. Every switch is a
  cold start. In practice, the repository has to be good enough that this does not matter —
  and if the repository is that good, you did not need account B's history anyway.
- **Two billing relationships, two security surfaces, two credential sets.** At company scale
  this becomes an audit finding.

**Failure mode.** Account suspension mid-milestone — strictly worse than the problem being
solved. Or, more likely and more insidious: the founder ships twice the unreviewed code.

**Long-term maintainability.** Poor. Does not survive hiring. "Log into my other account" is
not a process you can hand to an employee.

**Verdict.** Solves the symptom, ignores the constraint, adds compliance risk. **Not
recommended.**

---

### C. Claude Max (5× or 20× Pro per session, plus weekly limits)

**Advantages.** The sanctioned answer to sustained use. One identity, one history, one bill.
Scales with a slider rather than an account switch. Works with Claude Code and the Agent SDK
on the same plan. No compliance question.

**Disadvantages.** Higher monthly cost. Still has a ceiling — larger, not infinite.

**Hidden cost.** Effectively negative: removing the quota anxiety removes the incentive to
batch work into large uncommitted chunks.

**Verdict.** The correct baseline.

---

### D. Max (or Pro) + API billing for overflow

**This is the option not in your list, and it is the strongest.**

Interactive work runs on the subscription. When the subscription's window is exhausted,
overflow runs against API billing — Claude Code and the Agent SDK both support it — or against
purchasable usage credits on the same account.

**Advantages.**
- **Perfectly elastic.** Pay per token; no ceiling.
- **One identity.** No compliance question, no split history, no second credential set.
- **Cost-transparent.** Overflow spend is measurable per milestone. You learn what a milestone
  actually costs — which you will need when you hire.
- **Survives hiring.** Team members get their own seats; the overflow mechanism is unchanged.

**Disadvantages.** Two cost lines to watch. Requires a spend cap so a runaway loop cannot bill
you unboundedly. Slight setup.

**Failure mode.** Unbounded spend from a misbehaving agent loop. **Mitigation: hard budget
alert, non-negotiable.**

**Verdict.** **Recommended.**

---

### E. Claude + ChatGPT (already in use)

Product Architect / Chief Systems Engineer split.

**Advantages.** Genuine adversarial review. A second model reading the same specification
catches different classes of error. Different quotas, so partial natural overflow.

**Disadvantages.** Only works because the *repository* carries the context. Two models sharing
prose is a downgrade, not an upgrade.

**Verdict.** **Keep.** This is not an overflow strategy; it is a quality strategy that happens
to help with overflow.

---

### F. Claude + Gemini for architectural uncertainty (already in use)

**Advantages.** Independent judgement on high-impact, low-reversibility decisions.

**Disadvantages.** Adds a decision loop. Wasteful if invoked routinely.

**Verdict.** **Keep, gated.** Reserve for decisions rated High or Severe to reverse. Correctly
scoped in `00` §P.5; it was invoked zero times in M0 and M1, which is the right frequency.

---

### G. Local models (DeepSeek via Ollama, already available)

**Advantages.** Zero marginal cost, unlimited, private, no network. Good at mechanical
transforms — boilerplate, test scaffolds, format conversions, repetitive edits.

**Disadvantages.** Weaker at architecture and at subtle correctness. `00` §6.9 already
governs this: drafting tool, never authority; generated tests treated with extra suspicion.

**Verdict.** **Keep for mechanical work.** This is real overflow capacity that costs nothing.
It is under-used.

---

### H. Multi-agent orchestration in one session

Subagents for parallel exploration.

**Advantages.** Parallelises search-heavy work.

**Disadvantages.** Each subagent starts cold and re-derives context — the expensive path.
Consumes quota faster, not slower.

**Verdict.** Not an overflow strategy. Use only for genuinely parallel read-only exploration.

---

### I. Documentation-driven development (already in use)

**Verdict.** This is *why* account switching is even survivable. Keep and strengthen.

---

### J. Git-checkpoint workflow

**Verdict.** The load-bearing mechanism. **Currently the weakest link, because checkpoints are
milestone-sized.** See §6.

---

## 3. Comparison Matrix

Scored 1–5. Only the emphasised columns matter for a solo founder.

| Workflow | Continuity | **Review capacity** | **Compliance** | Cost | Complexity | **Scales to team** | Knowledge risk |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| A. Single Pro | 2 | 3 | 5 | 5 | 5 | 3 | 3 |
| **B. Two Pro accounts** | 4 | **3** | **1** | 4 | 3 | **1** | 2 |
| C. Max | 4 | 3 | 5 | 3 | 5 | 4 | 3 |
| **D. Max + API overflow** | **5** | **3** | **5** | 3 | 4 | **5** | 3 |
| E. + ChatGPT review | 4 | **5** | 5 | 4 | 3 | 4 | 4 |
| F. + Gemini (gated) | 3 | 4 | 5 | 4 | 3 | 4 | 4 |
| G. + local models | 4 | 3 | 5 | **5** | 3 | 4 | 3 |
| I. Documentation-driven | 5 | 4 | 5 | 5 | 3 | **5** | **5** |
| J. Task-level git checkpoints | **5** | 4 | 5 | 5 | 4 | **5** | **5** |

**Note the pattern.** The highest-scoring rows on the columns that matter — I, J, E — are
*process* choices costing nothing. The account question (A/B/C/D) barely moves the needle on
anything except continuity. **You have been optimising the least important variable.**

---

## 4. Recommended Workflow

**One identity. Elastic capacity. Task-level checkpoints. Generated bootstrap.**

| Layer | Choice |
| --- | --- |
| **Capacity** | Claude Max as baseline; **API billing or usage credits for overflow, same account, hard spend cap** |
| **Review** | ChatGPT as Product Architect and milestone reviewer (unchanged) |
| **Uncertainty** | Gemini, gated to High/Severe reversal cost (unchanged) |
| **Mechanical work** | Local DeepSeek under `00` §6.9 (unchanged, under-used) |
| **Continuity** | **Task-level commits** on a milestone branch |
| **Bootstrap** | **Generated brief** (`make brief`) — never hand-written |
| **Intent** | `NEXT_TASK.md` — small, tracked, one task |
| **Negative results** | `docs/_session/NOTES.md` — untracked, disposable, append-only |
| **Authority** | `make verify` — unchanged, non-negotiable |

**Two accounts are not part of this.** If you keep the second subscription, use it as a
personal account for non-DistriCore work — not as a capacity extension for this repository.

---

## 5. Documentation Strategy

### 5.1 The corpus, by lifetime

| Tier | Files | Lifetime | Changes |
| --- | --- | --- | --- |
| **Constitution** | `00` | Permanent | Amendment only (§P.4) |
| **Specification** | `01`–`05` | Frozen per edition | Amendment only |
| **Decisions** | `adr/` | Permanent, immutable | Superseded, never edited |
| **History** | `M*_Verification_Report.md`, `CHANGELOG.md` | Permanent | Append |
| **State** | `PROJECT_STATE.md` | Current | Every milestone |
| **Intent** | **`NEXT_TASK.md`** | Current | **Every task** |
| **Scratch** | **`docs/_session/NOTES.md`** | Session | **Untracked. Deleted at milestone close** |

The underscore prefix on `_session/` is deliberate: it is not part of the corpus and must
never be cited as authority.

### 5.2 Why the brief is generated, not written

A hand-written session file fails on all four properties that make documentation trustworthy.
A generated brief cannot drift, because it is derived from git and from files that already
have verification gates.

`make brief` should emit, on demand:

```
BRANCH        feat/m2-stock-ledger
LAST COMMITS  <git log --oneline -10>
WORKING TREE  <git status --short>          # dirty files = in-flight work
LAST VERIFY   <cat .verify-result>          # written by make verify
MILESTONE     <PROJECT_STATE.md current row>
NEXT TASK     <NEXT_TASK.md>
OPEN DEBT     <grep TD- from latest verification report>
DO NOT RETRY  <docs/_session/NOTES.md, if present>
```

Zero maintenance. Always accurate. **This replaces `SESSION_CONTEXT.md` entirely.**

### 5.3 `NEXT_TASK.md` — the only hand-written handoff artifact

```markdown
# Next Task

Milestone: M2 — Inventory & stock ledger
Task: 3 of 9 — stock_movement model and migration

## Definition of done
- [ ] Model with location_id, lot_id, signed quantity, CHECK (source OR reason)
- [ ] Migration passes ops/check_structural_columns.py
- [ ] Append-only trigger, mirroring core/0002
- [ ] Adversarial test: raw UPDATE and DELETE both rejected
- [ ] make verify green

## Constraints that apply
M2-1..M2-10 (irreversible), BR-004, BR-007, N-03, N-10

## Do not
- Do not add a cached balance table (EP-E, only if measured)
- Do not implement allocation (Edition 2)
```

Small enough to rewrite in two minutes. Specific enough that a cold session starts correctly.

### 5.4 `docs/_session/NOTES.md` — negative results only

**Untracked** (`.gitignore`). Append-only within a session. Deleted at milestone close.

```
- Tried enforcing non-negative stock with a partial index. Postgres cannot express a
  constraint over an aggregate. Do not retry — use a lock anchor or accept negatives.
- factory-boy post_generation with skip_postgeneration_save caused silent password loss.
```

This is the one thing genuinely lost when a session dies, and the only thing worth writing by
hand.

---

## 6. Git Strategy — the actual fix

### 6.1 The current weakness

Milestones are the commit unit. M1 was 5 tables, 3 modules, 8 endpoints and 92 tests in one
commit. A session ending mid-milestone leaves a working tree that no document describes, and
`git status` is the only record.

### 6.2 The change

**Decompose every milestone into 5–12 tasks, each independently committable and
independently verifiable.** M2, for example:

| # | Task | Verifiable alone |
| --- | --- | :-: |
| 1 | `stock_location` model + migration + seed | ✓ |
| 2 | `stock_lot` model + migration + lazy creation | ✓ |
| 3 | `stock_movement` model + migration + CHECK | ✓ |
| 4 | Append-only trigger + adversarial tests | ✓ |
| 5 | `inventory.services` receive/issue/adjust | ✓ |
| 6 | Derived on-hand selectors | ✓ |
| 7 | Concurrency adversarial suite | ✓ |
| 8 | API endpoints | ✓ |
| 9 | Admin screens + TD-12, TD-13 | ✓ |

Each ends with `make verify` and a commit. **A session can then die at any point and lose at
most one task.** Handoff becomes a non-event, which is the goal — not a better handoff
document.

### 6.3 Branch and commit rules

- One branch per milestone: `feat/m2-stock-ledger`.
- Commit after each task; `main` stays releasable (FD-08 unchanged).
- Push after **every** commit, not every milestone. The remote is the checkpoint; an
  unpushed commit protects against nothing.
- WIP commits allowed on the branch, squashed at merge. `wip:` prefix, never merged as-is.
- Tag at milestone close: `m2-inventory`.

### 6.4 The rule that makes all of it work

> **Never end a session with uncommitted work.** If a task is incomplete, commit it as
> `wip: <task> — <what remains>` and push. An unpushed working tree is the only state no
> document can reconstruct.

---

## 7. AI Session Lifecycle

```
  START      make brief            ->  paste output as the first message
             confirm NEXT_TASK.md  ->  correct it if the plan changed

  WORK       one task only
             make verify
             commit + push

  END        update NEXT_TASK.md to the next task
             append negative results to docs/_session/NOTES.md
             ensure the tree is clean
```

Three rules:

1. **A session never starts by explaining the project.** If it needs explaining, the
   repository has failed and the fix is in the repository.
2. **A session never ends with uncommitted work.**
3. **A session never spans more than one task.** Long sessions degrade: context fills,
   earlier constraints get crowded out. Ending a session at a task boundary is a feature.

---

## 8. Switching Procedure

If, despite the above, you switch AI instances mid-milestone:

1. `make verify` — if red, either fix or `wip:` commit with the failure stated in the message.
2. Commit and **push**.
3. Update `NEXT_TASK.md`.
4. Append negative results to `docs/_session/NOTES.md`.
5. In the new session: `make brief`, paste, work.

**Elapsed: under two minutes. No prose handoff. No `SESSION_CONTEXT.md`.**

---

## 9. What Should Be Automated

| Automate | Why |
| --- | --- |
| `make brief` | The only bootstrap; must not be hand-maintained |
| `make verify` writes `.verify-result` | So the brief reports real state, not remembered state |
| Pre-commit hooks | Already done |
| CI on every push | Already done |
| Spend alert on API overflow | **Missing. Add before enabling overflow** |
| Milestone → task decomposition | Not automatable. Human judgement |

## 10. What Must Never Depend on Chat History

Architecture · requirements · decisions and their reasoning · verification results ·
what is done · what is next · why an approach was rejected · what is technical debt.

**All of it is already in the repository except "why an approach was rejected", which is what
`docs/_session/NOTES.md` and ADRs are for.**

---

## 11. Common Mistakes in AI-Assisted Engineering

Observed generally, and where this project stands.

| Mistake | DistriCore |
| --- | --- |
| Treating output volume as progress | **At risk** — the two-account plan is exactly this |
| Letting the AI make architecture decisions mid-implementation | Avoided — ADR process |
| Skipping verification because the code reads correctly | Avoided — `verify_otp` proved why |
| Not recording negative results | **Gap** — `_session/NOTES.md` addresses it |
| Documentation describing intent rather than reality | Avoided — reports state what failed |
| One enormous session | **At risk** — enforce one task per session |
| Trusting AI-generated tests | Governed — `00` §6.9 AI-5 |
| Context stuffing instead of curation | **At risk** — `make brief` is curation |

---

## 12. Risks

| Risk | Severity | Mitigation |
| --- | :-: | --- |
| **Review capacity saturates; unreviewed code accumulates** | **High** | One task per session. `make verify` blocking. Never merge unreviewed |
| Unbounded API overflow spend | Medium | Hard budget alert before enabling |
| `NEXT_TASK.md` drifts from reality | Medium | Rewritten every task; too small to rot |
| Session ends with a dirty tree | Medium | Rule §6.4; `make brief` shows it immediately |
| ToS exposure from multi-account use | **High** | **Do not adopt.** Verify independently |
| Repository outgrows a single brief | Low | Brief is generated and bounded; it summarises, does not dump |

---

## 13. Future Scalability

**At hundreds of thousands of lines**, this workflow holds because nothing in it scales with
repository size:

- `make brief` is bounded — it summarises state, it does not dump the repository.
- Tasks stay small regardless of total size.
- `import-linter` contracts are what keep a large repository comprehensible; they already
  caught two violations by the engineer who wrote them.
- Verification stays mechanical.

**When you hire**, nothing changes structurally. `NEXT_TASK.md` becomes a ticket queue.
`make brief` becomes onboarding. Task-level commits become normal pull requests. Reviewer
capacity stops being one person — **which is the only thing that actually raises the
ceiling**.

**Two accounts survive none of this.** "Log into my other account" is not a process you can
hand to an employee, an auditor, or an acquirer.

---

## Decision

1. **Adopt one identity with elastic capacity.** Claude Max as baseline; API billing or usage
   credits for overflow on the same account, with a hard spend cap.
2. **Do not adopt multi-account switching.** Verify the terms question independently; do not
   build a permanent process on an unresolved compliance assumption.
3. **Decompose milestones into 5–12 independently verifiable tasks.** Commit and push after
   each.
4. **Replace `SESSION_CONTEXT.md` with `make brief` (generated) + `NEXT_TASK.md` (intent) +
   `docs/_session/NOTES.md` (negative results, untracked).**
5. **One task per session. Never end with uncommitted work.**
6. Keep ChatGPT as reviewer, Gemini gated, local models for mechanical work.

## Consequences

**Positive.** Handoff becomes a non-event. Capacity scales with a slider. Compliance risk
removed. Workflow survives hiring unchanged. Commit history becomes a genuine audit trail.

**Negative.** Higher monthly cost than two Pro subscriptions. Task decomposition is real
up-front work per milestone. Discipline required to end sessions at task boundaries.

**Harder.** Long uninterrupted sessions are discouraged — deliberately.

## Migration cost if reversed

*Low* — the process changes are additive and the repository already carries the corpus.

