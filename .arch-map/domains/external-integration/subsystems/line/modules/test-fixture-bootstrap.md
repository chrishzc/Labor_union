# Module: test-fixture-bootstrap

## Parent
- subsystem: `external-integration/line`

## Responsibility
建立與復原 development／test 環境使用的 LINE 身分、訂單生命週期／十三核心階段情境、歷史訂單採用證據、月嫂關聯、帳務 owner facts 與 Rich Menu 前置資料；禁止在 production 執行，不擁有任何正式業務規則。

## Implementation
- `scripts/seed_line_test_fixtures.py`

## Dependencies
- outbound: `case-import | orders | assignments | scheduling | contract-signing | client-finance | staff-payables` — 僅依既有 owner contract 建立 deterministic 測試根事實與 evidence，正式業務語意仍由各 owning domain 定義。
- outbound: `external-integration/line` — 建立 LINE identity 與 Rich Menu 測試前置資料，不呼叫外部 provider。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/test-fixture-bootstrap/`

## Change triggers
Reconcile when the fixture production guard, seeded scenario contract, owner bootstrap boundary, or deterministic reset behavior changes.
