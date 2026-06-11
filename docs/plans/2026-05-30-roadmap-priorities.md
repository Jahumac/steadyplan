# SteadyPlan roadmap priorities — next implementation sequence

> **For Hermes / Trae:** Treat this as the practical continuation of `STEADYPLAN_ROADMAP_2026-05-29.md` and `docs/plans/2026-05-29-roadmap-execution.md`. Keep each slice narrow, user-visible, and reviewable.

**Goal:** Turn the roadmap into a realistic short-to-medium-term execution order so SteadyPlan becomes clearer, calmer, and easier to trust before any hosted-beta thinking.

**Current repo-grounded context:**
- Roadmap source exists: `STEADYPLAN_ROADMAP_2026-05-29.md`
- Product truth exists: `docs/PRODUCT_TRUTH.md`
- Broad execution plan exists: `docs/plans/2026-05-29-roadmap-execution.md`
- `main` is currently clean and already contains the public-site positioning pass (`feat: align public site with roadmap positioning`, commit `a77d9dd`)
- `main` also contains the initial Overview answer-first / onboarding simplification work:
  - `feat: make overview answer-first for established users` (`b154697`)
  - `feat: simplify overview onboarding next steps` (`ef4a4be`)
  - follow-up Overview wording/consistency refinements through PR #251
- So the roadmap should now treat public-site alignment and the first Overview hierarchy pass as landed foundations, not as the current in-progress bundle

---

## 1. What to do next

### Priority 1 — docs/site/roadmap parity

**Why first now:**
The product has moved faster than some of the repo and website wording. Before chasing more surface-level polish, keep the roadmap, README, docs, and public site aligned with what SteadyPlan already is.

**Target outcome:**
A reader should be able to understand:
- who SteadyPlan is for
- what has already landed
- what still needs work
- how to evaluate it safely
- why hosted-beta thinking is still gated behind trust and supportability

**Best first files to inspect:**
- `README.md`
- `STEADYPLAN_ROADMAP_2026-05-29.md`
- `docs/PRODUCT_TRUTH.md`
- `site/index.html`
- `site/tour.html`
- `site/roadmap.html`
- `site/docs/*.html`

**Definition of done:**
- Public and GitHub-facing docs match the current app truth
- Roadmap distinguishes landed foundations from remaining work
- Safe evaluation guidance is consistent across repo and site
- Trust surfaces are described literally rather than with stale shorthand

**Verification:**
- static-copy regression tests
- local preview of the updated site pages
- diff review across repo docs and site files

---

## 2. Best next product slice after the docs refresh

### Priority 2 — densest remaining settings/setup flows

**Why second now:**
Once parity is restored, the biggest remaining UX risk is not the already-improved core flows. It is the density in the heaviest settings, diagnostics, and admin-adjacent surfaces.

**Questions to settle:**
- Which settings/admin blocks still feel too dense for ordinary users?
- What can be made more literal without changing behaviour?
- Which trust surfaces still require users to mentally translate internal language?

**Definition of done:**
- The densest remaining surfaces read more calmly and literally
- Important trust boundaries stay explicit
- Small follow-up slices are obvious and narrow

---

## 3. Then continue trust hardening for tiny external use

### Priority 3 — operational trust hardening

This remains important, but it should follow clarity/usability/trust improvements rather than replace them.

**Focus areas:**
- backup and restore confidence
- auth/account boundaries
- deployment repeatability
- health visibility / supportability
- consistency between UI, docs, and assistant/API surfaces

**Rule:**
Do not frame this as public launch preparation. It is low-blast-radius readiness work only.

---

### Recommended implementation order

### Now
1. Refresh roadmap, repo docs, and public-site parity
2. Verify the safe demo/evaluation story across README, site, and docs

### Next
3. Review the densest remaining settings/setup/admin surfaces as one narrow sequence of small fixes
4. Keep tightening literal trust wording and everyday data-entry clarity

### Later
5. Harden backup/auth/supportability for possible tiny private external use
6. Consider invite-only hosted beta only if the earlier work genuinely earns it

---

## What should not interrupt this sequence

Do **not** let these jump the queue unless there is a bug or trust/safety issue:
- native mobile app work
- pricing or subscription planning
- broad hosted/SaaS architecture
- major power-user feature expansion
- cosmetic redesigns that are not tied to product clarity or trust

---

## Practical product filter

Before taking a roadmap slice, ask:

> Does this make SteadyPlan easier for an ordinary person to understand, trust, and use calmly?

If the answer is weak, the slice probably belongs later.

---

## Recommended immediate next handoff

If continuing implementation work now, the next handoff should be:

**Bundle A — docs / roadmap / website refresh**
- inspect README, roadmap source, site pages, and docs hub for parity drift
- update wording so current landed foundations are explicit
- keep safe evaluation guidance and hosted-later caution consistent

**Bundle B — settings/setup density review**
- inspect the heaviest remaining admin/trust surfaces
- identify the smallest user-visible wording or hierarchy fixes worth shipping next
- keep follow-up bundles narrow and evidence-led
