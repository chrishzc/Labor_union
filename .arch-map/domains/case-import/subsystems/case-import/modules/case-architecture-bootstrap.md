# Module: case-architecture-bootstrap

## Parent
- subsystem: `case-import`

## Responsibility
以 Case Import named scalar facts 建立 first-use Client Finance、Payroll 與 Scheduling roots。Status 在提供 bootstrap Preview 前先揭露缺少正式開始日或正整數服務天數；修復介面只顯示實際缺少欄位，由 Orders-owned terms repair 補齊，另一項沿用 owner 已保存值。Payroll rate classification 優先使用 BeClass 已保存的 effective `multi_birth_count`，無胎數 correction 時才使用原始問卷值；可覆寫 identity classification，Client Finance identity semantics 不變。

- Bootstrap 付款條款透過 Client Finance stage plan 計算第二期預計日，正式 Apply 一併保存欄位及初始事件；以 Orders floor fee 與身分補助涵蓋判斷零金額，預覽不建立義務。

## Implementation
- `domains/bootstrap/case_architecture.py`
- `domains/case_import/case_import.py`
- `infrastructure/mysql/case_architecture_bootstrap_repository.py`
- `infrastructure/mysql/case_import_repository.py`
- `subsystems/bootstrap/case_architecture_status.py`
- `api/routes/case_architecture_bootstrap.py`
- `ui_react/src/api/case_import/case_architecture_bootstrap_client.ts`
- `ui_react/src/components/CaseArchitectureBootstrapRepairPanel.tsx`

## Dependencies
- outbound: `client-finance/obligation-planning` — 第二期預計日與零金額條件重用 Finance stage plan；bootstrap 不建立正式應付義務。
- inbound: `case-import/order-information` — BeClass raw survey 僅在 Case Import projection boundary 解析為 named scalar facts。
- inbound: `clients/client-profile/profile-change` — 客戶名冊只在 owner readback 回報缺少 bootstrap root 時提供既有 Q/P/A 修復入口，不直接寫入 Client Finance、Payroll 或 Scheduling。
- outbound: `payroll` — rate policy snapshot 是 assignment Payroll terms 的來源。
- cross-owner evidence: `tests/domains/case-import/subsystems/case-import/integration/test_registry_correction_disposable_mysql.py` — saved effective birth correction survives first-use bootstrap; Case Import subsystem owns this integration proof.

## Verification
- test_root: `tests/domains/case-import/subsystems/case-import/modules/case-architecture-bootstrap/`
