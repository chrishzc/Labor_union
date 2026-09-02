# Workspace Agent Rules — Lightweight

本檔是 repository-wide 基線。最新人工明確指示優先，其次為 `document/架構重整/01_規格基線/` 的 current 正式規格與可追溯業務／欄位權威；程式碼、測試、附件與 Git history 只提供 evidence，不得反向創造需求或覆蓋正式語意。

`.agents/AGENTS.md` 只能補充個人互動與 Git 偏好，不得覆蓋本檔或正式規格。不得 reset、clean、stash、覆蓋、搬移或刪除既有 ignored／untracked／dirty 使用者成果。

## 1. 預設導航與停止條件

每個任務預設只按以下順序工作：

1. 記錄 branch、HEAD、`git status --short`，保留所有 dirty paths。
2. 使用者已點名精確 path、symbol 或 test 時，直接開該檔案；只在需要確認 owner／相鄰測試時讀最接近的 `.arch-map/` leaf，不得先遍歷根索引或搜尋整個 repository。
3. 使用者只描述功能、畫面或業務詞彙時，以 `.arch-map/` 作為第一個定位索引：先用 filename-only bounded search（例如 `rg -l`）只搜尋 `.arch-map/`，最多保留 10 個候選且不輸出全文。若命中唯一最接近的 Module／Subsystem leaf，直接讀該 leaf；候選仍不明時才讀 `.arch-map/index.md`，並只沿一條 `Domain → Subsystem → Module` 最短路徑往下，不開 sibling branches。
4. `.arch-map/` leaf 一旦指出 owner、source、adapter、直接依賴或測試路徑，導航即結束；只讀完成 current task 所需的目標檔案與一個最直接測試。
5. **停止條件：** 已能確定 current target、owner、write set 與 focused verification。達成後不得繼續做 repository-wide search、caller graph 擴張、相鄰 Module／Domain 探索或文件瀏覽；「可能相關」不是擴搜理由。
6. 只有 `.arch-map/` 明確標示未建模／incomplete、沒有路由、指向的 path 不存在，或目標檔案出現一個會實質改變行為／修改位置／驗證邊界的 unresolved dependency 時，才在最可能的 owner 目錄做一次 bounded symbol／path search。解決該 unknown 後立即停止，不得因地圖缺口轉成全 repository 掃描。
7. 預設不整目錄載入 `document/`、`.arch-map/`、`tests/`，不先讀完整 `README.md`，也不跑 full suite。
8. 一般 T0／T1 局部修改不建立新 spec、Work Package、receipt、架構圖或追蹤文件。

完成上述定位後，只有任務實際涉及下列邊界時，才讀對應的最小 current 文件：

- owner、SSOT、root fact、state machine、cross-domain invariant、public contract／entry point、transaction／Unit of Work：讀 `.arch-map/` 指向的單一 owning Domain／Subsystem 正式規格；只有 currentness 或裁決仍不明時才讀 `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`。
- concurrency／fingerprint：只讀 `document/架構重整/01_規格基線/00_Global_共同契約.md` 的相關段落。
- schema／migration／preserve-data／cutover：只讀 `10_Global_保留資料Migration與Cutover_Subsystem.md` 與直接相關 owner spec。
- entry point retirement／replacement：只讀 `19_Global_Entry_Point_Governance.md` 的相關段落。
- 驗證情境、測試資料與 coverage ID：只讀 `28_驗證情境與測試資料正式規格.md` 與對應 owner spec。
- LINE 服務說明、客服分類與 Rich Menu audience：只讀 `29_LINE服務說明、客服互動與選單角色正式規格.md` 及其上位規格 17、20。
- rollback、incident、舊 release 重現或稽核：從 Git history 精準取回必要 revision，不掃描或復活已退役文件樹。

不得因文件存在、checklist 未完成、測試很多或可能有風險，就自動擴大 scope。

## 2. 架構與執行邊界

- `domains/<domain>/` 唯一擁有 root facts、state machine、invariants 與 typed business rules；不得依賴 UI、FastAPI 或 concrete DB adapter。
- `subsystems/<domain>/` 擁有 Query／Preview／Apply、fresh-fact 驗證、outer Unit of Work 與跨 Domain coordination；不得重定義 Domain 規則。
- `api/`、`ui_react/`、`line/`、`infrastructure/`、`scripts/` 只負責 transport、schema、presentation、typed-port implementation 與 ops；不得旁路 writer、重算 root facts 或 hidden commit。
- 依賴由外往內。Query 唯讀；Preview 零寫入；Apply fresh-read／lock current owner facts。每個 mutation 只有一個 outer commit owner；外部副作用只經 committed inbox／outbox／durable job。
- UI／LINE 使用 bounded typed API／port；raw persistence dict、SQL row、provider payload 不得穿透 presentation。

## 3. Scope、授權與外部效果

修改只限 current task write set。不得順手重構、建立 generic framework／base class、增加無 current consumer 的 abstraction、做全 repository cleanup，或為同一問題疊加 retry／fallback／compatibility branch。

下列變更沒有最新人工明確 Authority 時停止施工並回報：

- owner、SSOT、root fact、state machine、cross-domain invariant；
- public contract／entry point；
- transaction／Unit of Work 邊界；
- schema／migration、destructive data change；
- external provider effect、production data、deployment、cutover／entry switch。

本機 code edit、focused test、build 與 read-only check 可依既有 Authority 執行。不得自行 stage、commit、push、建 PR、切 branch 或建 worktree，除非使用者明確要求。API／CLI／page 不得只因找不到 static caller 就刪除。

## 4. Concurrency 與 DB

owner／aggregate version 是 business mutation 的主要 optimistic concurrency control。`PreviewFingerprint` 只用於真正跨 request 的 `Preview → human Confirm → Apply`；新增 fingerprint／digest／snapshot token 前，必須指出具體 race、現有 version 為何不足及唯一 failure meaning。stale／version conflict 必須是 typed conflict，不得以 generic 500 或 blind retry 掩蓋。

DB 變更須 additive、可追溯，並區分 fresh bootstrap、preserve-data upgrade、fixture reset 與 production migration。一般任務不包含 `union_db`、production、reset、replacement、`--switch` 或 destructive operation Authority。DB 任務依 `10_Global_保留資料Migration與Cutover_Subsystem.md#9-agent-與開發者-db-變更執行門` 執行並回報 `PASS | BLOCKED | NOT_RUN`。

## 5. 驗證、文件與資料

- 從最低受影響邊界驗證：Static → Module → Subsystem → Domain → Global。只有實際 failure signal 或整合風險才擴大到 full suite、DB、Browser、stress、security 或 performance。
- snapshot／golden／validation dataset 不得為了過測試任意重寫；canonical change 造成 deterministic drift 時，只同步直接受影響的 current asset。
- `document/` 的 current Markdown 只放在 `document/架構重整/01_規格基線/`。新語意優先修改既有 owner spec；只有既有 owner 無法承接且 current acceptance 明確需要時才新增正式規格。
- 非 Markdown 附件只作 input、範例或 evidence；不得因存在而升格為 SSOT。
- 所有文字 strict UTF-8。secret、token、完整銀行帳號、raw webhook secret、credential 與不必要 PII 不得進 Git、log、command argument、UI 或 receipt。
- 交付前確認 scope、dirty paths、必要 tests、`git diff --check`、typed conflict、外部效果上限與敏感資訊；清楚標示 `PASS | FAILED | BLOCKED | NOT_RUN`，完成 current acceptance 後停止。
