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

## 3. One-entry review procedure

每次只處理一個 `entry_id`：

1. 確認實際 route/page/CLI entry 與所有可見 caller；
2. 寫明「誰在何種人事／訂單／帳務／維運情境操作」；
3. 指定 Global、Domain、Subsystem 或 Module canonical owner；
4. 裁決 `active`、`retired_410`、`operator_only` 或 `removed`；
5. 若 retired，先完成 replacement／external contract boundary，再移除 source；
6. 執行 focused regression 與 entry queue validator。

## 4. Automated boundary

`scripts/generate_entrypoint_review_queue.py` 從 FastAPI decorators、Streamlit title pages 與
`__main__` CLI 產生 discovery queue。`tests/test_entrypoint_review_queue.py` 會拒絕：

- source entry 與 queue 不一致；
- duplicate entry id；
- 已裁決 entry 缺業務情境、操作者、owner 或 replacement；
- `retired_410` 非 HTTP entry，或 `operator_only` 非 CLI entry。

這個 queue 是入口治理，不是 runtime telemetry；它不記錄呼叫次數、人員、案件、payload 或 log。
