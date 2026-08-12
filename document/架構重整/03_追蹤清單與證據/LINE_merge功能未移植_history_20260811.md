# LINE merge 功能未移植 history（2026-08-11）

本文件只記錄第一版刻意不移植的 legacy 行為。它們不是現行規格，也不可直接恢復 caller；未來必須先補足架構決策與人工確認。

| Merge 行為 | 第一版處置 | 未來可移植的必要條件 |
|---|---|---|
| LIFF 接受 query string `userId` 作正式身分 | 不移植 | 無；此模式違反身分信任邊界，只能使用 verified ID token |
| 月嫂在排班頁直接送出並套用請假／代班 | 不移植正式 mutation | 建立 Scheduling-owned intake、人工 Preview／Apply、expected versions、fingerprint、occupancy mutex、Finance／Payroll／Orders impact |
| 客服 Service 接受欄位名稱直接 UPDATE clients | 不移植 | 每個可修改欄位需有 owner Domain typed command、欄位 policy、preview、expected version、audit 與 reversal contract |
| `client_profile_change_requests` 部分核准／回復 | 延後 | 先定義 Customer Profile aggregate、欄位權威性、跨 Orders projection、不可變 decision event 與 reversal 語意 |
| 連續兩次無法辨識後自動建立客服需求 | 延後 | 需要 durable conversation session、expiry、event lineage 與 exact replay 規格 |
| 完整客服對話歷史、指派、SLA、統計報表 | 第一版僅保留必要 ticket/event | 需補 assignment、SLA clock、escalation、reporting projection 與個資 retention 規格 |
| 舊 `line/line_bot.py` 直接 SQL／直接建 task | 不移植 | 不接受；功能只能改寫為 canonical handler、Domain service、repository 與 Unit of Work |
| 舊 `line/worker.py` 的 `line_push_message` 分支 | 不移植 | 使用現有 canonical `LineDeliveryRequest` payload 與 `LineDeliveryWorker` |

## 未來檢討原則

1. 先判斷資料 owner 與正式根事實，不以 merge 現況當規格。
2. 補齊 Global → Domain → Subsystem → Module 架構並取得人工確認後才可實作。
3. 不得為了還原畫面功能而建立第二套 Orders、Scheduling、Customer 或 LINE runtime。
4. 任何正式 mutation 都必須具備 typed error、expected version、idempotency、audit、conflict 與人工操作入口。
