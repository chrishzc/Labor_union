---
doc_type: receipt
declared_status: completed
---

# Form Management Legacy List Caller Migration Receipt

## Completed boundary

Form Management no longer reads the legacy full-list `GET /api/v1/orders` or
`GET /api/v1/clients` endpoints. Case selection now uses the existing bounded
`GET /api/v1/orders/summaries` typed client with a 50-item keyset page and
explicit previous/next navigation.

The page's pre-existing template facts are preserved by two authenticated,
read-only Orders queries:

- `GET /api/v1/orders/form-management-statistics` returns only the five
  existing global template metrics.
- `GET /api/v1/orders/{case_no}/form-management-context` returns only the six
  client context fields required after a case is selected.

Neither query writes facts, derives UI-owned business rules, or introduces a
second Orders list API. The statistics retain the previous page calculation
semantics, including the legacy government-claim eligibility predicate.

## Evidence

- `tests/test_form_management_query.py`,
  `tests/test_form_management_order_summary_migration.py`, and
  `tests/test_order_summary_query.py` passed: 13 tests.
- `tests/test_form_management_query_disposable_mysql_e2e.py` passed against a
  fresh disposable `lu_test_form_management_query` MySQL schema: 1 test. It
  proves statistics and selected-case context are read from canonical MySQL
  facts without the legacy list endpoints.
