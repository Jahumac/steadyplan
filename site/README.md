# SteadyPlan Static Website

This folder contains the source for the SteadyPlan static website hub (landing + lightweight docs). It is intentionally plain HTML/CSS with no build system.

## Purpose

- Provide a calm, privacy-first landing page for SteadyPlan
- Host the main human-readable docs hub (install, backups, privacy, reverse proxy)
- Act as the source directory for the live Cloudflare Pages deployment and any local preview/testing

Current public pages:

- `index.html` — landing page
- `tour.html` — product tour
- `roadmap.html` — public roadmap
- `docs/` — lightweight docs hub
- `about.html` — product story / positioning

## Local Preview

- Open `site/index.html` directly in your browser
- Or run a local static server:

```bash
python3 -m http.server 8000 --directory site
```

Then visit `http://localhost:8000/`.

## Cloudflare Pages

Current project settings:

- Root directory: repository root
- Build command: none
- Build output directory: `site`

Custom domains:

- Primary: `steadyplan.co.uk`
- Optional alias/redirect: `www.steadyplan.co.uk`
- Secondary domain to redirect to canonical: `steady-plan.co.uk`

DNS, redirects, and custom domains are configured in Cloudflare (dashboard), not in this repository.

## Theme support

- The public site is static HTML/CSS/JS with a manual light/dark toggle.
- Theme preference is stored client-side in `localStorage` (`steadyplan-site-theme`).

## Redirects and Headers

Cloudflare Pages supports Netlify-style files:

- `site/_redirects`:
  - Contains safe path-level redirects (e.g. `/docs` → `/docs/`)
  - Domain-level redirects (e.g. `steady-plan.co.uk` → `steadyplan.co.uk`) should be configured with Cloudflare redirect rules / bulk redirects
- `site/_headers`:
  - Contains basic security headers appropriate for a static docs site
