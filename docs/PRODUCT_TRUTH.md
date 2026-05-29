# SteadyPlan product truth

This document turns the roadmap into a short set of durable product rules.

Use it when deciding what to build, what to postpone, and how to describe SteadyPlan in the app, docs, and public site.

---

## Core direction

SteadyPlan should help ordinary people understand their financial position **calmly, privately, and without intimidation**.

It should not primarily optimise for:
- finance power-users chasing complexity for its own sake
- self-hosting hobbyists as the only audience
- SaaS growth mechanics before the product is clear and trustworthy

It should primarily help people who want to:
- understand where they stand
- stop avoiding the numbers
- connect day-to-day decisions to long-term goals
- make steadier decisions
- feel more in control without becoming spreadsheet obsessives

---

## Core user

SteadyPlan is for people like earlier-me:
- not financially hopeless
- but not fully confident
- possibly late to investing or long-term planning
- wanting clarity more than hype
- wanting a system that feels honest, calm, and practical

A good default mental model:

> Someone who wants a clear picture of their money and progress, but who may still feel intimidated by financial admin, projections, and long-term planning.

---

## Core promise

SteadyPlan should help users:
1. see where they stand
2. understand what is accessible now vs restricted or locked for later
3. connect monthly life with long-term plans
4. build financial steadiness without salesy pressure or false certainty

---

## Top-priority user jobs

These jobs should outrank lower-value feature work:

1. **Understand current position**
   - Net worth, key balances, and what needs attention should be obvious.
2. **See accessible vs locked money**
   - Users should understand what they can use now, what has penalties/restrictions, and what is for later retirement.
3. **Track whether they are on course**
   - Goals, retirement estimates, and monthly review state should feel understandable rather than overwhelming.
4. **Connect short-term actions to long-term goals**
   - Budget, contributions, and account actions should clearly feed into the bigger picture.
5. **Stop avoiding the overall picture**
   - First use, overview, and monthly review should reduce dread, not increase it.

---

## What SteadyPlan is

- A self-hosted personal finance planning and visibility tool
- A calm control panel for understanding money, progress, and trade-offs
- A product that values local control, clear assumptions, and honest wording
- A bridge between monthly decisions and long-term plans

## What SteadyPlan is not

- A broker
- A budgeting guru persona
- A financial adviser
- A promise engine for optimistic outcomes
- A race to become a generic hosted SaaS product

---

## Product principles

### 1. Answer first, machinery second
Especially on phone-sized screens, the app should show the answer before the plumbing.

### 2. Calm beats clever
A less flashy flow that users trust is better than a more impressive flow that confuses them.

### 3. Truth must be visible
Assumptions, estimates, projections, and confirmed numbers should not blur together.

### 4. Privacy and local control matter
SteadyPlan should continue to feel like a tool the user owns, not a platform that owns the user.

### 5. Hosted is a later accessibility layer, not the present mission
Current direction:
- self-hosted remains real
- hosted may come later
- only after usability, trust, supportability, and safety are stronger

### 6. Mobile-first web before native
Do not jump to iOS/Android native work as a shortcut. First make the responsive web app/PWA genuinely good on a phone.

---

## Decision filter

Before building a feature or rewriting a flow, ask:

> Does this help ordinary people understand their financial position more calmly, clearly, and confidently?

If not, it probably should wait.

---

## Near-term priorities

For the next meaningful stretch of development, priorities should be:

1. clarify product truth and user journeys
2. reduce intimidation and setup friction
3. improve compact-screen information hierarchy
4. strengthen trust copy and assumption clarity
5. make demo/evaluation easier without exposing real user data
6. harden backup, auth boundaries, and operational supportability before any private hosted beta

---

## Not now

These should not lead the roadmap yet:
- native iOS app
- native Android app
- broad hosted launch
- pricing and subscription mechanics
- growth optimisation
- broad feature expansion driven by edge-case requests rather than user clarity

---

## Current implementation implications

When working in this repo, the roadmap points first toward:
- improving Overview and first-use hierarchy
- tightening onboarding and first-run guidance
- making mobile/PWA flows answer-first
- keeping website/about/docs copy aligned with the calm, ordinary-person positioning
- preparing a safe demo path that does not depend on real user data

Likely first code/docs touchpoints:
- `app/templates/overview.html`
- `app/routes/overview.py`
- `site/index.html`
- `site/about.html`
- `site/tour.html`
- `README.md`
- `docs/VOICE_AND_COPY.md`

---

## Source

This document is derived from:
- `STEADYPLAN_ROADMAP_2026-05-29.md`
- existing product voice/copy guidance in `docs/VOICE_AND_COPY.md`
- current public positioning in `site/about.html`
