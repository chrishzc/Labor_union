---
doc_type: decision-work-package
declared_status: approved
execution_state: in-progress
identity: PROV-20260822-operations-frontend-real-data-readiness-priority-amendment
date: 2026-08-22
owner: React Admin Integration Owner
authority: latest-explicit-human-decision
db_change: none
---

# 營運作業前端與真實資料驗收優先序修正

## 人工裁決

目前先完成營運作業前端，順序改為：訂單管理（`#orders`、`#order-tracker`）→排班日曆
（`#scheduling`）→月嫂名冊（`#staff`）→資料匯入（`#data-import`）。本裁決只調整工作佇列與驗收順序，
不改變Domain owner、SSOT、public contract、交易邊界、既有Work Package write set或mutation授權；與舊交接順序
衝突時以本裁決為準。

## 三層驗收門

1. fixture／假資料：strict client、adapter、render、錯誤、race、pagination與request budget focused UI tests PASS。
2. 本機真實引擎：只在`APP_ENV=development`及`lu_test_*` allowlist，以真MySQL、API與browser受控驗收；
   `lu_test_*`是開發測試資料，不是真實業務資料。
3. 工會主機真實資料：另行取得明確主機存取／部署／操作授權後，才以工會主機上的真實業務資料驗收。

前一層失敗必須先修正，不得把未通過候選交給工會主機試錯。未取得第三層授權前，禁止連線、部署、操作
production DB/provider或執行production mutation。

## 可操作標準與邊界

- Query涵蓋正式資料範圍與cursor continuation，不得只顯示第一頁。
- Preview零寫入並顯示typed blocker、version／fingerprint與來源lineage。
- Apply只在owner Work Package、能力、fresh-fact、idempotency、receipt、re-query與scoped readback通過時解鎖；
  未通過者維持原生disabled。
- 匯入逐family閉合；HCM Preview不代表Client BeClass、Staff historical、Historical Orders或Bank/Finance完成。

本包不授權schema／migration／seed／backfill、`union_db`、production host、entry switch、deployment或provider
side effect。本包沒有DB變更：Scope與Change inventory `PASS`（四類皆none）；其餘DB gate `NOT_RUN`，固定結論
`DB_CHANGE_NOT_READY`。
