---
doc_type: work-package
declared_status: completed
date: 2026-08-11
owner: finance-architecture
---

# UI navigation convergence

## Business scenario

An administrator must see one business-oriented navigation system. A page-file list must not appear
beside a second system navigation, and selecting an operational area must not import or query an
unselected area.

## Approved scope

- Hide Streamlit's file-derived sidebar navigation.
- Replace runtime page-directory scanning and AST title parsing with an explicit, grouped page
  registry in `ui/app.py`.
- Keep module import lazy: only the selected page module is imported.
- Separate **訂單管理** from **帳務作業中心**. The latter owns bank import, accounts-payable
  query/export, subsidy reconciliation, client receipt reconciliation, payroll adjustment, and
  staff payout reconciliation.

## Non-goals

This changes no Domain rule, API route, database schema, financial event, accounting transfer, or
typed anomaly action contract. **異常警示中心** remains the only recovery entry for a projected
anomaly and continues to use Query → Preview → Apply.

## Acceptance

- The app renders one sidebar navigation with the groups **營運作業**, **帳務**, and **異常與稽核**.
- The auto-generated page list is hidden by `.streamlit/config.toml`.
- `ui/pages/04_finance.py` is not imported until **帳務作業中心** is selected; each of its panels
  remains lazily imported.
- `ui/pages/02_orders.py` loads only order summaries and no longer preloads finance or staff facts.
- Focused navigation and bounded-query regression passes; browser smoke confirms that the app opens
  with only the custom business navigation visible.
