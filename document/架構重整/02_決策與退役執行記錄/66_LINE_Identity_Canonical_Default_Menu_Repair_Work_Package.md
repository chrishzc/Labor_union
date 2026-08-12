---
doc_type: work-package
declared_status: completed-local-deployed
date: 2026-08-12
authorized_by: user
---

# 66. LINE 身分解除 canonical default menu 修復 Work Package

## Business scenario 與 owner

- 操作者：具 `line.identity.binding.manage` capability 的管理員。
- 情境：解除月嫂身分後，系統必須把該 LINE User ID 明確綁定至 canonical 最新已發布的
  `default_menu`，再完成 binding revoke 與 owner projection 清除。
- Domain／Subsystem：LINE Identity Management／Rich Menu publication。
- SSOT：`line_rich_menu_publication_tasks` 的最新 `published` `default_menu` publication；
  `line_rich_menu_publications` 只保留 legacy publication 歷史，不得再決定新解除請求。

## Live-drift

2026-08-12 唯讀診斷確認 `line_configuration_current` 與 canonical publication 已是
「服務登記／服務說明」，但 `MySqlLineIdentityManagementRepository` 仍從
`line_rich_menu_publications` 選出 2026-08-09 的「訂單查詢／尋找專員」。解除 worker 因而
成功套用錯誤的舊 provider menu。這違反
`01_規格基線/21_LINE身分管理與解除正式規格.md` 第 5、6、8 節。

## Scope 與 write set

- 讓新解除請求讀取 canonical 最新已發布 `default_menu` 的 publication ID／provider menu ID。
- 以向前相容 schema 保存 canonical publication FK；既有 legacy 解除紀錄保持可讀、不可改寫。
- 新增 stage 13 migration release metadata、repository/schema regression 與驗收 evidence。
- write set：
  - `infrastructure/mysql/line_identity_management_repository.py`
  - `db/schema_parts/179_line_identity_canonical_menu_publication.sql`
  - `db/migration_releases/labor_union_2026_08_12_line_stage13_v1*.json`
  - `tests/test_line_identity_management_first_release.py`
  - `document/架構重整/01_規格基線/21_LINE身分管理與解除正式規格.md`
  - 本 Work Package、索引與對應 evidence receipt。

## Out of scope

- 不套用 migration 到任何現有資料庫。
- 不呼叫 LINE provider，不自動重綁已受影響使用者。
- 不刪除或改寫 legacy publication、既有解除 request、binding event 或 owner 歷史。
- 不變更 API、capability、解除 state machine、transaction owner 或 retry policy。

## Acceptance 與 required tests

1. legacy publication 仍為舊版時，新解除 preview／apply 只選 canonical publication task。
2. 新 request 保存 canonical publication FK 與對應 provider menu ID；舊 request 仍可讀取。
3. canonical `default_menu` 未發布時維持 `line_identity_default_menu_not_published` fail closed。
4. migration 只新增 canonical FK 並放寬 legacy FK 欄位為 nullable，不刪除任何資料。
5. stage 13 manifest／descriptor hash 驗證、聚焦 pytest、`git diff --check` 與 UTF-8 檢查通過。

## Evidence

`03_追蹤清單與證據/evidence/2026-08-12_line_identity_canonical_default_menu_repair_receipt.md`。
