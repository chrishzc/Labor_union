# Data Browser Query Page-Slice Contract Matrix

Status: `candidate-frozen-local`; browser gate is `NOT_RUN`.

| React tab | Public source | Repository source | Cursor | Masked output |
|---|---|---|---|---|
| `orders_archive` | `orders` | `orders` | case number | status, service dates, updated time |
| `clients_archive` | `clients` | `clients` | positive id | masked name, city, identity-status, updated time |
| `staff_archive` | `staff` | `staff` | positive id | masked name, city, source status, updated time |
| `beclass_history` | `beclass_intake` | `beclass_records` | positive id | query number, masked name, received/updated time |
| `hcm_history` | `hcm_review` | `case_import_hcm_review_rows` | positive id | masked case identity, issue codes, created time |
| `bank_facts_history` | `bank_facts` | `finance_import_rows` | positive id | date, direction/status, masked amount, created time |

Endpoint: `GET /api/v1/admin/data-browser/sources/{source_id}` with `limit 1..100`, optional opaque `after`
and bounded `query`. Response is strict `DataBrowserMaskedPageView` → row arrays → scalar cell arrays. Unknown source,
cursor/query invalidity, source mismatch, duplicate row/cell and masking/schema drift fail closed.

The new endpoint contains no raw row, dynamic table identifier, phone, address, identity number, bank account,
counterparty, survey/HCM/import payload, source correction or mutation. Drawer consumes loaded `detail_cells` and
issues zero additional GET.
