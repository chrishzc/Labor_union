---
scope: 17_External_Integration_LINE_Access正式規格
status: proven-current-evidence
verified_at: 2026-08-09
---

# LINE、Access Control、Case Import 與 Knowledge 重新驗證收據

本輪已採用的 LINE review、Rich Menu 與管理員 session 具體政策，見
`04_已完成與上線封存/work_packages/52_LINE_Review_Rich_Menu_and_Admin_Session_Policy_Decision.md`。

## 已落地且重新驗證的範圍

- LINE review legacy routes 已依 `48` 固定回 410，正式 review router 維持 typed replacement。
- `49` 的 provisional LINE registration 已由 typed owner 處理相同 payload replay 與不同
  payload conflict；舊 LIFF registration route 不再直接寫 client、BeClass 或 LINE task。
- 本輪另發現 internal-key-only 的 `PUT /api/line/users/{user_id}/role/{role}` 仍可直接改寫
  LINE role。它現已固定回 `410 line_role_api_retired`，避免 service credential 被誤作
  human authorization。
- Access Control 現以固定 role bundle 加上有期限、versioned dynamic grant 對 LINE review
  decision、task read／control、Rich Menu publication、Knowledge 與 system configuration 作 API
  最終授權判斷；role hierarchy 只保留為相容查詢，非 API authorization decision。grant mutation
  必須有 expected authorization version、reason、idempotency／correlation identity，會同交易寫入
  immutable event／receipt、撤銷目標 session，並保護最後一位 dynamic system-admin。
- Knowledge Retrieval 現有獨立的 versioned source、event 與 receipt。content author 不得覆核或
  發布自己的內容；只有已發布項目可以查詢，回答回傳 source URI、content digest、version 與
  `authoritative=false`。LINE `rag_reply` 只送出這種 cited answer，沒有候選時轉人工。
- 已採用並實作 LINE 身分／重新綁定審核的永久待辦規則：沒有 due date、逾期、轉派、
  escalated state 或任何時間驅動的自動核准／拒絕；待審清單固定以最早送件優先，僅真人的
  explicit approve／reject／cancel 可離開 pending。
- 已採用並實作 Rich Menu 的單人 Preview → Confirm → Apply：管理員先取得目前設定版本的
  server-side preview receipt，再勾選二次確認才可建立 publication；receipt 綁定管理員、menu、
  config revision 與 fingerprint，內容變更或 receipt 已使用時一律 conflict，沒有雙人覆核。
- 管理員 session 已採 30 分鐘滑動閒置期限與首次登入起 8 小時 absolute deadline；每次有效
  請求只能延長至兩者較早者，deadline 到達後必須重新輸入密碼，缺 absolute deadline 的既有
  session fail closed。
- Security Audit 已採兩年線上保存、無自動 archive deletion；任何已登入管理員都可查摘要，
  不要求 `admin.audit.read` capability。IP 與敏感欄位固定遮罩；所有已登入管理員可直接查看
  已遮罩明細。背景 worker 每日把到期紀錄移至不對 UI 開放的 archive。
- LINE webhook inbox、identity review、暫存登記、Case Import、admin session 與 legacy-exit
  的聚焦測試為 `59 passed`；capability migration 與 Knowledge boundary 修正後相關回歸測試
  為 `49 passed`。這些測試沒有連線外部 provider 或正式資料庫。
- 使用者已於 2026-08-09 授權退役 BreezySign。現行 runtime、schema、正式基線與系統地圖
  已移除其功能；無損稿、既有 decision package 與 immutable inventory snapshot 僅保留為歷史
  退役證據，不是可執行規格或 runtime dependency。

## 尚待人工裁決的正式缺口

無；第 17 份列明的人工作業政策均已決定並實作。

## 驗證

- 本輪 Access／LINE／Security Audit policy 與 schema bootstrap／release chain：
  `82 passed, 1 skipped`；
- local Access／LINE／Knowledge 集合：`58 passed`；
- disposable MySQL 8.4：`1 passed`，覆蓋 temporary grant 導致目標 session revoke、不同人
  review／publish、published-only cited retrieval；
- schema bootstrap 成功載入 `147_access_capability_grants.sql` 與
  `148_knowledge_retrieval.sql`。
- current `formal_baseline_v1.json` 為 `669` writer findings、legacy runtime callers 為 0，
  validation SHA-256 為 `40d10928ff3af03b035d3d49b7b182ae2325ee26731ac8950efadca0bdcf91e3`。

第 17 份列明的 LINE review、Rich Menu、session、Security Audit、dynamic capability grant 與
Knowledge Retrieval 政策都已取得人工裁決並完成實作；未來的 policy 變更仍必須先更新決策。

## Current-source policy verification

```text
LINE / Access / Knowledge policy and retirement boundary suite
20 passed in 1.23s
```
