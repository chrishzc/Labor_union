# 歷史訂單 review 人工更正工作包

- `work_package_id`: `CUR-P0-HISTORICAL-ORDER-REMEDIATION-01`
- `declared_status`: `in-progress`
- `owner`: Orders；Anomalies 僅作受控入口組合
- `scenario`: 操作者收到 `HISTORICAL-ORDER-001` 後，上傳唯一對應該 immutable review 的更正工作簿，完成可稽核的 Preview → Confirm → Apply → predicate recheck，而非把 alert 手動關閉。
- `authority`: 2026-08-26 使用者明確裁決「所有異常都應該要有人工修正的功能」；限本機 development／`lu_test_*` 驗收，不含 `union_db`、production、provider、entry switch 或 deployment。
- `formal_specs`: `01_規格基線/00_Global_共同契約.md` §2、`01_規格基線/01_Orders_Domain.md`「歷史 review 更正來源重新匯入」、`01_規格基線/06_Anomalies_Domain.md`。

## Scope 與 write set

允許新增 Orders-owned immutable remediation disposition、receipt、outbox 與其 additive schema release；新增
Orders typed context Query、Preview、Apply、API schema／route、outbox projector；新增 Anomalies 的 typed
Orders remediation renderer 與 focused tests。可以修改既有 historical adoption 的 command composition，僅為
避免 correction replay 重複 lifecycle／assignment／receipt。

不得修改 immutable `historical_order_adoption_reviews`，不得加入 Anomalies generic root editor、任意 status
resolve 或跨 Domain SQL。不得接受多 review 或不唯一列映射的更正工作簿；不得以 tracking state 代替 root
predicate。共同 manifest／release chain／catalog／lockfile 由 integration writer 單獨寫入。

## 依賴與不變量

1. `prior_review_identity` 是唯一 prior binding；所有 Preview 與 Apply 必須 materialize prior review、
   original receipt、Orders target、review／disposition versions、new workbook digest、actor capability。
2. Preview 零寫入；Apply fresh-read、lock、revalidate，使用單一 Orders outer Unit of Work。
3. immutable review 永不更新／刪除。每個 prior review 至多一個 remediation disposition，並以唯一
   idempotency／fingerprint 回放同一 receipt。
4. 合法更正列導向 `corrected_source_adopted` 並由 outbox auto-resolve prior alert；仍有 issue 時先建立
   successor review／warning，接著寫 `superseded_by_replacement_review` 並可追溯 successor。
5. payload mismatch、未授權、stale、非唯一對應、digest drift、preview stale、timeout 與 projector 未達
   predicate 必須保留 blocker，不得假結案。

## DB change inventory 與 gates

| 類別 | 目標 | 資料效果／回復 |
|---|---|---|
| schema-only | remediation disposition、receipt、outbox tables及 indexes／FK／triggers | additive；版本化 release 收錄，descriptor 必須完整列出 owned objects。 |
| system-seed | 無 | 不適用。 |
| business-row-backfill | 無 | 不回填既有 review；既有 open alert 保留，僅新的 owner Apply 建立 disposition。 |
| destructive | 無 | 不得 reset、replace、`--switch` 或操作 `union_db`／production。 |

實作前後均須依 root `AGENTS.md` §3.1 依序提供：scope、inventory、static release、descriptor、read-only
plan、fresh bootstrap、preserve-data candidate、developer acceptance gate。必要證據包括 source backup、candidate
receipts、old row preservation、new object exactness、rollback evidence。所有必要 gate 均為 `PASS` 前，總結固定
為 `DB_CHANGE_NOT_READY`。

## 驗收與 evidence

1. module／subsystem／domain focused tests 覆蓋 context redaction、zero-write Preview、capability、non-unique
   mapping、stale／replay、duplicate Apply、payload mismatch、clean correction、successor review、outbox timeout。
2. 真實 MySQL fresh bootstrap 與含代表性舊 review／receipt／warning 的 preserve-data candidate 通過；每項
   migration gate 依 §3.1 附 `PASS | BLOCKED | NOT_RUN` 表與命令／receipt。
3. 在允許的 `lu_test_*` 中以唯一 scenario identity 實測：Preview／Confirm／Apply 後讀回 immutable prior
   review、不重複 lifecycle／assignment、remediation receipt、outbox 與 prior alert inactive 或 successor
   active；只清理本次 owned rows。
4. React Browser 由 enabled persisted human Session 走完「修正此筆歷史匯入」；local bypass、401／403、
   stale 與失敗檔案都保持 fail closed。無 enabled persisted Session 時 Browser 正向標 `BLOCKED`，不得以
   local bypass 或單元測試代替。
5. historical detail 至少顯示每個 issue 的欄位路徑、遮罩來源值／既有值、規則、流程阻擋與此筆更正的
   完成條件；只顯示「歷史訂單欄位衝突」或追蹤狀態不得通過。成功 Apply 後 prior alert 必須自 active
   list 消失，或顯示具體 successor issue 與其修正入口。

## Completion

完成後更新 `96_Current_剩餘代辦任務總表.md`、Orders／Anomalies 正式規格、active evidence index 與 final
receipt。此包只完成 `HISTORICAL-ORDER-001`；其餘異常依 necessity partition 由
`PROV-20260826-all-anomaly-manual-remediation-spec-gap.md` 逐 owner 收斂與分包：目標為 `33 active anomalies
+ 7 owner work items + 1 retired false-positive + 1 audit-only successor occurrence`。

## DDH 執行拓撲紀錄

| 時點 | phase／模式 | 變動依據 | 實際安排 |
|---|---|---|---|
| 2026-08-26 初始盤點 | E4 isolated read-only lanes | 當時文件記為 41-code；2026-08-26 現場 canonical registry 重載確認為 42-code。registry audit、schema contract 與 UI/API contract 可獨立讀取，且不寫 shared worktree。 | 三條唯讀 lane 平行完成，主代理整合其 evidence；後續以 42-code 為完整範圍。 |
| 2026-08-26 schema proposal | E3 serial exact-patch proposal | `1006`、release chain、assembly／catalog 是 shared hot spots，並行 writer 無隔離收益；需先由專家產生單一 SQL proposal。 | 一條唯讀 patch-producer；主代理只在 proposal 驗收後以 native `apply_patch` transport 整合。 |
| 2026-08-26 schema proposal terminal | E3 → E2 integration writer | 唯讀 patch-producer 在 90 秒 idle lease 內未回傳 proposal；native terminal receipt `479a0ca48d74a5c62e80852f4c1874a19c43bfec64d88c677b34cf913c0a5c8d` 為 failed，且無 workspace effect。單一 shared SQL 的重派沒有獨立收益。 | 由主代理以已完成的獨立 schema／API audit 為 evidence 寫入；同一 operation revision 不重派。 |
| 2026-08-26 DB receipt verification | E3 read-only producer → verifier（Luna High） | final candidate receipt 是 material migration evidence，需獨立交叉檢核；兩條 lane 均為 `gpt-5.6-luna`／`high`，沒有 child write。 | reader 指出原 candidate 只有 empty-data preservation；verifier 因代表性 review／receipt／warning rows 為 0 而正確拒絕 terminal acceptance。native receipt `d14b02a7845f10c2bebb37016e2f4a981f4580cbd8ad09e31ea9946b3cc8d565` failed，無 workspace effect。 |
| 2026-08-26 legacy-row migration rerun | E3 → E0 deterministic controlled validation | 上列 `VALIDATION_OUTCOME` 顯示缺口不是語意不明而是明確缺少 representative rows；重新派 agent 沒有額外收益。 | 在 `lu_test_*` source 建立 1 筆既有 historical review／receipt／warning，重跑 dump → candidate → apply/resume → verify；source/candidate 的 review、receipt、pairing evidence、current alert、warning occurrence／task 均各 1 筆且指紋相同，1006 為 exact。developer-acceptance replacement 仍待人工明確授權。 |
| API／React source 實作 | E4 isolated writers | backend、projector、React 是互斥新增檔；shared router／registry／worker／AnomaliesPage 仍是 hot spots。 | 三條 writer 均為 `gpt-5.6-luna`／`high`；主代理序列整合 shared files。 |
| 初版 verifier 拒絕 | E4 → E3 verifier/integration | verifier 找到常見 review 被 composition guard 永久阻擋、router 未掛、path／DTO 漂移、Preview 未跑完整 Orders rules；projector 另有 receipt binding、private helper 與 successor replacement 問題。 | 不接受局部綠測試；序列重構 adoption caller-owned UoW、完整 owner Preview、API/React round-trip 與 projector fail-closed binding。 |
| 修正版 source verification | E3 integration → E3 三條獨立 re-verifier | Python 77、React 49、production build PASS；runtime MySQL／Browser capability仍不存在。 | backend、API/React、projector 分三條 Luna High 唯讀 re-verification；DB/Browser 維持 `NOT_RUN`，不以 source tests 代替。 |
| 第二輪 verifier 拒絕與規則收斂 | E3 verifier → E3 integration writer | backend verifier 發現 generic admin capability、Preview 未鎖定、no-op adoption 仍寫 lifecycle、missing alert 誤判 inactive、successor warning 任意 fallback；其餘兩條 verifier 通過。這些均是同一 owner contract 的序列修正，無隔離 writer 收益。 | 依 Orders 規則書加入 `orders.historical_review.remediate` 並 materialize permission scope；Preview 在 caller-owned UoW 以 lock read 後 rollback；無 root change 不增加 lifecycle version／event；missing projection fail closed；不同欄位不建立錯誤 replacement link。focused Python 87 passed、7 skipped；再交 Luna High 唯讀 re-verification。 |
| 第三輪 verifier 與規格校準 | E3 三條唯讀 verifier → terminal source candidate | API/React、projector 直接 PASS；backend verifier 初判 no-op composition 與 successor mismatch 仍有風險，integration writer 以 Orders 正式規格第 3～5 點及可構造根事實反證，要求同一 Luna High verifier 重校準，不新增 writer。 | verifier 確認 same status/date 不寫 lifecycle，既有 assignment 不形成 candidate，replacement receipt 是規格要求；successor warning 先建立後可關閉 prior，review-level relation 保留而 occurrence 不錯綁。三條 Luna High 最終均 PASS；runtime MySQL／Browser 仍 `NOT_RUN`。 |
| 2026-08-27 runtime constraint failure | E3 exact proposal（Luna High） | 真實 MySQL Apply 暴露舊 `chk_historical_order_adoption_shape` 錯誤要求所有 adopted 均必須有 lifecycle event，與規則書的合法 no-op adoption 衝突；這是單一 exact successor patch。 | 動態將剩餘工作從 API runtime acceptance 重投影為 E3 唯讀 proposal → 主代理 integration writer；子代理為 `gpt-5.6-luna` / `high`，無 workspace write。 |
| 2026-08-27 1008 後驗收 | E3 → E0 deterministic validation | 1008 形狀、release、descriptor 均已精確，剩餘 restore／apply／verify、API replay 與 outbox 投影為可機械驗證的序列。 | 不再增加寫入代理；使用 `lu_test_*` 完成 fresh bootstrap、preserve-data candidate、Preview／Apply／replay／consumer／readback。enabled-human Browser 因沒有 persisted enabled Session 維持 `NOT_RUN`。 |
