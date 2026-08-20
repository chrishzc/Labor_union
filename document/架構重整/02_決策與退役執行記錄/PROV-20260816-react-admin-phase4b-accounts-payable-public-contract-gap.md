---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260816-react-admin-phase4b-accounts-payable-public-contract-gap
date: 2026-08-16
owner: Staff Payables Reporting / Access
domain: Staff Payables / Client Finance / Government Subsidy / Access
subsystem: Accounts Payable Preview / Export / Archive
successor_proposal: PROV-20260817-react-admin-phase4b-ap-public-contract-hardening
---

# Phase 4B-AP-H：Accounts Payable public contract／PII／download 缺口

## 0. Blocked scenario

React Finance 頁面需要查詢應付帳款摘要並下載 XLSX。現行 preview、export、archive routes 沒有
管理員驗證；preview 又公開完整銀行帳號與身分證字號。因此即使 success DTO 是 typed，也不得接入
React 或宣稱 Finance read/download slice ready。

Exact backend-only successor 已提出於
`PROV-20260817-react-admin-phase4b-ap-public-contract-hardening-work-package.md`，目前仍為`proposed`。

## 1. 已證明 live-drift

1. `GET /api/v1/finance-reports/accounts-payable`、`.../export`、`.../archive` 沒有
   `require_admin` 或 router-level 等價保護；`api/main.py` 也沒有補上全域 auth middleware。
2. `AccountsPayableRowView` 直接輸出 `bank_account` 與 `recipient_identity_card`，沒有 server-side
   masked display contract。
3. export 只有 XLSX content type／filename，缺 correlation、content length／上限及 server hash metadata。
4. preview 與 export 各自重新查詢，沒有 preview fingerprint；UI 不得宣稱「下載內容就是剛才預覽」。
5. archive 只有清單，沒有受保護的既有 archive download contract。
6. `view` query parameter 被忽略；`target_month` 轉成當月 15 日的語意未明列於 public contract。
7. legacy `/accounts-payable-summary` 已 410，禁止重新接回或以 raw dict 補洞。

## 2. 可保留的 backend 基礎

- workflow 使用 read-only snapshot，沒有更改付款／退款／ledger 狀態；
- workbook 產生後會計算 SHA-256；
- archive atomic write、拒絕覆蓋，hash 不一致 fail closed；
- archive failure 已有 typed error code。

這些只證明內部 query/export workflow 有基礎，不等於 public security contract ready。

## 3. Successor 必須先裁決

- preview／export／archive 的 admin auth 與 finance capability；
- preview 只回傳 server-masked PII，完整帳務資料只允許受保護 XLSX；
- request correlation 與 Global typed errors；
- XLSX 安全 filename、hash、size／上限及 empty/content-type validation；
- export 是 fresh snapshot 或 preview-fingerprint-bound artifact；
- archive list／download 的 retention、capability 與完整性驗證；
- request budget：初次 preview 1 GET、人工 export 1 GET、展開 archive 1 GET、0 polling／0 N+1。

## 4. Candidate successor write set（未授權）

- `api/routes/finance_reports.py`
- `api/schemas/accounts_payable_export.py`
- `tests/test_finance_reports_accounts_payable.py`
- 必要的 `tests/test_accounts_payable_export_workflow.py` regression
- hardening 通過後才可另立 React client／adapter／FinancePage read-download Work Package。

若 capability、shared exception handler、owner 或 public interface 必須改變，successor 需人工確認 exact
Work Package；本 gap 不構成 production code 授權。

## 5. Close condition

只有 auth、masked preview、binary metadata、typed errors、focused route/workflow tests 與 controlled browser
download evidence 全部閉合後，React 才能開 AP preview／download。其他 Finance mutation 仍保持 native disabled。
