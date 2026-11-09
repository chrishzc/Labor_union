# Module: payout-reconciliation

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
沿既有 Staff Payables 契約編排銀行出款核銷、退匯與沖正的 Query／Preview／Apply；由同一 outer Unit of Work 保存付款事件、精確義務連結、projection、receipt 與 outbox，不發動銀行匯款。

## Implementation
- `subsystems/staff_payables/case_accounting_query.py`
- `infrastructure/mysql/case_staff_accounting_repository.py` — case-scoped effective obligation, payout and historical evidence; no month filter, no cash writer.
- `domains/staff_payables/reconciliation.py`
- `subsystems/staff_payables/payout_reconciliation.py`
- `infrastructure/mysql/staff_payout_repository.py` — 永豐以原始交易參考編號的完整帳號投影付款收款人；台新於Preview／Apply以原始備註姓名唯一確認月嫂，投影typed memo staff proof取代帳號必填，所選義務仍須同人。借用Finance Import的完整帳號及姓名擷取；備註六碼不作台新月嫂定位或銀行帳戶。其他格式的既有帳戶投影不變。
- 規格22 §19人工補登另以Finance Import命令收據綁定的同案exact obligations確認月嫂，投影manual_confirmed_staff_id；不要求交易帳號，不改一般銀行來源的帳號／備註驗證。核銷金額、fee、difference、projection、receipt及outbox仍由本owner原workflow負責。
- Finance Import 的永豐薪資及台新月嫂補助候選，在宣稱可自動核銷前委派本 owner 的同一 Preview；台新先重新驗證原始備註姓名且不要求帳戶，永豐沿原帳戶規則。正式 Apply 仍重驗原版本、來源及分配，不新增核銷 writer 或 transaction owner。

## Contracts
- `document/架構重整/01_規格基線/05_Staff_Payables_Export_Domain.md` §2–3。
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md`。

## Verification
- integration_root: `tests/domains/staff-payables/subsystems/staff-payables/integration/test_staff_payout_reconciliation_workflow.py`
- integration_root: `tests/domains/staff-payables/subsystems/staff-payables/integration/test_staff_payout_repository_recovery.py`
