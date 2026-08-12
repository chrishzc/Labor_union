# UI 工作區測試資料情境矩陣

- 狀態：`in-progress`
- Priority：`P0`
- Owner：UI validation／各 owning Domain
- Domain／Subsystem：Case Import、Orders、Contract Signing、Client Finance、Scheduling、Staff
  Payables、Government Subsidy、Anomalies／Validation Dataset
- 更新日期：2026-08-11
- 核准日期：2026-08-10
- 目的：在既有 UI 工作區驗收業務事件的計算、狀態、異常與修正結果；pytest／DB verifier 是證據，不是 UI 的替代品。
- 正式依據：[`21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md`](../架構重整/01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md)
- 已完成執行範圍：[`56_Contract_Signing_and_UI_Validation_Work_Package.md`](../架構重整/04_已完成與上線封存/work_packages/56_Contract_Signing_and_UI_Validation_Work_Package.md)

本文件只擁有 UI 驗收情境 backlog，不再定義契約簽署、服務承諾、訂金、Contract
Completion 或 execution conversion 的架構語意。架構衝突一律以上述正式規格為準。

## 分層與責任

| 層級 | 責任 |
|---|---|
| Global | `lu_test_dataset_*` 為唯一資料目標；初始 schema 建立後，WP56 v4 依人工裁決採 append-only 每次新增案例，禁止覆寫候選／正式庫或重建既有 v4。 |
| Domain | Case Import、Orders、Client Finance、Scheduling、Payroll、Subsidy、Anomalies 仍各自擁有根事實與正式命令。 |
| Subsystem | scenario runner 只編排正式 Import／Preview／Apply；不能直接 INSERT 衍生 projection、alert、receipt 或 status。 |
| UI | 既有訂單、月曆、帳務及異常警示頁只讀 typed API view，呈現事件後的結果與可用修正入口。 |

## Scenario 的強制格式

每個 scenario 必須包含 `Arrange → Event → Observe → Repair → Re-observe → Replay`：

1. Arrange 只產生根事實或外部輸入。
2. Event 是正式 typed command／import；預覽與套用的版本、fingerprint、idempotency 必須保留。
3. Observe 同時有 DB verifier、pytest API contract、既有 UI workspace oracle。
4. Repair 只能走 owning Domain 的正式命令；Alert resolve 不可取代問題修正。
5. Re-observe 驗證 projection／blocker／alert 的新狀態。
6. Replay 驗證同 key 不重複寫入。

## 第一批 UI 情境

| ID | 可見 UI 工作區 | 事件與預期 UI 結果 | 現況判定 | 完成缺口 |
|---|---|---|---|---|
| UI-ORD-BLOCK-001 | 訂單總覽／合約完成面板 | Case Import 後缺 `contract_identity` 與契約所需精確服務日；顯示洽談中與 typed blockers。 | `in-progress` | v4 DB receipt 已驗證 `DSV1-CASE-0001` 為洽談中且零契約 roots；UI 狀態畫面已保存為 `evidence/wp56_ui_ord_block_001_v4.md`，仍缺 typed API blocker 與 Replay／repair 驗收。 |
| UI-CI-INVALID-001 | 異常警示中心／Import review | 非法 Case Import 外部列被隔離；零正式 case；顯示 IMPORT 類型 alert 與 review 入口。 | `in-progress` | v4 append runner 已建立單一遮罩 review root，驗證 canonical Client／Orders／Client Finance roots 零增量、exact replay 與 changed-payload conflict；仍缺 typed API、UI 操作／視覺證據與完整 repair。 |
| UI-FI-MANUAL-001 | 訂單收款核銷／異常警示中心 | 銀行原始入款分類不完整，顯示 `finance_import_manual_review`；人工分類後 alert 解除。 | `in-progress` | v4 runner 已完成 open review→owning Finance correction→alert resolved→same-key replay，並有專屬 DB oracle receipt；仍缺 UI 操作／視覺證據。 |
| UI-ANOM-REOPEN-001 | 異常警示中心 | 人工 resolve 但根因仍存在時 scanner reopen；UI 顯示 open→claimed/resolved→open。 | `in-progress` | v4 已有專屬 runner、timeline verifier 與 DB receipt，證明 claim→resolve→reopen→auto_resolve→reopen；仍缺 UI 截圖或人工驗收 receipt。 |
| UI-ORD-CONTRACT-001 | 訂單、收款、排班 | 月嫂先簽→承諾→訂金可先核銷→客戶簽回→Contract Completion；UI 分開顯示訂單與契約狀態。 | `in-progress` | normal-chain runner 與 v4 DB oracle 已驗證 immutable archive、雙方簽回、Contract Completion、settled deposit 及 exact assignment；UI status/archive screenshot 已保存為 `evidence/wp56_ui_ord_contract_001_v4.md`，仍缺同 key browser replay 與 repair evidence。 |
| UI-SCH-ASSIGN-001 | 月嫂配對、月曆、訂單 | 訂金與客戶契約均完成後，精確承諾轉為 assignment／正式工作日，顯示 coverage、工時與月曆。 | `in-progress` | v4 normal-chain oracle 已驗證 one commitment→one converted event→one assignment→five schedules；仍缺 UI 操作／視覺證據、occupancy conflict 與 repair/replay。 |
| UI-SP-PAYABLE-001 | 月嫂付款、應付輸出 | assignment 產生應付、精確出款、少匯補救。 | `in-progress` | v4 read-only Accounts Payable oracle 已聚合兩筆 immutable obligations 為一筆 `staff_payable`、總額 7200；仍缺出款／少匯 repair command 與 UI evidence。 |
| UI-GS-CLAIM-001 | 補助清冊 | 申請、核准、政府入款唯一核銷與歧義。 | `in-progress` | v4 正式 claim workflow 已新增 Q3 draft batch，12 items、requested total 433200、single outbox/receipt 與 exact replay；仍缺提交、核准、入款核銷與 UI evidence。 |

## Existing integration mapping

本表是既有整合的 discover index，不新增 UI、API 或業務責任。執行驗收時必須先依此表選擇
owning surface；不能因目前導航選單、預設年月或可見資料不同，就推論 integration 不存在。

| Scenario | Existing bounded UI integration | Typed client／formal repair boundary | DB receipt owner |
|---|---|---|---|
| UI-ORD-CONTRACT-001 | `ui/pages/order/editor.py` → `ui/pages/order/contract_match_panel.py` | `contract_signing_api_client.py`；Contract Signing commands 與 Contract Completion | `validation/receipts/UI-ORD-CONTRACT-001_v4.json` |
| UI-ORD-BLOCK-001 | `ui/pages/order/editor.py` → `ui/pages/order/contract_match_panel.py` | `contract_signing_api_client.py`；matching／staff signing 所屬命令修復 blocker | `validation/receipts/UI-ORD-BLOCK-001_v4.json` |
| UI-CI-INVALID-001 | `ui/pages/06_finance_alerts.py` → `ui/pages/anomalies/beclass_import_review_panel.py` | `beclass_import_review_api_client.py`；Case Import review Preview／Apply | `validation/receipts/UI-CI-INVALID-001_v4.json` |
| UI-FI-MANUAL-001 | `ui/pages/04_finance.py` → `ui/pages/finance_import/panel.py` | `finance_import_api_client.py`；Finance correction Preview／Apply | `validation/receipts/UI-FI-MANUAL-001_v4.json` |
| UI-ANOM-REOPEN-001 | `ui/pages/06_finance_alerts.py` anomaly registry detail path | `anomaly_registry_api_client.py`／`anomaly_recovery_api_client.py`；owning root repair | `validation/receipts/UI-ANOM-REOPEN-001_v4.json` |
| UI-SCH-ASSIGN-001 | `ui/pages/03_calendar.py` → `ui/pages/scheduling/case_staffing.py` | `assignment_plan_api_client.py`；Assignment Plan Preview／Apply | `validation/receipts/UI-SCH-ASSIGN-001_v4.json` |
| UI-SP-PAYABLE-001 | `ui/pages/04_finance.py` → `ui/pages/order/tab4_accounts_payable.py` | Accounts Payable typed query；Staff Payables owning payout/recovery command | `validation/receipts/UI-SP-PAYABLE-001_v4.json` |
| UI-GS-CLAIM-001 | `ui/pages/government_subsidy/claim_panel.py` | `government_subsidy_api_client.py`；claim plan／submission／approval Preview／Apply | `validation/receipts/UI-GS-CLAIM-001_v4.json` |

本表的 UI module 是 canonical display owner；其被哪個 navigation composition 載入屬 entry-point
治理，不改變 scenario 的 Domain、Subsystem、command 或 receipt owner。

## 現況裁決與執行順序

- `orders.contract_identity` 已有 worktree writer／API 骨架，不再記為「完全不存在」；但尚未具備
  客戶簽回、Contract Completion、剩餘期款與 receipt/outbox 的單一交易閉環，因此只能判定
  `partial`，不得以檔案存在宣告情境完成。
- `scripts/seed_payment_schedule_normal_case.py` 目前只建立 Case Import 根事實；在正式 runner
  完成 matching、signing、commitment、finance reconciliation 與 assignment Apply 前，不得以
  名稱或最終狀態 verifier 取代 command lineage 證據。
- 第一批負向／異常情境與正常鏈可各自施工，但每一個 UI ID 都必須獨立完成本文件的六階段
  scenario 與四類驗收證據，不能用其他 scenario ID 的 receipt 代替。

## Scope／Out of scope／Dependencies

- Scope：八個 UI scenario 的 runner、fixture、expected manifest、typed API/UI oracle、Repair、Replay
  與驗收證據。
- Out of scope：直接修改 production／candidate 資料、以 SQL seed 衍生狀態、把 pytest 當成 UI
  驗收、在本文件重新定義 Domain 狀態機。
- Dependencies：正式規格 `21`、Work Package `56`、乾淨 `lu_test_dataset_*` schema、可重播正式
  commands，以及各 owning Domain 的 disposable-MySQL 驗收能力。

## 驗收證據

每個已導入案例必須保存：

- versioned root fixture 與 expected manifest；
- DB verifier JSON；
- pytest result（Domain／API contract／replay）；
- UI 操作截圖或人工驗收紀錄，包含 case／alert identity、預期欄位與修正前後狀態。

## Write set 與 required tests

- Write set：`validation/datasets/`、`validation/scenarios/`、`validation/expected/`、完成後的
  `validation/receipts/`、validation seed/verifier scripts、對應 API/UI typed clients/panels、直接
  對應 tests 與本文件。實際 production write set 仍受 Work Package `56` 限制。
- Module／Subsystem tests：fixture parsing、typed views/errors、Preview 零寫入、Apply replay/conflict、
  Repair 與 Re-observe。
- Domain tests：每個 owning Domain 使用 disposable MySQL 驗證 root→projection→repair，不得以
  fake 最終 dict 取代。
- Global tests：乾淨 validation schema、完整 command lineage、DB verifier、API contract 與實際 UI
  oracle；所有八個 UI ID 均須獨立取得 receipt。

完成條件是八個 scenario 均滿足強制六階段與四類證據；全部完成後只在本文件改為
`completed` 並連結 evidence，不建立另一份「完成版」。
