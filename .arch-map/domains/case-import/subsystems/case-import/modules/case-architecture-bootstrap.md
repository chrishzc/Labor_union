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

## Dependencies
- inbound: `case-import/order-information` — BeClass raw survey 僅在 Case Import projection boundary 解析為 named scalar facts。
- outbound: `payroll` — rate policy snapshot 是 assignment Payroll terms 的來源。

## Verification
- test_root: `tests/domains/case-import/subsystems/case-import/modules/case-architecture-bootstrap/`
