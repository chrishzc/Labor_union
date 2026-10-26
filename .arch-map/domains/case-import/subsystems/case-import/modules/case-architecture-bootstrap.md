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
- `subsystems/bootstrap/case_architecture_workflow.py` — `ensure_in_unit_of_work` 沿 caller 的交易，無 nested begin／commit。
- `api/routes/case_architecture_bootstrap.py`
- `ui_react/src/api/case_import/case_architecture_bootstrap_client.ts`
- `ui_react/src/components/CaseArchitectureBootstrapRepairPanel.tsx`

## Dependencies
- inbound: `orders/order-terms` — 完成缺件進件或洽談中完整補件時委派初始化，沿用正式政策與缺漏／partial protection，不修改既有付款與薪資資料。
- inbound: `contract-signing/external-signing-presentation` — 簽約文件缺少付款條款／薪資初始資料時，只顯示具體原因並導向同案客戶名冊；不在簽約頁嵌入補建 Preview／Apply，也不在 Query 自動補建。
- HCM 完整進件沿原 bootstrap adapter 在父命令相同交易同步客戶應收及應退；不另設操作關卡。
- cross-owner evidence: `tests/domains/case-import/subsystems/case-import/integration/test_hcm_automatic_accounting_mysql.py` — real MySQL intake、非零第二期逐期銀行核銷、重播與 rollback。
- outbound: `client-finance/obligation-planning` — 第二期預計日與零金額條件重用 Finance stage plan；完整正常案件在相同 UoW 自動同步各期客戶應付；不建立實際收付款或月嫂應付。
- inbound: `case-import/order-information` — BeClass raw survey 僅在 Case Import projection boundary 解析為 named scalar facts。
- inbound: `clients/client-profile/profile-change` — 客戶名冊只在 owner readback 回報缺少 bootstrap root 時提供既有 Q/P/A 修復入口，不直接寫入 Client Finance、Payroll 或 Scheduling。
- outbound: `payroll` — rate policy snapshot 是 assignment Payroll terms 的來源。
- cross-owner evidence: `tests/domains/case-import/subsystems/case-import/integration/test_registry_correction_disposable_mysql.py` — saved effective birth correction survives first-use bootstrap; Case Import subsystem owns this integration proof.

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_case_architecture_bootstrap_workflow.py` — 保留既有跨 owner workflow 測試位置，新增同步 seam；不搬移。
- test_root: `tests/domains/case-import/subsystems/case-import/modules/case-architecture-bootstrap/`
