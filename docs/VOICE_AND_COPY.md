## SteadyPlan Voice & Copy Guide

This document defines the product voice, copy rules, and personality boundaries for SteadyPlan.
It exists so future UI/copy work stays consistent, trustworthy, and UK-finance-aware.

This is a guide for wording and tone only:
- It does not describe features or product direction changes.

---

## 1. Product Voice Summary

SteadyPlan should read like a calm, factual, UK-aware personal finance control panel.

Primary feeling:
- You’re in control; nothing is hidden; nothing is irreversible without confirmation.

Personality:
- A light “slow and steady” warmth is allowed, but it is seasoning, not narrator.

---

## 2. Product Identity Notes

Product name:
- SteadyPlan (formerly Shelly Finance)

Primary domain:
- steadyplan.co.uk

Tagline candidates:
- Your plan. Your data. Your pace.
- Track progress, not promises.
- Self-hosted clarity for ISAs and pensions.
- Slow and steady, on your own server.

Notes:
- Avoid names and taglines that imply regulated advice, broker services, or performance promises.

---

## 3. Copy Principles

### Write in plain English
- Short sentences.
- Prefer everyday wording over jargon unless the UK finance term is the clearest option.

### Use UK terms when they reduce ambiguity
- ISA, Lifetime ISA (LISA), SIPP, Workplace Pension, Premium Bonds, tax year.
- Use “tax year” rather than “fiscal year”.

### Be explicit about certainty
Always distinguish:
- Recorded: entered/saved as a value (may still be provisional)
- Confirmed: explicitly confirmed by the user during Monthly Review
- Estimated: inferred from defaults/assumptions (not user-confirmed)
- Scenario estimate: calculated outcome based on assumptions

### Prefer clarity over cheerleading
- Neutral, precise phrasing.
- No “you’re smashing it” or celebratory money language.

### Avoid advice/trading language
- This is a tracking dashboard and scenario tool, not an adviser or broker.
- Avoid “should”, “recommended”, “best”, “beat the market”, “optimize”.

### No cutesy language around serious actions
When copy relates to money safety, data safety, or risk (e.g., restore/reset, tax, warnings):
- Keep it professional.
- Keep it reversible when possible.
- Use explicit confirmation prompts for destructive actions.

---

## 4. Rules by Area

### Overview
Goal:
- Fast clarity: “where am I?” and “what needs attention?”

Rules:
- Separate facts from estimates in labels.
- Warnings should be compact: one sentence + one action.
- Avoid “healthy status” banners on Overview; show only when action is needed.

### Monthly Review
Goal:
- Turn the month into “truth” the user can trust.

Rules:
- Use procedural language: “confirm”, “record”, “skip”, “complete”.
- State what completion changes: completed reviews become the source of truth.
- Avoid guilt. Make it feel like maintenance, not judgement.

### Scenario estimates
Goal:
- Explain scenarios, not promises.

Rules:
- Always use “scenario estimate”, “projection”, “based on assumptions”.
- Label assumptions drivers clearly (fees, growth rate, contributions, retirement timing).
- Avoid any language that implies certainty (“you will have”, “guaranteed”).

### Goals
Goal:
- Targets and progress without implying inevitability.

Rules:
- Goals are “targets” and “progress”, not commitments or guarantees.
- ETA language must remain approximate (“approximate”, “based on assumptions”).

### Allowances
Goal:
- Calm tracking of UK tax-year limits.

Rules:
- Use “used”, “remaining”, “projected”.
- Escalate only when nearing/exceeding thresholds, and provide a single action.

### Performance
Goal:
- Transparent performance measurement based on recorded cash flows.

Rules:
- Focus on method transparency: “based on recorded contributions”.
- Avoid competitive language (“winning”, “beating”, “crushing”).

### Settings / Diagnostics
Goal:
- Configuration and system visibility with zero drama.

Rules:
- Use factual labels and status indicators.
- Avoid mascot language and jokes.

### Backup / Restore
Goal:
- Maximum trust, maximum clarity.

Rules:
- Use explicit, serious wording: “Export”, “Validate backup”, “Restore (overwrites data)”.
- Confirmation steps must clearly state scope and impact (which user/data is replaced).
- Never soften destructive actions with humour.

### Empty States
Goal:
- Provide a clear next step with light warmth.

Rules:
- A small “slow and steady” line is acceptable.
- Always include a single clear CTA.

### Warning / Error States
Goal:
- Explain and unblock quickly.

Rules:
- Structure: what happened → impact → what you can do next.
- Avoid blame (“you did…”) and avoid jokes.

---

## 5. Turtle / Personality Rules

Allowed (helps):
- Onboarding/setup
- Empty states
- Success states (saved, exported, completed)
- Icon/branding

Not allowed (hurts trust):
- Totals and headline money figures
- Losses, drawdowns, underperformance
- Tax and allowances breach warnings
- Restore/delete/reset flows
- Diagnostics and system health
- Scenario estimate certainty and disclaimers

General rule:
- If a user might feel anxious, uncertain, or risk-exposed, do not use mascot language.

---

## 6. Preferred / Avoid Phrase List

### Preferred
- dashboard
- self-hosted
- stored locally
- privacy-first
- recorded / confirmed / estimated / projected
- scenario estimate
- needs attention
- review / check / confirm
- export / validate / restore

### Avoid
- guaranteed
- you will / you’ll have (for scenario estimates)
- best / recommended / optimize (advice-coded)
- beat the market / alpha / outperform (trading-coded)
- grow your wealth fast (salesy)
- oops / yay / cute exclamations around money safety or destructive actions

### Terms that must remain precise
- ISA allowance, Lifetime ISA (LISA), SIPP, Workplace Pension
- tax year
- annual allowance / MPAA (where applicable)
- estimate vs actual vs recorded vs confirmed
- restore overwrites data (do not euphemise)

---

## 7. Example Before/After Rewrites

### PWA/offline
- Before: “Works offline as a PWA”
- After: “Installable as a PWA” / “Installable as an app (PWA). For privacy, financial pages aren’t stored for offline viewing.”

### Scenario estimate certainty
- Before: “Projected at retirement”
- After: “Projected at retirement (estimate)” / “Scenario estimate at retirement”

### Warnings
- Before: “Looks good!” (on a dashboard surface)
- After: Render nothing when healthy; show only actionable warnings (with a single CTA).

### Destructive actions
- Before: “Reset my account” (without scope)
- After: “Reset data for this user (irreversible)” + explicit confirmation prompt.

---

## 8. Wording Audit Plan

Audit order (highest trust risk first):
1. Backup/Restore and Danger Zone wording
2. Scenario estimate labels and estimate disclaimers
3. Diagnostics, offline, and privacy wording consistency
4. Overview CTAs and alert phrasing
5. Empty states and onboarding warmth

Method:
- Inventory strings by surface (Overview/Review/Scenario estimates/etc.).
- Tag each string as factual, estimate, warning, or action.
- Apply the strictest rules to warnings, restores, and anything that could be read as advice.
