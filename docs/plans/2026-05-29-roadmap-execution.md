# SteadyPlan roadmap execution plan

> **For Hermes:** Use `writing-plans` for follow-on slices and keep each implementation bundle narrow, reviewable, and testable.

**Goal:** Turn the product roadmap into a practical sequence of small implementation slices that keep SteadyPlan coherent as the product truth, first-use cleanup, mobile improvements, and trust surfaces mature.

**Architecture:** Treat the roadmap as three linked workstreams rather than one giant rewrite: (1) product truth and public positioning, (2) core in-app usability/mobile improvements, and (3) trust/operational hardening. Keep the app self-hosted-first, and prefer improving the existing Flask app, templates, static site, and docs instead of inventing parallel systems.

**Tech Stack:** Flask, Jinja templates, SQLite, static HTML/CSS site in `site/`, pytest

---

## Current standing

A large part of the original roadmap foundation is now live:

- product truth and public positioning docs exist
- Overview and first-use hierarchy already had substantial answer-first work
- Monthly Update, Planning, and many mobile-critical flows already reflect the calmer product direction
- trust surfaces such as Diagnostics, backup/restore boundaries, assistant access, and safe demo guidance are now shipped

So the next execution phase is less about inventing direction and more about keeping the docs, site, and product surfaces in sync while tightening the densest remaining flows.

---

## Source of truth

- Strategic roadmap: `STEADYPLAN_ROADMAP_2026-05-29.md`
- Product truth summary: `docs/PRODUCT_TRUTH.md`
- Tone/copy rules: `docs/VOICE_AND_COPY.md`
- Public positioning today: `site/about.html`, `site/index.html`, `site/tour.html`
- Core user-facing app hierarchy today: `app/routes/overview.py`, `app/templates/overview.html`

---

## Workstream A — product truth and direction guardrails

### Objective
Make sure future implementation work is judged against a stable definition of who SteadyPlan is for and what the product is trying to help with.

### Deliverables
- committed roadmap source file
- durable product truth doc
- short roadmap execution plan
- README/site copy alignment checklist

### Status
Landed foundation. Keep these files current whenever shipped product truth moves.

### Task A1: Commit roadmap source and product truth docs

**Files:**
- Add: `STEADYPLAN_ROADMAP_2026-05-29.md`
- Add: `docs/PRODUCT_TRUTH.md`
- Add: `docs/plans/2026-05-29-roadmap-execution.md`

**Acceptance criteria:**
- The repo contains the roadmap you pasted.
- There is a concise product-truth document other work can cite.
- There is a sequenced implementation plan for the next phases.

**Verification:**
- `git diff -- STEADYPLAN_ROADMAP_2026-05-29.md docs/PRODUCT_TRUTH.md docs/plans/2026-05-29-roadmap-execution.md`

### Task A2: Keep core product copy aligned with the roadmap

**Files to inspect/update:**
- `README.md`
- `site/index.html`
- `site/about.html`
- `site/tour.html`
- `docs/VOICE_AND_COPY.md`

**Objective:**
Ensure the public-facing story consistently says SteadyPlan is for ordinary people who want calm clarity, not finance-optimiser hype.

**Acceptance criteria:**
- “Self-hosted now, hosted later only if earned” is reflected where needed.
- Copy emphasises clarity, privacy, local control, and ordinary-person usability.
- Demo/tour language does not imply regulated advice or polished SaaS promises.

---

## Workstream B — core usability and compact-screen hierarchy

### Objective
Keep reducing friction and intimidation in the actual product, especially in the densest first-use, settings, and phone-sized flows that still feel heavier than the core product truth.

### Recommended implementation order
1. Overview hierarchy and next-action clarity
2. Onboarding simplification / first-run guidance
3. Mobile-critical flow cleanup
4. Wording cleanup in the app

### Task B1: Overview answer-first audit and correction plan

**Files:**
- Inspect: `app/routes/overview.py`
- Inspect/Modify: `app/templates/overview.html`
- Inspect: supporting styles/macros referenced by Overview templates
- Test: overview-related pytest files plus any snapshot/regression coverage already present

**Objective:**
Make Overview answer the most important user questions first, especially on smaller screens:
- where do I stand?
- what needs attention?
- what should I do next?
- what is cash-accessible, invested-accessible, restricted, or locked for later?

**Required outcomes:**
- Reduce repeated or secondary information near the top of Overview.
- Keep a visible next action when useful.
- Introduce or improve an accessible-vs-locked summary if the current overview does not surface it clearly enough.
- Preserve trust language: clearly mark estimates, assumptions, and review state.

**Acceptance criteria:**
- A user landing on Overview can see one top summary, one main next action, and one clear money-access framing without scanning a long dense page.
- Compact-screen layout feels intentional rather than “desktop stacked vertically”.

**Likely follow-on tests:**
- route rendering assertions for next-action / monthly-review / accessible-vs-locked summary blocks
- regression coverage for stale or duplicate status summaries

### Task B2: First-use onboarding simplification

**Files:**
- Inspect/Modify: `app/templates/overview.html`
- Inspect: any setup, settings, account-create, and goal-create templates/routes linked from onboarding
- Inspect: login or setup templates if first-run entry points need copy cleanup

**Objective:**
Make first use feel guided rather than like a wall of finance.

**Required outcomes:**
- Keep only the few most important steps visible.
- Use plain-English labels.
- Make the difference between “essential to start” and “deeper admin/config” clearer.

**Acceptance criteria:**
- A new user can understand the first three or four actions without reading lots of explanation.
- Onboarding copy sounds calm and direct.

### Task B3: Mobile-critical flows pass

**Priority flows:**
1. Overview / where do I stand
2. Monthly position / budget
3. Cash-accessible, invested-accessible, restricted, and locked-for-later money
4. Goals / progress
5. Important next action or monthly review prompt

**Files likely involved:**
- `app/templates/overview.html`
- `app/templates/...` for budget/goals/monthly review related screens
- related CSS/static files already used by the app

**Objective:**
Review and tighten the top 3–5 phone-critical flows before any native-app discussion.

**Acceptance criteria:**
- Dense cards are reduced or collapsed where appropriate.
- Primary actions remain visible.
- Bottom navigation and spacing do not obscure key content.
- Repeated metrics near the top of pages are reduced.

---

## Workstream C — public trust and demoability

### Objective
Make the product easier to understand from outside the app, then make it easier to evaluate safely.

### Task C1: Website trust/copy parity maintenance

**Files:**
- `site/index.html`
- `site/about.html`
- `site/tour.html`
- `site/docs/index.html`
- `site/docs/privacy.html`
- `site/docs/backups.html`

**Objective:**
Help an outsider quickly understand:
- what SteadyPlan does
- who it is for
- why it exists
- what it does not claim to do

**Acceptance criteria:**
- Messaging matches `docs/PRODUCT_TRUTH.md`.
- Trust/data-safety statements are easy to find.
- Demo/tour pages help people imagine using the product without installing first.

### Task C2: Demo path review

**Files to inspect:**
- `README.md`
- demo seed scripts and demo-related routes/config if present
- public tour/site pages describing demo access

**Objective:**
Define the safest and clearest first-use evaluation path.

**Required outcomes:**
- Decide whether the current sample/demo mode is enough or needs a dedicated walkthrough polish pass.
- Confirm that demo flows do not depend on Janusz’s real production data.

---

## Workstream D — trust and private-beta foundations

### Objective
Prepare for tiny private external use only after the product is clearer and easier to trust.

### Task D1: Backup and restore confidence review

**Files:**
- `README.md`
- `DEPLOY.md`
- backup/restore routes, templates, and tests
- site backup/privacy docs

**Objective:**
Make data safety legible and repeatable.

**Acceptance criteria:**
- Backup routine is documented clearly.
- Restore impact is explicit.
- Validation/dry-run restore flows remain prominent.

### Task D2: Auth/account-boundary and supportability review

**Files likely involved:**
- auth/user models and settings/admin routes
- assistant access/API safety code
- deployment docs and diagnostics surfaces

**Objective:**
Only once usability/trust groundwork is in place, harden for possible tiny private hosted testing.

**Acceptance criteria:**
- account ownership boundaries are understandable and testable
- logs/health/update flow are reviewable
- no public-beta framing creeps in prematurely

---

## Recommended immediate sequence

### Slice 1 — done now in docs
- commit roadmap source
- commit product truth doc
- commit roadmap execution plan

### Slice 2 — recommended next coding slice
**Overview answer-first + compact-screen hierarchy pass**

Reason:
- it directly serves the roadmap’s top user jobs
- it improves both existing users and future demo/public understanding
- it is smaller and safer than attempting hosted/demo architecture changes first
- it gives a strong foundation for later onboarding and trust-copy cleanup

### Slice 3
**Onboarding simplification pass** tied to the revised Overview hierarchy

### Slice 4
**Website/index/tour trust-copy alignment** so the public story matches the in-app truth

---

## Guardrails

Do not do these as the next move:
- jump into native app work
- start pricing/subscription mechanics
- broaden hosted/SaaS architecture first
- do a sweeping redesign across every page at once
- add complex power-user features that do not improve clarity or trust

---

## Validation commands

For docs-only slices:
- `git diff --stat`
- `git diff`

For the next app slice (Overview/mobile hierarchy):
- targeted `pytest` for overview-related tests
- full `pytest` run when the slice is complete
- manual phone-width browser check of Overview and linked next-action flows

---

## Report-back format for future slices

When implementing the next bundle, report back with:
- summary of changes
- exact files changed
- tests added/updated
- exact test results
- assumptions made
- unresolved UX/product questions
