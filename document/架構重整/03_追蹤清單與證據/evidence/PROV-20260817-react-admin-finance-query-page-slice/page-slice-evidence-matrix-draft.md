---
doc_type: evidence-matrix-draft
declared_status: draft
identity: PROV-20260817-react-admin-finance-query-page-slice-evidence-matrix
date: 2026-08-17
owner: Finance React Page Integration Owner
not_a_receipt: true
---

# Finance Query Page-Slice Evidence Matrix（Draft）

本草案不是contract freeze、核准或驗收證據；實作前須依live Pydantic與route重新確認。

## 1. Endpoint／field disposition

| Tab／GET | Typed fields used | UI disposition | Current activation |
|---|---|---|---|
| Client Receipt `/orders/{case_no}/client-finance/receipt-reconciliation` | `case_no/account_version/bank_facts[]/obligations[]` | facts與obligations唯讀；settled狀態不推導 | typed GET；query auth需`require_admin` |
| Client bank fact | `finance_import_row_id/amount_ntd/transaction_date/dedup_fingerprint` | 去敏fact identity/amount/date | wired after route auth |
| Client obligation | `obligation_identity/payment_stage/amount_due_ntd/due_date` | server stage原值；settle disabled | wired after route auth |
| Staff Payables `/staff-payables/{staff_id}` | `staff_id/staff_payables_version/obligations[]/events[]` | obligation/event tables唯讀 | typed GET；query auth需`require_admin` |
| Staff obligation | `identity/case/amount_due/due_date/net_paid/balance/payout_status` | payout_status只顯示server值；mark-paid disabled | wired after route auth |
| Staff event | `id/event_type/amount/occurred_on/import_row/reversal/reference` | event history唯讀 | wired after route auth |
| AP `/finance-reports/accounts-payable` | `target_payment_date/row_count/total_amount/rows[]` | month preview | `blocked-public-contract` |
| AP row | payment date/type、recipient、bank code、masked account、amount、obligation/case IDs、masked ID card | 完整帳號／身分證禁止DOM | 需同包auth＋masked view |
| Finance Import `/batches` | batch id/identity/format/source file nullable/row count/status/version/architecture flag/created | list；status不映射成功 | typed GET；query auth需`require_admin` |
| Finance Import manifest | format/sheet/header/counts/digest/versions/timestamps | lazy read-only Drawer | wired after route auth |
| Finance Import review rows | row/date/direction/amount/classification/disposition/reconciliation/source/occurrence/actions | raw server labels；actions disabled | wired after route auth |
| Finance Import reprocess runs | ids/fingerprint/counts/status/timestamps/cursor | history唯讀；reprocess disabled | wired after route auth |

## 2. UI surface matrix

| Existing Finance surface | Target |
|---|---|
| 客戶收款核銷 tab | Client Receipt GET；`settle` native disabled |
| 月嫂薪資 tab | Staff Payables GET；adjustment／paid native disabled |
| 客戶退款＋政府補助 mock tabs | 收斂為 AP masked preview；approve／advance disabled |
| 銀行流水 tab | Finance Import batches/detail GET；upload/apply/reprocess disabled |
| 匯出總清冊 XLSX | 保留按鈕位置但disabled；本包0 export GET |
| 四個 mutation Drawers | 保留視覺槽位但unavailable；0 local state/alert/fake receipt |

## 3. Failure／budget matrix

| Evidence | Required behavior |
|---|---|
| no Session／401／403 | 0 anonymous fallback；typed unavailable/login |
| 404 selector target | explicit not-found；不自動冒充第一筆成功 |
| 409／422／503／timeout/network | code/correlation/retryability；不轉成empty |
| selection/tab switch | abort old request + stale discard |
| empty | explicit server empty；不顯示mock rows |
| AP redaction | response與DOM都不含完整bank account／identity card |
| request budget | active tab only；0 polling／0 N+1／0 non-GET |
| browser | existing DB只GET Network→DOM；Happy DOM不能替代 |

## 4. Forbidden substitutions

- 不使用 `client_payments.py` raw dict routes或retired AP summary。
- 不以amount equality、balance、中文message或local enum推導settled／paid／eligible。
- 不把JobAccepted、HTTP 200、mock、XLSX按鈕或歷史receipt當作Finance mutation成功。
- 不為次要欄位另拆gap；原位unavailable並繼續其他query tab。

Final matrix必須在production施工前由Integration Owner凍結；本草案不更新shared index。
