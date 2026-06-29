# SteadyPlan roadmap — product direction and next phases

## Core direction

SteadyPlan should help ordinary people understand their financial position **calmly, privately, and without intimidation**.

That means the app should not mainly optimise for finance power-users or self-hosting enthusiasts. It should optimise for people who want to:

- understand where they stand
- stop avoiding the numbers
- connect day-to-day decisions to long-term goals
- make steadier choices
- feel more in control of money without becoming spreadsheet or investing obsessives

## Important strategic position

We are **not** rushing into a fully hosted product.

We are also **not** assuming self-hosting alone will be enough forever.

The likely long-term shape is:

- **self-hosted remains a real option**
- **hosted may come later as a convenience/accessibility layer**
- but only after the product is clearer, safer, easier to use, and supportable

So the immediate goal is **not** “launch SaaS”.
The immediate goal is to make SteadyPlan ready, in a careful and methodical way, for eventual **small private external use**.

## Current standing (June 2026)

The foundations are now much stronger than this roadmap originally assumed:

- product truth, calm positioning, and public trust language are now committed in-repo
- Overview, Monthly Update, Planning, and the main compact-screen flows have had substantial answer-first cleanup
- Diagnostics, backup/restore boundaries, assistant access, safe demo guidance, and public-site trust copy are now real shipped product surfaces
- an optional Trading 212 broker snapshot review beta exists for preview-first broker review without forcing users away from manual/CSV tracking

That means the next stretch is no longer “invent the direction from scratch”. The next stretch is to keep the shipped experience coherent, reduce density in the heaviest flows, and strengthen supportability and trust before any tiny hosted beta discussion.

---

## Phase 1 — clarify product truth (foundation landed; keep it current)

### Goal
Keep SteadyPlan’s purpose sharp and stop the product drifting sideways as new features and docs continue to land.

### Questions this phase answers
- Who is this app really for?
- What problem is it really solving?
- What should feel central vs secondary?
- What should wait?

### Product stance
SteadyPlan is for people like earlier-me:
- not financially hopeless
- but not fully confident
- possibly late to investing/planning
- wanting clarity more than hype
- wanting a system that feels honest and calm

### Core promise
SteadyPlan should help users:
- see where they stand
- understand Liquidity Profile
- connect monthly life with long-term plans
- build financial steadiness

### Core user jobs
The app should prioritise helping users:
1. understand their current position
2. see Liquidity Profile
3. track whether they are on course
4. connect short-term actions to long-term goals
5. stop avoiding the overall picture

### Deliverables
- product vision statement
- core user definition
- “what SteadyPlan is / is not” wording
- agreed list of top-priority user jobs
- list of things not to prioritise yet

---

## Phase 2 — improve usability for normal people (major foundation landed; continue simplification)

### Goal
Keep reducing friction, intimidation, and over-complexity, especially in the densest remaining setup and maintenance flows.

### Why this matters
At the moment, the people most likely to install a self-hosted finance app may not be the same people who most need SteadyPlan.

So before thinking about hosted/private beta, the product must become easier to understand and easier to start using.

### Priorities

#### 1. Onboarding
Make first use simpler and less overwhelming.

Needs:
- clearer first steps
- less wall-of-finance feeling
- “start with only a few important things”
- setup that feels guided rather than dense

#### 2. Information hierarchy
The app should answer key questions first, especially on compact screens.

Needs:
- what matters now at the top
- detail below
- less repeated information
- less visual density in key flows

#### 3. Language
Wording should feel:
- plain English
- calm
- direct
- not guru-ish
- not over-technical unless necessary

#### 4. Trust-building UX
SteadyPlan must feel safe and honest.

Needs:
- visible assumptions
- clear scenario-estimate caveats
- no exaggerated certainty
- no pressure language

### Deliverables
- onboarding review
- UX simplification plan
- wording cleanup plan
- phone-first hierarchy review for core screens

---

## Phase 3 — make mobile/PWA experience genuinely good (core pass landed; keep refining)

### Goal
Keep making SteadyPlan feel useful and comfortable on a phone, without rushing into native apps or pretending the job is finished.

### Important principle
Do **not** jump straight to iOS/Android native development.

First make SteadyPlan a genuinely good **mobile-first responsive web app / PWA**.

If the phone web experience is weak, wrapping it as an app will not solve the underlying problem.

### Mobile priorities
Phone users probably mainly need:
- overall dashboard / where do I stand
- monthly position
- Liquidity Profile
- key goals / progress
- important next actions
- possibly quick affordability/context views

They do **not** need full desktop complexity on every screen.

### Product rule
Mobile should focus on:
- answer-first experience
- simple summaries
- important signals
- reduced clutter
- clear next actions

Deeper admin/setup/detail flows can remain desktop-heavier if needed.

### Deliverables
- list of top 3–5 mobile-critical flows
- compact-screen UX improvements
- PWA experience review
- navigation and “what matters now” cleanup

---

## Phase 4 — improve public-facing trust and first impression (foundation landed; keep parity current)

### Goal
Keep it easy for someone outside the project to understand what SteadyPlan is, why it exists, and how to evaluate it safely.

### Why this matters
Before private external use, people need to trust the app and quickly understand:
- what it does
- who it is for
- why it exists
- why it might help them

### Priorities

#### 1. Founder-story / trust copy
Continue building the human, honest voice across the site.

#### 2. Clearer product explanation
The site should show:
- who SteadyPlan is for
- what problem it solves
- what it helps with
- what it does not claim to do

#### 3. Demo-friendly product presentation
People should be able to imagine using it without needing to self-host first.

#### 4. Screenshots / guided tour / walkthrough
The product should be easier to understand from the outside.

### Deliverables
- improved website messaging
- better “who it’s for” copy
- better tour/demo/screenshot plan
- consistent trust language across site and app

---

## Phase 5 — keep the safe evaluation path clear

### Goal
Keep SteadyPlan easy to evaluate without setup friction while preserving the safest trust path for real use.

The read-only demo path and sample data now exist, so the remaining work is to keep the evaluation story honest and easy to follow.

### Why this matters
The product will be hard to share if every new person needs to install/configure it before even understanding the value.

### Current safe path
- screenshots and tour first
- local install on LAN/VPN for hands-on evaluation
- optional host-controlled read-only demo using sample data
- real financial data only after the operator understands the local/self-hosted boundary

### Purpose
This is not about flashy marketing.
It is about helping people see:
- what the app feels like
- how it helps
- whether it matches their needs

### Deliverables
- keep README, public docs, and roadmap aligned on the safest evaluation order
- keep demo-data screenshots and sample-data language current
- make the read-only demo boundary obvious whenever demo access is mentioned
- avoid presenting public demo access as the default trust path for real use

---

## Phase 6 — prepare technical foundations for small private external use

### Goal
Make the app safe and supportable enough for a **tiny private hosted beta**, if and when we decide it is ready.

### Important caution
This phase is **not** public launch.
It is preparation for a small, low-blast-radius test.

### Technical areas to harden

#### 1. Deployment repeatability
Need confidence that installs/updates/backups are reliable.

#### 2. Backup and restore confidence
Data safety must feel trustworthy before external use.

#### 3. Authentication and account boundaries
If external users ever touch this, auth and ownership must be dependable.

#### 4. Supportability
Need basic confidence in:
- logs
- health visibility
- failure recovery
- update flow
- operational simplicity

#### 5. Product consistency
The app should avoid confusing differences between screens/calculations/wording.

### Deliverables
- deployment readiness checklist
- data-safety checklist
- auth/account boundary review
- supportability checklist
- private beta readiness criteria

---

## Phase 7 — tiny private hosted beta only if earned

### Goal
Test whether hosted convenience actually unlocks value for non-technical users.

### Rules
- invite-only
- very small number of users
- explicit beta expectations
- manual onboarding is acceptable
- low blast radius
- not a public launch
- not a polished SaaS promise

### Ideal testers
- trusted people
- patient users
- maybe a mix of technical and non-technical
- people willing to give real feedback

### What we want to learn
- where people get confused
- what they use most
- what they ignore
- what breaks trust
- whether hosted access solves a real accessibility problem
- whether the app genuinely helps ordinary users stay on top of money

### Success criteria
Private hosted beta only makes sense if:
- the product feels clear
- the mobile experience is decent
- setup/friction is reduced
- data safety feels trustworthy
- users actually find it useful, not just interesting

---

## Things we should **not** prioritise yet

For now, these are probably too early:

- native iOS app
- native Android app
- broad public SaaS launch
- detailed pricing strategy
- subscription mechanics
- growth/marketing optimisation
- advanced monetisation
- chasing every feature request before product clarity exists

---

## Near-term implementation priorities

### Recommended next sequence
1. define product vision more clearly
2. identify the top 3–5 user journeys that matter most
3. improve mobile-first experience for those journeys
4. simplify onboarding / first-use experience
5. improve trust copy and product explanation
6. keep the safe demo/sample walkthrough path clear
7. review what would be needed for eventual tiny private external use

---

## Product principle to guide decisions

When deciding what to build next, use this question:

> Does this help ordinary people understand their financial position more calmly, clearly, and confidently?

If yes, it is probably aligned.

If it mainly adds complexity, power-user depth, or architectural ambition without helping clarity/trust/usability, it should probably wait.

---

## Business / sustainability note

It is fine to think ahead about long-term sustainability, but pricing is not the immediate priority.

For now, the product should aim to become:
- useful
- trustworthy
- approachable
- supportable

If charging ever comes later, it should feel:
- fair
- simple
- aligned with trust
- not aggressively subscription-driven unless there is a very good reason

That decision can wait.

---

## Summary

SteadyPlan should move forward in a calm, methodical sequence:

- sharpen purpose
- simplify experience
- improve mobile usability
- build trust
- reduce setup friction
- create demo-friendly exploration
- prepare carefully for tiny private external use
- only then consider broader hosted convenience

This is not a race to become SaaS.

It is a process of making SteadyPlan good enough, clear enough, and trustworthy enough that eventually a small number of ordinary people could genuinely benefit from it.
