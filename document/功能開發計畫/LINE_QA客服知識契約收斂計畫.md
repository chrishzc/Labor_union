---
doc_type: feature-plan
declared_status: approved
updated: 2026-09-02
owner: Customer Service / Knowledge Retrieval / LINE Integration
domain: Customer Service / Knowledge Retrieval / LINE Integration
source_artifact: document/line/AI客服QA題庫.jsonl
source_artifact_role: runtime-catalog
db_change: none
---

# LINE QA 客服知識簡化規格

## 1. 目的

LINE QA 題庫 runtime 只保留「啟用／未啟用」兩種狀態，不建立額外的 review workflow、五態狀態機或逐列治理平台。

正式 runtime catalog 為：

`document/line/AI客服QA題庫.jsonl`

`document/line/QA問答集.xlsx` 可保留作原始素材與人工查核來源，但 runtime 不直接讀取 Excel。

## 2. 題目欄位

每筆 QA 使用以下欄位：

- `id`
- `category`
- `tag`
- `question`
- `aliases`
- `answer`
- `enabled`
- `source_ref`
- `notes`（可選）

Runtime 不再使用 `ready`、`partial`、`missing`、`review_required`、`manual_only` 等狀態。

## 3. 啟用規則

### `enabled=true`

- 題目可進入 AI／語意比對候選集合。
- 回答必須使用 catalog 內既有 `answer`。
- 模型只能協助選擇候選 QA，不得自行生成新的政策、費用、資格或業務規則。

### `enabled=false`

- 題目完全排除於自動回答候選集合。
- 即使有 question、alias 或暫存 answer，也不得由自動客服使用。
- 人工確認內容後，直接修改題目並將 `enabled` 設為 `true` 即可，不需要另一個 runtime 狀態。

Loader 對 `enabled` 採嚴格 boolean 驗證；缺欄或非 boolean 視為 catalog 無效，不自行推測。

## 4. LINE 回答順序

```text
LINE 文字
  → 身分／角色與固定指令
  → Service Help deterministic route
  → enabled=true QA／Knowledge 語意比對
  → 命中：回 catalog 固定答案
  → 未命中：安全 fallback
  → 明確找真人／否定答案／客訴：既有客服 ticket / escalation
```

固定指令與四角色功能優先於 QA。QA 不負責角色判定、Rich Menu switch 或任何 Domain mutation。

## 5. UI

AI 客服工作室的常見 QA 題庫只顯示：

- 全部
- 啟用
- 未啟用

摘要顯示總筆數與已啟用筆數。UI 不再顯示五種舊狀態。

## 6. 來源與安全邊界

- `source_ref` 保留，用於人工追查原始資料。
- `notes` 可保留內容疑義或編輯提醒，但不影響 runtime 狀態。
- 題庫本身不授權任何寫入客戶、訂單、排班、財務或身分資料。
- 未命中題庫時不得由模型猜測答案。

## 7. 驗收

1. JSONL 每筆只有 boolean `enabled`，不存在舊 `status` 欄位。
2. Loader 嚴格驗證 `enabled` 並可只回傳 enabled items。
3. `/api/v1/line/ai-events/qa-catalog` 回傳 `enabled` 與 `enabled_count`。
4. React QA panel 只提供啟用／未啟用 filter。
5. `enabled=false` 不得進自動回答候選集合。
6. 固定指令、真人客服與客訴 escalation 行為不因本規格改變。
