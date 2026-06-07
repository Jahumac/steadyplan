# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Public roadmap page and a manual light/dark toggle on the public website.
- Scoped assistant access in Settings with UI-managed tokens, permission labels, and recent write activity.

### Changed
- Refreshed GitHub-facing docs so README/API/site notes match the current Monthly Update, Diagnostics, assistant access, and public-site experience.
- Refreshed public demo screenshots and the public marketing/docs site presentation.

### Fixed
- Test-account reset now clears dependent user-owned rows safely instead of failing on SQLite foreign-key constraints.
- Public dark-mode logo rendering no longer uses the semi-transparent showcase mark that caused pale edge haloing.

## [2026.5.0] - 2026-05-25

### Added
- Backup health tracking and display in Settings.
- Deployment notes for the SteadyPlan Docker/Unraid setup.

### Changed
- Continued mobile polish across the private app experience.
- Updated runtime dependencies to current releases, including Flask 3.1.3, Flask-WTF 1.3.0, yfinance 1.4.0, Gunicorn 26.0.0, APScheduler 3.11.2, pytz 2026.2, Flask-Limiter 4.1.1, and openpyxl 3.1.5.
- Updated the Docker base image to Python 3.14 slim.
- Updated GitHub Actions workflow dependencies for checkout, GHCR login, metadata, and Docker build/push.

### Verified
- Full test suite passes on Python 3.13 and Python 3.14.
- GitHub Docker build/publish and Cloudflare Pages checks pass.
- Production container update was smoke-tested on Unraid.

## [2.0.0] - 2026-05-24

### Added
- SteadyPlan public website, install docs, and demo-data screenshots.
- New primary Docker image: `ghcr.io/jahumac/steadyplan`.
- User JSON export in Settings and a hardened JSON restore flow (validate preview + explicit confirmation, transactional, current-user scoped).
- Overview Data Health panel (read-only) for stale/missing inputs.
- Monthly Update workflow (lightweight check-in with notes, contribution confirm/skip, and month completion snapshot).
- Manual account balance update workflow for regular use/monthly update.

### Changed
- Rebranded the project from Shelly Finance to SteadyPlan across the public app, documentation, Docker image, Unraid template, and repository metadata.
- Renamed the GitHub repository to `Jahumac/steadyplan` and updated local quick-start instructions.
- Updated screenshot tooling to prefer `STEADYPLAN_*` environment variables while retaining legacy `SHELLY_*` aliases.
- Clarified the distinction between per-user JSON exports and whole-instance SQLite/appdata backups.
- Scenario estimate copy replaces leftover projections wording.
- Monthly Review contribution copy uses “Confirmed” (does not imply a financial transaction was recorded).
- Contribution truth hardening:
  - Draft Monthly Reviews no longer affect allowance usage or performance cash-flow calculations.
  - Completed Monthly Reviews are authoritative; completed review contributions count only when confirmed, or when an explicit skip override exists (override_amount = 0).
  - Pension allowance usage now respects overrides and completed Monthly Review contributions (and counts the effective “into pot” amount).
  - Performance contribution cash flow now uses effective “into pot” (tax relief / LISA bonus / employer match, net of any contribution fee).
  - Monthly Review completion avoids writing fresh snapshots for manual/Premium Bonds accounts unless their balance was updated in that review.
  - CSV holdings import marks touched accounts as holdings_updated for Monthly Review state.
  - Allowance POST routes reject wrong account types (ISA/pension/dividend).

### Fixed
- Backup/restore UX hardening: clearer preview metadata, stale export warnings, explicit destructive confirmation, and safer backup diagnostics copy.

### Compatibility
- Legacy `ghcr.io/jahumac/shelly-finance` image publishing remains in place for rollback/migration compatibility.
- Existing appdata paths such as `/mnt/user/appdata/shelly-finance` can still be reused safely during migration.

## [1.8.0] - 2026-04-20

### Added
- **Professional Pricing Engine**: Integrated Twelve Data API as the primary source for high-reliability live prices.
- **Currency Intelligence**: Automatic FX conversion for USD and EUR holdings into GBP account values.
- **Security Hardening**:
    - Cryptographically hashed API tokens (SHA-256).
    - Strict Content Security Policy (CSP) with no inline JavaScript.
    - Global API rate limiting (60 req/min).
    - Optional Redis support for shared rate limiting across multiple instances.
- **Manual Refresh Cooldown**: 3-minute cooldown to prevent API credit burn and server race conditions.
- **Improved Observability**: Detailed provider breakdown (TwelveData, Yahoo, etc.) in the refresh success banner.

### Fixed
- **Atomic Transactions**: Background price updates and holding syncs are now wrapped in SQL transactions to prevent data corruption.
- **"Stuck Price" Bug**: Normalized database timestamps to ensure the Overview page always reflects the true latest update.
- **Browser Caching**: Added strict `Cache-Control` headers to prevent stale HTML views after refreshes.
- **Maintenance Safety**: Implemented `ON DELETE CASCADE` across the schema for automatic and safe data cleanup.
- **Concurrency Safety**: Database migrations are now multi-worker safe, preventing race conditions during container startup.

### Changed
- **Modular Assets**: Moved all inline JavaScript logic to a dedicated external `app.js` file.
- **Neutral Branding**: Updated UI wording from "Yahoo Finance" to "live market data providers" to reflect the new multi-source capability.
