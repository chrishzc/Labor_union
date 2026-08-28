# HCM 多問題匯入警示逐筆解除與 Umbrella 收旂 Work Package

- `declared_status`: `completed`
- `package_result`: `PACKAGE_READY`
- `authority`: 2026-08-27 人工裁決：同一匯入有三個問題時，每修正一個只解除該 occurrence；最後一個修正後整筆匯入警示消失。
- `owner`: Case Import HCM owning command；Anomalies 只擁有 current projection／tracking
- `formal_spec`: `01_規格基線/17_External_Integration_LINE_Access正式規格.md` §5.2.1 與匯入異常解除裁決

## Scenario 與不可破壞事實

同一 HCM review 可包含多個 `logical_code + field_path` occurrence。正式修正來源 Apply 後，只有通過
owner validation、binding 與 fresh-root readback 的 occurrence 可轉為 `auto_resolved`。同 review 仍有任一
未解除 occurrence 時，`IMPORT-004` umbrella 必須維持 active；未解除數為零時才能依新版
owner event 投影 inactive，並從 active list 消失。不得新增或重用人工 `closed`／tracking resolve 作為解除依據。

已解除 occurrence、source、event 與 receipt 保持 append-only 歷史；新來源產生 replacement／new
occurrence 時 umbrella 必須重新 active。未知 logical code、stale root、binding mismatch、readback failure
或缺少 current alert 一律 fail closed，不得宣稱整批完成。

## Write set

- `infrastructure/mysql/import_warning_auto_resolution.py`：依 exact occurrence 鎖定 review／source receipt，計算同 review 未解除數與去敏剩餘 issue snapshot。
- `domains/anomalies/registry.py`：只新增 `IMPORT-004` 已核准 aggregate owner terminal predicate，不放寬其他 code。
- `subsystems/anomalies/hcm_resubmission_outbox_consumer.py`：單筆 auto-resolve 後依 aggregate readback 重新投影 `IMPORT-004`。
- `tests/test_import_warning_auto_resolution_guard.py`、`tests/test_anomaly_rulebook_auto_resolution_guard.py` 及直接 HCM consumer focused tests。
- 本 Work Package、Task96 current 總表與 final evidence receipt。

`schema-only=NOT_APPLICABLE`、`system-seed=NOT_APPLICABLE`、`business-row-backfill=NOT_APPLICABLE`、
`destructive=NOT_APPLICABLE`。不新增套件、public API、provider effect、DB migration 或歷史資料改寫。

## Acceptance

1. 同 review 三個 occurrence 初始全部未解除，umbrella active。
2. 解除第一個後剩二個；只有第一個 `auto_resolved`，umbrella 仍 active。
3. 解除第二個後剩一個，umbrella 仍 active。
4. 解除最後一個後剩零，umbrella 依 correction event 的單調 source version 投影 inactive，active list 不再顯示。
5. 每個 occurrence 的 source／tracking events／receipts 保留；不寫 `closed`／manual resolve。
6. stale root、cross binding、unknown code、readback failure、新未解除 occurrence 與 projector failure 全部保持 umbrella active。
7. 同 review 的 correction outbox 必須依 id 序列處理；較早未 published 事件存在時，較晚事件不可被
   `SKIP LOCKED` 提前 claim，以保證 projector `source_version` 不倒退。

## Verification 與完成門

- focused domain／repository-helper／consumer tests；相關 HCM resubmission／IMPORT-004 regression；`git diff --check`；strict UTF-8。
- 有真 MySQL／service 時驗證 3→2→1→0 讀回、outbox replay 與 active-list removal。本次未啟動服務時，
  runtime 固定 `NOT_RUN`，不得以 fake 冒充。
- source 只在 focused tests 全 PASS、無 sibling false clear、無 tracking-close bypass 且獨立覆核後可標記完成。

## DDH 執行投影

前置 Luna High E3 唯讀覆核已定位單筆解除後 umbrella 不重投影的 P1 缺口。本包只有一個
cohesive write set，因此執行階段轉為 E2 主代理單一 writer；完成後再交給 Luna High E3 獨立驗證。

## 2026-08-27 執行快照

- source／focused candidate：`PASS`；最終 84 focused tests passed，compileall 與 `git diff --check` passed。
- E3 獨立驗證：三輪均使用 `gpt-5.6-luna` / `high`。前兩輪找到並關閉缺少 owner contract、
  missing-alert no-op、inner-join 漏算與同 review 亂序 checkpoint 四個 P1；最終輪 `PASS`，無 P0／P1。
- runtime：`NOT_RUN`；本次依使用者說明未啟動 Docker Compose、MySQL、API 或 React service，未以 mock
  充當真 lock／active-list evidence。
- final receipt：`../03_追蹤清單與證據/evidence/2026-08-27_hcm_multi_occurrence_umbrella_resolution_receipt.md`。
