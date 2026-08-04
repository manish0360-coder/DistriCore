# 0001 — Record architecture decisions

Status: Accepted
Date: 2026-08-04
Deciders: Product Architect, Chief Systems Engineer

## Context

`00_Engineering_Foundation.md` §P.4 requires that any amendment to the constitution, and any
architectural decision taken during implementation, is recorded before code changes. Without a
durable record, the *reasoning* behind a decision is lost within weeks and the decision is
re-litigated — or worse, silently reversed by someone who never knew it was deliberate.

## Options

1. **ADRs in the repository** — versioned with the code, reviewed in the same pull request.
2. Decisions in issue comments — searchable, but not versioned and easily buried.
3. No formal record — the default, and the reason most codebases cannot explain themselves.

## Decision

Numbered Markdown ADRs in `docs/adr/`, using the template in `00` §4.4. An accepted ADR is
immutable; it is superseded by a new ADR, never edited.

## Consequences

Positive: reasoning survives personnel and time; review has a place to argue before code exists.
Negative: a small overhead per decision, which is the intended friction.

## Migration cost if reversed

Trivial — but the record already written cannot be recovered if abandoned.
