# `faq` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`10_知識與擷取紀錄`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：跳過待確認（待 LINE API 接通與實測）
- 根事實展開：跳過待確認（待 LINE API 接通與實測）
- 規格反查：跳過待確認（待 LINE API 接通與實測）

- Schema：`db/schema.sql`
- live writer／reader：未找到 production caller；也不在 Data Browser 白名單。
- 現況資料：最近的保留資料升級證據顯示本表為空表。
- 舊規格定位：提供聊天機器人與客服人員使用的 FAQ 知識來源。
- 規格漂移：LINE 設計規格的 RAG／FAQ 章節明列「未定案」，且規劃的是不同資料表 `faq_knowledge`，包含 `category`、`standard_question`、`standard_answer`、`redirect_url`；live `faq` 只有 `question`、`answer` 與技術時間。
- 本輪處理：依既有裁決，所有 LINE 相關功能跳過待確認；不得由目前未使用的 live Schema 反推最終 RAG／FAQ 權威模型。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `INT AUTO_INCREMENT PRIMARY KEY` | live FAQ row 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 一筆 FAQ 內容。 | 待 LINE FAQ 模型確認後再決定。 | 無 live owner | 無 | 無 live 契約 | 目前沒有 caller；最終規格可能使用不同的 `faq_knowledge` 表。 | 跳過待確認（待 LINE 實測） |
| `question` | `TEXT NOT NULL` | live Schema 的標準問題文字。 | 內容來源事實候選 | 無公式。 | 無 live writer。 | 人工核准的標準問題內容。 | 待 LINE FAQ 寫入、版本與向量同步流程確認後再決定。 | 無 live owner | 無 | 無 live 契約 | 規格稱 `standard_question`，且預期需觸發 embedding 同步；現況均不存在。 | 跳過待確認（待 LINE 實測） |
| `answer` | `TEXT NOT NULL` | live Schema 的預設答案文字。 | 內容來源事實候選 | 無公式。 | 無 live writer。 | 人工核准的標準答案內容。 | 待 LINE FAQ 回覆、版本與發布流程確認後再決定。 | 無 live owner | 無 | 無 live 契約 | 規格稱 `standard_answer`；目前沒有 caller、內容審核或發布邊界。 | 跳過待確認（待 LINE 實測） |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | live FAQ row 建立時間。 | 技術時間 | DB `CURRENT_TIMESTAMP`。 | DB clock。 | FAQ row 建立事件。 | 待最終 FAQ 資料模型確認；若保留則應統一 UTC 且禁止 caller 指定。 | DB／無 live owner | 新增 row | 不變 | DB session timezone 契約未明，且本表可能不是最終模型。 | 跳過待確認（待 LINE 實測） |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | live FAQ row 最近更新時間。 | 衍生技術時間 | 任意 row UPDATE 時由 DB 自動刷新。 | DB row update。 | FAQ 內容或其他欄位的最後修改事件。 | 待最終 FAQ 版本／發布模型確認；不可直接視為已發布內容版本。 | DB／無 live owner | 任意 row UPDATE | 持續變動 | 只表示資料列更新，不表示 embedding 已同步或 LINE 已採用新版內容。 | 跳過待確認（待 LINE 實測） |
