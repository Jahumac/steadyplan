# SteadyPlan Static Website

This folder contains the source for the SteadyPlan static website hub (landing + lightweight docs). It is intentionally plain HTML/CSS with no build system.

## Purpose

- Provide a calm, privacy-first landing page for SteadyPlan
- Host the main human-readable docs hub (install, backups, privacy, reverse proxy)
- Act as the source directory for a future static host deployment (Cloudflare Pages, GitHub Pages, etc.)

## Local Preview

- Open `site/index.html` directly in your browser
- Or run a local static server:

```bash
python3 -m http.server 8000 --directory site
```

Then visit `http://localhost:8000/`.

## Cloudflare Pages (Intended)

Recommended project settings:

- Root directory: repository root
- Build command: none
- Build output directory: `site`

Custom domains:

- Primary: `steadyplan.co.uk`
- Optional alias/redirect: `www.steadyplan.co.uk`
- Secondary domain to redirect to canonical: `steady-plan.co.uk`

DNS and domain redirects are configured in Cloudflare (dashboard), not in this repository.

## Redirects and Headers

Cloudflare Pages supports Netlify-style files:

- `site/_redirects`:
  - Contains safe path-level redirects (e.g. `/docs` → `/docs/`)
  - Domain-level redirects (e.g. `steady-plan.co.uk` → `steadyplan.co.uk`) should be configured with Cloudflare redirect rules / bulk redirects
- `site/_headers`:
  - Contains basic security headers appropriate for a static docs site
