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
- `infrastructure/mysql/staff_payout_repository.py` — 選定正式應付後，即使預計付款日或補助流向尚未形成（`due_date IS NULL` 且無不可解分期歧義），同案同月嫂之已發生出款仍可經既有 `MySqlStaffPayoutRepository` Preview／Apply 核銷；`_verify_sinopac_payout_targets` 與 `_verify_taishin_memo_recipients` 驗證備註案件與授權月嫂身分，`staff_installment_funding_unconfirmed` 僅於需要補助／自費分期才能決定本次可核金額時阻擋。`AccountsPayable` 清冊／匯出仍維持付款日、路由與收款帳戶防線，不因已建帳或已完成既有出款核銷而開放匯款或自動結案。永豐以完整帳號或受保護之同案備註核對而不將交易參考編號充作月嫂收款帳戶；台新以原始備註姓名唯一確認月嫂。
- `query_staff_funding_portions` 共用原正式分期與按銀行核銷連結的 typed 自備款／補助款餘額；自動配對與正式 Preview／Apply 均按出款銀行限額（包含部分／超付模式），同月不合併跨來源，未知分配不推定。原案件 Query 投影各來源待付與整筆出款手續費，沒有新金融 writer 或 schema。
- 原 payout Preview／Apply 的 `confirm_subsidy_split` 明確承接單案單筆永豐自備款。Preview 只讀既有案件補助金額 Query；Apply 先鎖案件、客戶／Payroll account、補助來源及原月嫂事實，在原 Staff Payables outer UoW 內借用方案事件 writer、Payroll 缺席分期 writer及原付款 writer。型別 `StaffSubsidySplit` 隨原 preview fingerprint 驗證金額、方案版本、日期及分配；同鍵重播沿原收據。既有方案不同、來源缺失或矛盾拒絕，不改一般獨立方案儲存語意。`api/routes/staff_payout.py`／`api/dependencies/durable_job_handlers.py` 沿原 durable command 轉送旗標，不新增 job 或外部派送。
- 依規格 #22 §6「案件帳務手動補登與自動銷帳」，人工補登另以Finance Import命令收據綁定的同案exact obligations確認月嫂，投影manual_confirmed_staff_id；不要求交易帳號，不改一般銀行來源的帳號／備註驗證。核銷金額、fee、difference、projection、receipt及outbox仍由本owner原workflow負責。
- Finance Import 的月嫂出款、客戶入款後備配對與客戶退款在 `infrastructure/mysql/finance_import_owning_domain_composite.py` 先以可核實的案件、對象、用途與精確義務識別收斂競爭候選（`_filter_competing_obligations`），僅於仍可能競爭之候選缺少到期日時回報 `due_date_missing`。永豐薪資及台新月嫂補助候選在宣稱可自動核銷前委派本 owner 同一 Preview，正式 Apply 仍重驗原版本、來源及分配。

<a id="contracts"></a>

## Contracts ^staff-payout-owner-write

```yaml archmap-impact
- kind: implements_requirement
  source: staff-payout-owner-write
  target: .arch-map/requirements/16_Staff_Payables與Client_Refund正式規格.md#^staff-payout-reconciliation
```
- 台新原始備註的唯一月嫂姓名與正式案件／指派關聯，可於原 Preview 投影方案一分期，選填六碼須與該案一致。交易月份由 Finance Import 自動配對檢查；六碼指定案件的跨月流水可走單筆人工核對，沿原 Preview／Apply 重驗對象、案件及款項。Apply 沿原 outer UoW 鎖來源、確認銀行方案及原 Payroll 分期，再核銷原月嫂義務。一般／歷史訂單同用資格，無方案或分期不直接視為無款；未達資格明示阻擋，方案不得使月嫂總應收增加。既有永豐自備款限制保留。
- `.arch-map/requirements/05_Staff_Payables_Export_Domain.md` §2–3。
- `.arch-map/requirements/16_Staff_Payables與Client_Refund正式規格.md`。
- #16 §2.2：非同步 Apply 的 `202 JobAccepted` 是受理，不是已核銷。付款事件、義務連結和成功收據在原 owner 的同一交易提交；以背景工作成功收據加正式根資料回讀為核銷證據。不等於所有款都結清，清償狀態以各選定義務回讀為準。

## Verification
- integration_root: `tests/domains/staff-payables/subsystems/staff-payables/integration/test_staff_payout_reconciliation_workflow.py` — 既有合成案例核對相同命令重送回傳原收據，不增加寫入。
- integration_root: `tests/domains/staff-payables/subsystems/staff-payables/integration/test_staff_payout_repository_recovery.py`
- integration_root: `tests/domains/staff-payables/subsystems/staff-payables/integration/test_staff_subsidy_split_mysql.py` — 無方案／無分期共同確認、已有分期、先前部分付款、原日期、來源衝突、同鍵異命令及中途失敗整筆回滾；補助先付時銀行別餘額與月清冊／逐案查核一致，含自備款小於補助款。
