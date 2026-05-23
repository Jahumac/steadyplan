# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- User JSON backup/export in Settings and a hardened JSON restore flow (validate preview + explicit confirmation, transactional, current-user scoped).
- Overview Data Health panel (read-only) for stale/missing inputs.
- Monthly Review workflow (lightweight check-in with notes, contribution confirm/skip, and month completion snapshot).
- Manual account balance update workflow for regular use/monthly review.

### Changed
- Projection copy frames projections as scenario estimates.
- Monthly Review contribution copy uses “Confirmed” (does not imply a financial transaction was recorded).
- Contribution truth hardening:
  - Draft Monthly Reviews no longer affect allowance usage or performance cash-flow calculations.
  - Completed Monthly Reviews are authoritative; completed review contributions count only when confirmed, or when an explicit skip override exists (override_amount = 0).
  - Pension allowance usage now respects overrides and completed Monthly Review contributions (and counts the effective “into pot” amount).
  - Performance contribution cash flow now uses effective “into pot” (tax relief / LISA bonus / employer match, net of any contribution fee).
  - Monthly Review completion avoids writing fresh snapshots for manual/Premium Bonds accounts unless their balance was updated in that review.
  - CSV holdings import marks touched accounts as holdings_updated for Monthly Review state.
  - Allowance POST routes reject wrong account types (ISA/pension/dividend).

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
