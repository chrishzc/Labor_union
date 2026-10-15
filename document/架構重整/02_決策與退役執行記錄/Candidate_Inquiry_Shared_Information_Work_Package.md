# 候選詢問共用資訊實作

狀態：completed；Authority：2026-10-14 人工確認 UI 預覽，並要求三份內容分開寄送與瀏覽器驗證。以下 direct acceptance 已通過；無外部 provider 寄送或 production／entry switch。

Owner 與 contract：Scheduling Candidate Contact Pool；`../01_規格基線/02_Assignments_Scheduling_Domain.md` 的候選聯繫池 2026-10-14 裁決。Orders 保有資料與 Service Dates writer；LINE 保有 durable task 與 delivery。

範圍：候選工作台、共用 typed Query、逐人既有 Preview／Apply、第三份補充寄送事件與必要 release metadata。名冊換人與實際開始日更正不在 write set。只沿用既有 outer UoW、event key 與 recipient-bound fingerprint；content fingerprint 只描述共用文件內容，不能取代 writer 的 fresh read。

Schema：232 fresh／1051 preserve byte-equivalent ALTER，僅在 enum 尾端新增 `info_3_sent`；schema_only，無 seed／backfill／刪除／資料修正。原 ordinal、欄位與所有資料保持；exact predecessor 可 apply、exact successor 可 replay，其他 metadata drift 阻擋。rollback：切換前丟棄 disposable candidate；已套用後保留 enum，以 compatible forward release 處理。歷史 182 與既有 release 不修改。

新 release 已 qualification／apply 的原始 bytes 以 `.gitattributes` 限定這五個新 hash-bound 資產保留，避免後續 Git 行尾轉換改變已保存的 identity；原 artifact／receipt 不重寫。兩個 mutable current catalogs 使用 LF，重新對齊 assembly hash，完整 SQL reproduction check 通過。

驗收：新增候選成功回清單；無候選共用預覽；三份各自選人／發送任務／逐人回讀；個別意願與備註；推薦準備帶入且須顯式建立；未保存日期禁止寄送；stale Preview 零寫入、same-key 原 receipt replay、未知結果可恢復；名冊既有流程回歸；fresh MySQL 與舊 schema／代表資料 dump→candidate→apply→verify；正式 updater 唯讀 plan；build、focused tests、desktop／mobile browser 與 scoped architecture closure。

證據：`scratch/candidate-inquiry-implementation/` 為執行輸出；schema qualification final receipt 必須沿 migration 所需 archive 保存。沒有完成上述必要驗收前不得標示 umbrella 完成。

## DB gates

| Gate | 結果 | 證據 |
|---|---|---|
| Authority／scope | PASS | 本文件與 Scheduling owner 的 2026-10-14 裁決 |
| Classification／rollback | PASS | 232／1051 只追加 enum 尾端值；manifest schema_only、無 backfill |
| Release wiring | PASS | current fresh assembly、validation v45、完整 SQL、preserve ordered chain／hash 與 qualification 已同步 |
| Exact descriptors | PASS | `test_candidate_weekly_information_schema.py`；exact predecessor／successor，順序與 nullability drift 阻擋 |
| Read-only plan | PASS | `scratch/candidate-inquiry-implementation/maintenance-plan.json`：只待套 1051，零 DB 寫入 |
| Real engine | PASS | `validation/receipts/PROV-CANDIDATE-WEEKLY-INFORMATION-local-additive-qualification-20261014.json`；fresh／六種舊事件 source→dump→candidate→apply→verify，逐欄保留 |
| Developer acceptance | PASS | `launcher-preflight.json`、`maintenance-apply.json`、`local-apply-receipt.json` 與 `scratch/local_database_updates/fast_additive/union_db.receipt.json`；本機 additive current，未切換／替換 source |

首次 live backup 因備份期間 source 異動而零 DDL 停止，保留該次 preparing artifacts；暫停兩個已確認的本機 API 後重新取得 plan、備份與 qualified apply，成功後按原啟動參數恢復。前端亦恢復 5173。最後 8000／8001 的 OpenAPI 包含共用資訊路由；5173 經 proxy 回傳新路由的正常匿名 401。

## 功能驗收

`scratch/candidate-inquiry-implementation/browser/evidence.json`：Chrome 桌機 1440／手機 390，新增候選、無候選預覽、三份分開選人寄送與 exact owner 回條、單人重送、個別意願與備註、帶入客戶確認準備、saved／draft 日期限制與完成版抽屜畫面均 PASS。客戶確認使用正式 `/matching-plans/active` 檢查，不因導覽而自動建立方案。

`delivery-readback.json`：隔離 MySQL 的正式 LINE worker＋不連網 mock provider，18 個任務處理後三份各人的最新狀態 sent、原 event／task ID 與意願事件保持；外部 sends=0。candidate Query 讀 canonical task state，並不改写原發送事件。

`vitest-final.json`：229 項 focused UI tests PASS，含名冊既有流程；`build-final.log`：build PASS。後端 71 項 focused pytest、release check、diff check 與 `architecture-closure.json` PASS。實際 LINE provider 寄送為 NOT_RUN，不以 mock receipt 宣稱真實收件人已收到。
