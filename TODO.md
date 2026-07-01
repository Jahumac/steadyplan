# SteadyPlan To-Do List

## 1. Complete the Website Sandbox Port
- [ ] **Test the Simulator:** Verify that the "Simulated API Integrations" (Trading 212 & InvestEngine) in the Sandbox provide realistic fallback data for users trying out the UI.
- [ ] **Hook up Import/Export:** Ensure the "Upload/Download JSON" buttons in the Sandbox settings actually serialize and deserialize the `localStorage` state correctly.
- [ ] **Mobile Responsiveness:** Do a final pass on the sandbox on mobile viewports to ensure the navigation and tables aren't breaking horizontally.

## 2. Immediate Roadmap ("Improving Next")
- [ ] **Reduce Density:** Simplify the heaviest setup and settings surfaces so it's less overwhelming for new self-hosters.
- [ ] **Tighten Data-Entry:** Polish the everyday workflows (CSV imports, manual updates, and validation flows) to reduce friction during the Monthly Update.
- [ ] **Documentation Parity:** Ensure the public website, documentation hub, and GitHub README perfectly match the current capabilities of the product (reflecting recent `pip-tools` addition and sandbox).
- [ ] **Security & Auth:** Strengthen supportability and authentication boundaries (e.g., locking down the API token/Assistant access further) before considering any hosted beta.

## 3. Backend & Integrations
- [ ] **Broker Integrations (Actual):** Stabilize the "broker snapshot review beta" for Trading 212 and consider rolling it out fully or adding similar API/scraping support for InvestEngine.
- [ ] **Multi-Currency Support:** Investigate adding basic EUR/USD native handling if tracking non-GBP core assets becomes a priority.

## 4. Technical Debt & DevOps
- [ ] **CI/CD Pipeline:** Set up GitHub Actions to run the `pytest` suite automatically on Pull Requests and check for outdated dependencies via `pip-compile --upgrade`.
- [ ] **Frontend Testing:** Write a few Playwright end-to-end tests for the new `site/sandbox.html` to prevent regressions and UI bugs.

## 5. Long-term Explorations
- [ ] **Invite-only Hosted Beta:** Investigate multi-tenancy constraints and secure user isolation if a hosted version is offered.
- [ ] **API Evolution:** Finalize external API endpoints so users can build custom integrations (e.g., pushing data from their own scripts safely).
