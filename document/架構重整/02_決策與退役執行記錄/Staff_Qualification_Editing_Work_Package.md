# 完整資格主檔直接編輯

- Authority：2026-10-13 使用者要求完整資格主檔直接編輯，並明確同意補上技能、按摩證書與證照儲存。
- Owner：Staff qualification master；正式契約為 33 §3.2 的「完整資格主檔直接編輯」補充。
- 範圍：保留四分頁；在資格分頁重用個資／銀行與六項接案能力正式 writer，新增既有專業資格、照顧寶寶數與交通值的 Q/P/A。無 schema、migration、production、部署或外部效果。
- 驗收：技能可增刪、按摩證書支援有／無／未登錄、一般證照可增刪；服務數與交通可修改；預覽零寫入、確認後讀回；取消不保存、stale typed 409、same-key replay、失敗 rollback。
- 驗證：Staff qualification module 測試、資格編輯 UI 流程、既有個資銀行及六項偏好回歸、實際本機瀏覽器畫面與 API 路由。資料庫寫入驗證只使用 disposable lu_test_* 資料；不修改真實人員資格。
- 停止：本步驗收完成即停止；四分頁合併留待下一步。醫療／體檢與有效期 source unavailable 不創建人工通過狀態。

## 本步交付

### 下拉條件與欄位按需展開

最新子步 Authority：2026-10-13 使用者移除新增說明及其寫入，要求自訂開始／結束時間，
儲存須符合 4／8 小時與休息規則。以 24 的「六項接案條件與自訂服務起迄」為 current acceptance，
此裁決取代本子步先前的說明展開與其他時段自由輸入。時段 tuple 由 Staff Domain 驗證與編碼
至既有 slot identity，新 detail 為 NULL；來源說明唯讀，未變列不重新寫入。Matching adapter
沿同一 Staff tuple 投影服務時數，無 schema／migration、資料清除或額外起迄 eligibility。

本次自訂起迄驗收 PASS：backend 55 項、frontend 32 項；真 MySQL disposable 驗證不足
8.5 小時零寫入、完整時段保存／讀回、新 detail 為 NULL、舊說明無 DML、多個不同四小時
時段與媒合同來源時數；桌面／手機操作通過。Staff source／直接依賴／受影響 tests 的型別
檢查與前端單獨打包 PASS。本機 API 已載入 typed clock fields。
全專案型別檢查 FAILED：範圍外的 Orders／application-shell／Client registry tests 有既有或
同時進行中的型別錯誤，本次不修改這些測試。未執行 production、schema 或外部效果。

2026-10-13 最新 Authority：使用者要求六項接案條件改成標準下拉，新增條件時才增加欄位。
沿用 Staff 六 relation Q/P/A，新增 Staff-owned typed options Query 與新值 validation，範圍為
domain／workflow／HTTP／client／既有 StaffPage 及直接 tests，規格為 24 的「六項接案條件的下拉維護」。
驗收：正常只有已登錄的選單；按新增才有一個待選列；補充說明按需展開，既有說明保存；
新增／移除使 Preview 失效，重複不能選，既有非標準資料保留，新未知值／不可解析的其他時段
或排休被拒絕；保存後原 relation 讀回並供原 Matching fresh Query 使用。
效果上限維持本機 code、focused tests、synthetic disposable DB／Browser；無 schema／migration／
production data、外部效果或四分頁合併。

此子步驗證 PASS：backend 11 項、frontend 32 項、真 MySQL disposable 的 Preview 零寫入／
新未知值拒絕／保存與移除條件／同一名冊 projection 回讀／replay；桌面與手機的下拉與按需
展開流程通過，前端打包通過。本機 API 已載入 options 與 validation；既有真實人員資料未重寫。

- PASS：資格主檔 backend 16 項、前端相關 22 項、真 MySQL disposable 預覽零寫入／儲存回讀／replay／stale／receipt failure rollback、桌面與手機合成資料操作。
- PASS：前端單獨打包、本機 API 路由已載入，頁面代理要求登入（401）；架構歸屬與 diff whitespace 檢查。
- FAILED（範圍外）：標準完整前端 build 的 TypeScript 檢查被既有 `order_intake_completion_entry.test.tsx:157` TS2352 擋住；本步不修改訂單測試。
- 無 schema／migration／production data／外部 provider effect；本機真實月嫂資格未作測試寫入。四分頁合併尚未執行。
