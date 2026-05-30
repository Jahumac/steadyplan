# SteadyPlan roadmap priorities — next implementation sequence

> **For Hermes / Trae:** Treat this as the practical continuation of `STEADYPLAN_ROADMAP_2026-05-29.md` and `docs/plans/2026-05-29-roadmap-execution.md`. Keep each slice narrow, user-visible, and reviewable.

**Goal:** Turn the roadmap into a realistic short-to-medium-term execution order so SteadyPlan becomes clearer, calmer, and easier to trust before any hosted-beta thinking.

**Current repo-grounded context:**
- Roadmap source exists: `STEADYPLAN_ROADMAP_2026-05-29.md`
- Product truth exists: `docs/PRODUCT_TRUTH.md`
- Broad execution plan exists: `docs/plans/2026-05-29-roadmap-execution.md`
- Public-site alignment work is already in progress in the working tree:
  - `site/index.html`
  - `site/about.html`
  - `site/tour.html`
  - `site/assets/site.css`

---

## 1. What to finish first

### Priority 1 — finish the public front-door alignment already in progress

**Why first:**
The repo already has uncommitted work on the public site. Finish and validate that before starting a new broad app pass, so the roadmap gains a coherent outward-facing story instead of leaving half-finished positioning work in the tree.

**Target outcome:**
A cautious visitor should quickly understand:
- what SteadyPlan is
- who it is for
- why it exists
- what it does not claim to be
- where to go next for docs / trust / installation / tour

**Files already in play:**
- `site/index.html`
- `site/about.html`
- `site/tour.html`
- `site/assets/site.css`

**Definition of done:**
- Home, About, and Tour read as one coherent story
- Tone matches `docs/PRODUCT_TRUTH.md` and `docs/VOICE_AND_COPY.md`
- Copy is calm, practical, and non-SaaS
- Trust boundaries are visible: self-hosted, local control, not financial advice, assumptions are illustrative
- Layout feels intentional on desktop and phone widths
- Docs/install/trust links are easy to find

**Verification:**
- browser/manual check of Home, About, Tour
- console check for broken assets/errors
- quick phone-width inspection

---

## 2. Best next in-app slice after the site work

### Priority 2 — Overview answer-first pass

**Why second:**
If the public site promises clarity for ordinary people, the in-app landing experience has to prove it immediately.

**Core product question:**
When someone opens SteadyPlan, do they instantly understand:
- where they stand?
- what needs attention?
- what to do next?
- what money is actually accessible now vs later?

**Primary touchpoints:**
- `app/routes/overview.py`
- `app/templates/overview.html`
- any supporting macros/styles used by Overview

**Definition of done:**
- One top summary comes before dense detail
- One main next action is visible when helpful
- Accessible vs locked framing is obvious
- Repeated or lower-value information near the top is reduced
- Compact-screen layout feels designed, not just stacked desktop cards
- Estimates / projections / confirmed truth stay clearly labelled

**Suggested acceptance tests:**
- rendering assertions for primary summary blocks
- rendering assertions for next-action visibility
- regression coverage for duplicate or stale status summaries

---

## 3. Then reduce first-use intimidation

### Priority 3 — onboarding / first-run simplification

**Why third:**
Overview hierarchy and onboarding are tightly linked. Once Overview is clearer, the first-use journey should stop feeling like a wall of finance.

**Primary aim:**
Reduce dread and cognitive load for somebody who is not a finance hobbyist.

**Likely touchpoints:**
- `app/templates/overview.html`
- setup-linked templates/routes
- account-create and goal-create entry flows
- first-run or login-adjacent guidance if present

**Definition of done:**
- Essential first steps are obvious
- “Do this now” is separated from “do this later”
- There is one clear primary CTA for the next incomplete essential step
- Language is plain, calm, and not admin-heavy

---

## 4. Then tighten compact-screen product truth

### Priority 4 — mobile/PWA critical-flow pass

**Why fourth:**
SteadyPlan should earn mobile confidence through the web app before any native-app discussion.

**Top flows to review in order:**
1. Overview
2. Monthly Review
3. Budget / monthly position
4. Accessible vs locked / planning signal
5. Goals progress / next-action prompts

**Definition of done:**
- Important answers appear before machinery
- Primary actions stay visible
- Secondary detail is collapsed or demoted where appropriate
- Bottom navigation/safe-area spacing never obscures key content
- Screens do not repeat the same headline numbers unnecessarily

---

## 5. Then improve trust through safer evaluation

### Priority 5 — demo/evaluation path

**Why fifth:**
Before asking outsiders to install or trust the app, the product should be easier to evaluate without real personal data.

**Questions to settle:**
- Is the current demo seed flow enough?
- Does the `/demo` path explain itself clearly enough?
- Is there a better guided evaluation path using sample data and screenshots?

**Definition of done:**
- Demo story is clearly documented
- Demo path does not depend on Janusz’s real production data
- Website/docs explain how to explore safely
- Demo mode feels like evaluation, not a hidden technical trick

---

## 6. Only then spend effort on hosted-beta foundations

### Priority 6 — operational trust hardening

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

## Recommended implementation order

### Now
1. Finish and validate public-site alignment work already in progress
2. Commit that as the completed “public front door” slice

### Next
3. Do an Overview answer-first pass
4. Follow with onboarding simplification tied to Overview

### After that
5. Review top mobile/PWA flows as one narrow sequence of small fixes
6. Define and document the safe demo/evaluation path

### Later
7. Harden backup/auth/supportability for possible tiny private external use
8. Consider invite-only hosted beta only if the earlier work genuinely earns it

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

If continuing implementation work after the current site changes, the next handoff should be:

**Bundle A — finish and verify the public front door**
- complete current edits in `site/`
- verify desktop + mobile layout
- check docs/trust links
- tighten any remaining copy drift against `docs/PRODUCT_TRUTH.md`

**Bundle B — Overview answer-first audit**
- inspect current Overview hierarchy
- identify repeated or low-signal top-of-page content
- promote next action + accessible-vs-locked clarity
- add narrow regression coverage before broader onboarding work
