# Root Cause Analysis & Resolution: Chart Rendering Regression

## 1. Executive Summary
A critical regression was identified where all charts throughout the application failed to render, displaying only empty containers. This was accompanied by the disappearance of the bug reporting button in the holdings interface and failures in various interactive features.

## 2. Root Cause Analysis
The investigation revealed that a recent security hardening update introduced a strict **Content Security Policy (CSP)** in `app/__init__.py`:
```python
csp = (
    "default-src 'self'; "
    "script-src 'self' https://cdnjs.cloudflare.com; "
    ...
)
```
This policy intentionally omits `'unsafe-inline'`, thereby blocking all inline JavaScript. Since the application relied on inline `<script>` tags within Jinja2 templates for chart initialization and dynamic UI logic, the browser blocked these scripts, causing the rendering failures.

## 3. Implementation Details
The resolution involved a systematic migration of all inline JavaScript to external, CSP-compliant files:

### 3.1 Chart Initialization (`charts.js`)
- **Centralized Logic**: Created a robust `DOMContentLoaded` listener in `app/static/js/charts.js` that scans for specific canvas IDs.
- **Data Transfer**: Updated templates (e.g. `app/templates/overview.html`, `app/templates/accounts.html`) to pass data via `data-` attributes (e.g., `data-labels`, `data-values`).
- **Interactive Support**: Moved logic for period switching (1D, 1M, ALL) and range pills into the external listener.

### 3.2 Feature Migration (`app.js`)
- **Holdings Lookup**: Moved the instrument search and Yahoo Finance lookup logic from `app/templates/holdings.html` to `app/static/js/app.js`.
- **What-If Calculator**: Ported the complex client-side projection logic from `app/templates/projections.html` to `app/static/js/app.js`, utilizing data attributes for baseline metrics.
- **Tag Management**: Migrated the account tag add/delete functionality to `app/static/js/app.js`.

### 3.3 UI Restoration
- **Bug Reporting**: Re-inserted the "Report a bug" button into the `badge-row` of the `app/templates/holdings.html` listing interface.

## 4. Verification & Testing
- **Chart Rendering**: Verified that Line, Doughnut, and specialized financial charts render correctly across all views.
- **CSP Validation**: Confirmed no "Refused to execute inline script" errors remain in the browser console for primary features.
- **Responsive Behavior**: Ensured that the externalized chart logic correctly handles canvas resizing and high-DPI displays via the `drawFallback` and Chart.js options.

## 5. Preventive Measures
- **Externalize by Default**: All future JavaScript logic must be placed in `app.js` or `charts.js`.
- **Data Attributes for Jinja2**: Use `data-` attributes to pass server-side variables to client-side scripts.
- **CSP Auditing**: Regularly check the browser console for CSP violations during development.
