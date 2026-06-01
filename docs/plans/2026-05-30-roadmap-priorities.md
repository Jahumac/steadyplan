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

### Priority 1 — mobile/PWA critical-flow pass

**Why first now:**
The public front door is already aligned and the first Overview/onboarding pass has landed. The next roadmap value comes from checking whether the app actually feels calm and clear on phone-sized screens across the flows ordinary people will use most.

**Target outcome:**
A phone user should be able to open SteadyPlan and quickly understand:
- where they stand
- what needs attention this month
- what they should do next
- how goals and monthly progress connect to the bigger picture

**Best first screens to inspect:**
- `app/templates/overview.html`
- `app/templates/monthly_review*.html`
- `app/templates/budget*.html`
- `app/templates/goals.html`
- related shared layout/styles used by those screens

**Definition of done:**
- Primary answers appear before dense detail on compact screens
- Important CTAs stay visible without scrolling through admin-heavy blocks
- Repeated headline numbers are reduced
- Cards feel intentionally ordered rather than just vertically stacked desktop sections
- Bottom navigation / safe-area spacing does not obscure meaningful content

**Verification:**
- browser/manual check of Overview, Monthly Review, Budget, and Goals at phone width
- regression tests for any hierarchy/CTA/order changes
- quick visual sanity pass for spacing and repeated metrics

---

## 2. Best next documentation/product slice after the mobile pass

### Priority 2 — safe demo/evaluation path

**Why second now:**
Once the app is calmer on the core phone flows, the next roadmap question is how an outsider can evaluate it safely without real personal data.

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

## Recommended implementation order

### Now
1. Review top mobile/PWA flows as one narrow sequence of small fixes
2. Start with Overview, Monthly Review, Budget, and Goals at phone width

### Next
3. Define and document the safe demo/evaluation path
4. Tighten any missing website/docs guidance that the demo decision exposes

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

**Bundle A — mobile/PWA critical-flow audit**
- inspect Overview, Monthly Review, Budget, and Goals at phone width
- identify repeated or low-signal top-of-page content
- check CTA visibility and spacing with bottom navigation/safe areas
- record the smallest user-visible fixes worth shipping first

**Bundle B — safe demo/evaluation definition**
- inspect the current `/demo` path and any sample-data helpers
- document whether the current evaluation story is good enough
- note the smallest follow-up slice needed to make demo evaluation obvious and safe
