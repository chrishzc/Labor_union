# Workspace Agent Rules

本檔是本 repository 的根層 Agent 規範。Agent 先讀本檔，再讀任務直接相關的 current 正式規格與 evidence；不要把歷史文件、live code 或測試結果反向升格為業務 Authority。

`.agents/AGENTS.md` 是可選個人 overlay，只能補充互動、計畫與 Git 偏好，不得覆蓋本檔、正式規格或人工裁決。共享工作不得依賴個人帳號、絕對本機路徑、私人 plugin、個人 `.env` 或 ignored 檔案。既有 ignored／untracked／dirty 使用者成果不得 reset、clean、stash、覆蓋、搬移或刪除。

legacy ADAD task、checkpoint、system map、history 只供追溯，不是 SSOT、代辦、授權或實作 gate。

## 1. 開工與權威

1. 先記錄 branch、HEAD、`git status --short`，保留所有 dirty paths。
2. 讀 `README.md`、`document/架構重整/00_開發者與Agent導覽.md`。
3. 讀 `document/架構重整/01_規格基線/00_Global_共同契約.md`、`15_正式規格索引與裁決總表.md`、對應 owning Domain／Subsystem current spec 與最新人工裁決。以 `15` 判斷 current 文件，不假定規格編號上限。
4. 只讀本任務直接對應且仍 active 的 `02_決策與退役執行記錄/` 與必要 `03_追蹤清單與證據/`；不要整目錄載入。
5. 歷史、rollback、incident、舊 release 重現或稽核才依 `04_已完成與上線封存/README.md` 精準取回單一歷史文件。
6. 最後讀 live schema／code／caller／tests，確認 `live-drift`；live 現況不能覆蓋正式語意。

權威順序：最新人工明確裁決 → current 正式規格 → 可追溯業務／欄位權威 → 其他架構文件 → live evidence。

任務開始依 [00_Agent任務分級與交付規範.md](document/架構重整/00_Agent任務分級與交付規範.md) 判斷 T0–T3、最小 artifacts 與驗證範圍。T1／T2 直接重用 current spec；不得要求每個 slice 新建 spec、Work Package 或 receipt。

## 2. 架構邊界

- Global／`shared_kernel/`：跨 Domain 技術契約與不變量；不得擁有業務公式。
- Domain／`domains/<domain>/`：唯一擁有 root facts、state machine、invariants 與 typed business rules；不得依賴 UI／FastAPI／concrete DB adapter。
- Subsystem／`subsystems/<domain>/`：Query／Preview／Apply、fresh-fact 驗證、UoW 編排、跨 Domain coordination、worker／recovery；不得重定義 Domain 規則。
- Module／Adapter／`api/`、`ui/`、`line/`、`infrastructure/`、`scripts/`：transport、schema、presentation、typed-port implementation、ops；不得旁路 writer 或重算 root facts。

依賴由外往內。Query 唯讀；Preview 零寫入；Apply fresh-read／lock current owner facts。每個 mutation 只有一個 outer Unit of Work／commit owner，repository／adapter 不得 hidden commit。外部副作用只經 committed inbox／outbox／durable job。

規格只需記錄會影響 observable contract 或 failure model 的內容；不得為了 checklist 強迫每個 Subsystem 重複抄寫所有 ports、retry、timeout、legacy exit 等欄位。既有 owner contract 足夠時直接實作。

UI／LINE 必須使用 bounded typed API／port；raw persistence dict、SQL row、provider payload 不得穿透 presentation。共用 authentication 可以 shared transport composition，不得藉此合併 business owner。

## 3. 何時必須人工確認

下列變更停止施工並取得新的人工 Authority：

- owner、SSOT、root fact、state machine、cross-domain invariant；
- public contract／entry point；
- transaction／Unit of Work 邊界；
- 未授權 schema／migration、destructive data change；
- external provider effect、production data、deployment、cutover／entry switch。

依既有 Authority 的本機 code、focused test、build、read-only check 與已核准 `lu_test_*` gate 不需逐 slice 再請示。

超出 current acceptance／write set 不得順手重構。只有真正 `SPEC_GAP` 回 current spec；只有 material handoff／effect ceiling 確有需要才維護一份 living Work Package。不得為單一案例建立 generic framework、base class 或未有 current consumers 的 abstraction。

API／CLI／page 即使找不到 static caller 也不能自行刪除；依 current entry-point governance 做 bounded replacement／retirement。

## 4. Concurrency／Fingerprint 簡化

- owner／aggregate version 是 business mutation 的主要 optimistic concurrency control。
- `PreviewFingerprint` 只用在真正跨 request 的 `Preview → human Confirm → Apply`，且 candidate 可能因外部 current-fact change 失效的邊界。
- idempotency fingerprint 只證明 same key + same canonical command；content digest 只證明 immutable artifact／source bytes。
- 同一 outer command／batch coordinator 的合法前序 mutation 是 expected state advance，不得讓後序內部 step 因舊 preview fingerprint產生 self-induced stale。
- snapshot token 只有在無單一合法 owner version、且必須證明多 root authoritative snapshot 時才使用。
- 新增 fingerprint／digest／snapshot token 前必須說明它保護的具體 race、現有 version 為何不足，以及唯一 failure meaning；否則不得新增。
- stale／version conflict 是 closed typed conflict，不能以 generic exception／500 表示；不得用 blind retry 掩蓋 false-stale。
- 不做全 repository fingerprint cleanup。只有 current slice 已證明 false-stale、duplicate protection 或 deterministic drift 時做最小修正。

更完整契約以 `00_Global_共同契約.md` 的 concurrency／fingerprint section 為準。

## 5. DB 變更

schema／migration 仍須 additive、可追溯，並區分 fresh bootstrap、preserve-data upgrade、fixture reset 與 production migration。一般驗收不能推導 `union_db`、production、reset、replacement、`--switch` 或 destructive operation Authority。

DB 變更的 gate、`PASS | BLOCKED | NOT_RUN`、`DB_CHANGE_NOT_READY`、allowlisted `lu_test_*` 與禁止事項，只由 [10_Global_保留資料Migration與Cutover_Subsystem.md#9-agent-與開發者-db-變更執行門](document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md#9-agent-與開發者-db-變更執行門) 定義；本檔不複製操作細節。

## 6. 文件與 artifacts

同一事實只保留一個 owner：

- `01_規格基線/`：current contract／SSOT；
- `02_決策與退役執行記錄/`：active decision／gap／必要 Work Package；
- `03_追蹤清單與證據/`：current inventory／必要 final receipt／review queue；
- `04_已完成與上線封存/`：歷史；
- `scratch/<task-slug>/`：intermediate plan、stdout、HTTP dump、candidate evidence 等一次性成果。

Current register 只保存 owner、status、blocker、next material gate，不重抄完整 spec、commands、logs。Final receipt 只在 release／migration／rollback／incident／external effect／audit 或明確 consumer 需要時 tracked。

合法 canonical change 若使仍在使用的 tests、validator、current manifest／inventory 產生 deterministic drift，可在同一 bounded slice 做最小同步；不得改 business oracle。Historical receipt、published/applied immutable artifact、hash-bound historical evidence 與 archive 不改寫。

## 7. 驗證、Git 與協作

- 驗證從最低受影響邊界開始：Static → Module → Subsystem → Domain → Global；只有實際 failure model／整合風險需要才擴大到 full suite、DB、Browser、stress、security 或 performance。
- snapshot／golden／validation dataset 是受保護資產；不得為了過測試任意重寫。
- 修改只限 current task write set。不得自行 stage、commit、push、建 PR、切 branch 或建 worktree，除非使用者明確要求。
- 平行工作只在 2 個以上互不依賴、write set 不重疊且 shared hot spots 可隔離時使用；共同 index／manifest／release chain／lockfile 同批只有一名 integration writer。
- 所有文字 strict UTF-8。secret、token、完整銀行帳號、raw webhook secret、credential 與不必要 PII 不得進 Git、log、command argument、UI 或 receipt。

## 8. 交付前

確認 scope／owner／SSOT／UoW／external-effect ceiling、dirty paths、必要 tests、typed conflict handling、`git diff --check`、strict UTF-8、敏感資訊，以及所有 `blocked | not_run | live-drift`。DB 變更另依 canonical DB gate 檢查 release／descriptor／fresh／preserve-data／developer acceptance。
