---
doc_type: specification-gap
declared_status: proposed
date: 2026-08-28
owner: global-ux / react-presentation / line-surface-owners
authority_status: CONFIRMED-2026-08-28
terminal_status: SPEC_GAP
task_id: CUR-UI-STITCH-UNIFICATION-01
priority: Task-96-last
---

# Task 96 Stitch UI 風格統一規格缺口

## 1. 已確認需求與邊界

使用者已確認：Task 96 新增功能完成後，最後執行一次 UI 風格統一；新增但未套用既有視覺語言的
功能必須先以 Stitch 產生可比較的設計證據，再整合回 React。LINE 功能預期是主要盤點範圍，但
不得只檢查 LINE，也不得用 Stitch 輸出直接覆蓋 current business flow、owner contract、既有使用者
dirty changes 或已通過的互動行為。

本項固定為 Task 96 最後順位。它不阻擋歷史異常、DB 1003→current、Rich Menu、LINE 模組 1～4、
完整契約 PDF 或其他功能包，也不得在功能契約尚未收斂時提前施工。

## 2. Objective

在所有前順位功能已完成或有明確 terminal disposition 後，建立 current React surface inventory，找出
未套用共同 UI 語言的頁面與元件；以 Stitch 對代表性高差異畫面提出設計稿，再把人工選定的方向轉成
可重用 design tokens／components，逐頁修正並以真 Browser 驗收視覺、responsive、WCAG 與既有功能。

## 3. In scope

- React 管理端與 current LINE 管理／LIFF 工作台新增 surface 的視覺一致性盤點。
- 色彩、字級、間距、卡片、表格、表單、狀態、空／錯誤／載入、drawer／dialog 與 responsive pattern。
- 同一 business fact 的資訊階層與重複顯示；技術 provenance 預設收合。
- Stitch 代表性設計稿、選定方向、DTCG-compatible tokens／component mapping 與 before/after evidence。
- desktop／mobile 真 Browser、keyboard、focus、contrast、zoom、loading/error/empty 與功能 regression。

## 4. Non-goals

- 不改 Domain owner、API 語意、狀態機、權限、交易或外部副作用。
- 不以假資料、靜態 mock 或 Stitch 圖稿冒充 current API／Browser 驗收。
- 不重新設計已明確放棄的營運分析／月報，也不把個人美感偏好當成新業務需求。
- 不覆蓋、刪除或搬移使用者既有 dirty UI changes。

## 5. SPEC_READY 前仍需收斂

1. 在執行當時，以 final current routes 建立 surface／state inventory，特別標記 LINE 新增功能。
2. 固定現行可保留的品牌／視覺基線與不可改互動，避免 Stitch 概念稿成為隱性產品改版。
3. 選出少量代表性 surface 送入 Stitch，保存輸入、輸出與人工採用／拒絕理由。
4. 建立 page → token／component → acceptance coverage matrix，並凍結不重疊 write set。
5. 在使用 Stitch 前確認當時 runtime capability；不可用時標 `BLOCKED_CAPABILITY`，不得自行改用
   其他生成式設計服務或跳過設計證據。

## 6. Candidate acceptance

- 所有 current React routes 與重要 empty／loading／error／success state 都有 inventory 與 disposition。
- LINE 新增功能不存在孤立色彩、字級、spacing、card、table、form 或 feedback pattern。
- 採用的 Stitch 方向已轉為共用 token／component；未採用稿不進 production。
- 去除重複資料時仍保留 owner 語意差異與單一可展開 provenance 入口。
- desktop／mobile、keyboard、focus、contrast、200% zoom、overflow 與 screen-reader label 通過。
- 真 Browser 證明 current API 功能、錯誤處理與主要流程無 regression；Stitch 圖稿不算 runtime evidence。
- final receipt、owner acceptance、task package 與 current 總表在同一 completion turn 同步為完成。

## 7. Spec Pipeline 狀態

已具備需求 Authority，但 surface inventory 與代表性設計方向只能在前順位功能定稿後取得，故目前為
`SPEC_GAP`，不得編譯 `PACKAGE_READY` 或提前修改 production UI。到達最後順位時重新執行
`spec-workshop`；收斂為 `SPEC_READY` 後才由 `task-pack` 編譯 bounded packages，再交 DDH 執行。
