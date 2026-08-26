# Global Entry Point Governance

## 1. Purpose

API endpoint、Streamlit page 與 direct CLI 是外部可達契約；被 router mount、動態 page loader 或
`__main__` 串起，不等於仍有合法業務用途。它們不得以「有 wiring」逃避 legacy retirement audit。

## 2. Entry SSOT

`03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl` 是現況 entry discovery 與人工裁決
清單。每筆都必須有唯一 `entry_id`、kind、source path 與下列其中一個 status：

- `review_required`：尚未逐項裁決；不得因這個狀態被誤認為 active，也不得擴大功能。
- `active`：必填業務情境、操作者、canonical owner 與 public／operator contract。
- `retired_410`：僅限 HTTP；必填 replacement 與 retirement decision，route 必須回 typed `410 Gone`。
- `operator_only`：僅限 CLI；必填操作情境、操作角色、owner 與安全邊界。
- `removed`：source path 已不存在，並有 replacement 或明確不再需要的決策證據。

不得以「內部沒有 static caller」自動刪除 API、UI 或 CLI entry。API 的外部 consumer、UI 的
dynamic navigation、CLI 的人工維運都屬可能 caller；只有逐項業務裁決後才可退役。

2026-08-26 人工已核准 current entry queue 的 caller／replacement 盤點、focused regression、
retirement plan 與 cutover rehearsal。這項核准允許逐 entry 準備與驗證，不會把 `review_required`
自動改成 retired，也不直接授權 production entry switch、source removal 或不可逆 retirement；實際
切換前仍須逐項取得 exact target、replacement readback、rollback、maintenance window 與涵蓋該
entry 的 execution approval。任一資訊缺失固定 fail closed。

## 3. One-entry review procedure

每次只處理一個 `entry_id`：

1. 確認實際 route/page/CLI entry 與所有可見 caller；
2. 寫明「誰在何種人事／訂單／帳務／維運情境操作」；
3. 指定 Global、Domain、Subsystem 或 Module canonical owner；
4. 裁決 `active`、`retired_410`、`operator_only` 或 `removed`；
5. 若 retired，先完成 replacement／external contract boundary，再移除 source；
6. 執行 focused regression 與 entry queue validator。

實際執行 `retired_410`／`removed` 前，還必須保存切換前 caller inventory、replacement 可達證據、
回復路徑與切換後 readback；rehearsal passed 不等於 production switch completed。

## 4. Automated boundary

`scripts/generate_entrypoint_review_queue.py` 從 FastAPI decorators、Streamlit title pages 與
`__main__` CLI 產生 discovery queue。`tests/test_entrypoint_review_queue.py` 會拒絕：

- source entry 與 queue 不一致；
- duplicate entry id；
- 已裁決 entry 缺業務情境、操作者、owner 或 replacement；
- `retired_410` 非 HTTP entry，或 `operator_only` 非 CLI entry。

這個 queue 是入口治理，不是 runtime telemetry；它不記錄呼叫次數、人員、案件、payload 或 log。

## 5. 資料中心 React 正式入口（2026-08-26）

- canonical 側邊欄入口為 `資料中心`，沿用 `data-import` hash 作穩定 identity。
- `資料中心` 內固定包含 `NAS 檔案`、`資料匯入`、`數據瀏覽` 三個分頁；分頁不是新的 Domain owner，
  只組合各自 typed Query／Command UI。
- 現行 `data-browser` 不得直接刪除。它作為 compatibility deep link 時，必須開啟資料中心的
  `數據瀏覽` 分頁；不得再顯示為側邊欄獨立項目，也不得建立第二份 Data Browser 實作或 API client。
- 舊入口轉向須保留 hash query、認證後目標與瀏覽器 back／forward 語意，並以 focused route／navigation
  regression 證明匯入流程、數據瀏覽 Query 與未送出草稿沒有退步。
- NAS 分頁採已核准的高保真前端狀態機與使用者設計，明示清單、容量、下載、上傳與刪除目前皆為
  本機介面預覽；不得宣稱已操作 NAS 或資料庫。實體 mount path、arbitrary path query、browser-side
  file mutation、NAS mount／搬移與 provider delivery 均不屬本次入口切換。後續 typed storage adapter
  只能填入真實資料，不得覆蓋或簡化既有 UI。
