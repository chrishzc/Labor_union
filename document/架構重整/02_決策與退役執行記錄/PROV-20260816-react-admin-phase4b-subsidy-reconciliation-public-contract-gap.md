---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260816-react-admin-phase4b-subsidy-reconciliation-public-contract-gap
date: 2026-08-16
owner: Government Subsidy Reporting / Access
domain: Government Subsidy / Reporting / Access
subsystem: Subsidy Reconciliation Preview / Export
successor_proposal: PROV-20260817-react-admin-phase4b-subsidy-report-authority-hardening
---

# Phase 4B-S：Subsidy reconciliation typed authority／PII／download 缺口

## 0. Blocked scenario

React Reports／Finance 想顯示季度、年度補助核銷並下載 XLSX。現行四個 route 使用 raw
`BaseResponse[dict[str, Any]]` 或 binary response、缺少 admin auth，且 query module 自行從 Orders、Clients、
BeClass 推導補助時數與金額，不能直接升格成 Government Subsidy 正式 read model。

Exact backend-first successor 已提出於
`PROV-20260817-react-admin-phase4b-subsidy-report-authority-hardening-work-package.md`；root-fact／公式無法由
正式規格唯一決定時必須維持blocked。

## 1. 已證明 live-drift

1. quarterly／annual preview 沒有 typed row schema，raw dict 會穿過 public boundary。
2. preview／export routes 沒有管理員驗證。
3. quarterly payload 含身分證字號、地址等敏感欄位，沒有 masking/capability contract。
4. JSON 與 workbook 欄位不一致；annual payload 還包含 workbook 未使用欄位。
5. `reconciliation_register_query.py` 直接從多個 source projection 計算資格、時數與金額，不是已證明的
   Government Subsidy ledger/root-fact query。
6. export 缺 hash、size、correlation 與 preview lineage。
7. ReportsPage 的三-sheet weekly workbook 沒有相同 backend contract，不得用本 route 冒充。

## 2. Successor 必須先裁決

- report owner、root facts、資格／時數／金額正式公式與 date semantics；
- quarterly／annual typed Pydantic views、nullable/required、masking 與 display/export field policy；
- admin auth、report capability、Global typed errors、correlation；
- Preview 與 XLSX 的 lineage、hash、size limit、retention/replay；
- FinancePage 與 ReportsPage 哪個是 canonical entry，是否仍需要同一個三-sheet workbook。

## 3. Candidate successor write set（未授權）

`api/routes/finance_reports.py`、新的 subsidy report schemas、正式 Government Subsidy reporting query/application、
focused route/domain tests，以及 successor 核准後的 React bounded client／adapter／page tests。若新增 owner、
public interface、transaction 或 DB/schema，必須另立 exact Work Package 並執行相應 gates。

## 4. Close condition

typed authority、auth／PII、binary metadata、focused tests 與 browser download evidence 全部閉合前，
quarterly／annual preview、export及 generic weekly workbook 均顯示 `BACKEND_GAP / unavailable`，禁止假下載。
