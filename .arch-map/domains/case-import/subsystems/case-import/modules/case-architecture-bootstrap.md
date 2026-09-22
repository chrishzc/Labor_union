# Module: case-architecture-bootstrap

## Parent
- subsystem: `case-import`

## Responsibility
以 Case Import named scalar facts 建立 first-use Client Finance、Payroll 與 Scheduling roots。Payroll rate classification 可由 case 的 authoritative `multi_birth_count` 覆寫 identity classification；Client Finance identity semantics 不變。

## Implementation
- `domains/bootstrap/case_architecture.py`
- `domains/case_import/case_import.py`
- `infrastructure/mysql/case_architecture_bootstrap_repository.py`
- `infrastructure/mysql/case_import_repository.py`
- `ui_react/src/api/case_import/case_architecture_bootstrap_client.ts`
- `ui_react/src/components/CaseArchitectureBootstrapRepairPanel.tsx`

## Dependencies
- inbound: `case-import/order-information` — BeClass raw survey 僅在 Case Import projection boundary 解析為 named scalar facts。
- inbound: `clients/client-profile/profile-change` — 客戶名冊只在 owner readback 回報缺少 bootstrap root 時提供既有 Q/P/A 修復入口，不直接寫入 Client Finance、Payroll 或 Scheduling。
- outbound: `payroll` — rate policy snapshot 是 assignment Payroll terms 的來源。

## Verification
- test_root: `tests/domains/case-import/subsystems/case-import/modules/case-architecture-bootstrap/`
