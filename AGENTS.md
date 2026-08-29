# Workspace Agent Rules

本檔案是本專案所有 AI Agent 與自動化程式修改工作的根層規範。所有 Agent 進入工作區後都必須先讀本檔，再讀任務範圍內的正式規格與相鄰文件。

`.agents/AGENTS.md` 是可選的個人 overlay；存在時才以 strict UTF-8 完整讀取，只能補充互動、
計畫與 Git 偏好，不得覆蓋本檔、正式規格或人工裁決，也不得合併回共享規範。缺檔時正常繼續；
存在但無法 strict UTF-8 解碼時必須告知使用者且不得套用。同一任務內若檔案內容及 HEAD 均未
改變，不必重複載入；切換分支、更新 HEAD 或檔案變更後必須重讀。

本檔必須保持跨開發者與跨機器可攜：不得要求個人帳號、絕對本機路徑、私人 skill／plugin、
個人 `.env` 或 Git ignored 檔案才能執行共享工作。個人工具可自行使用，但不能成為專案 gate、
驗收證據的唯一來源或其他協作者的必要依賴。

`.agents/`、`history/git_PR.md`、`history/git_PR.md.example` 及其他已被 Git 忽略的個人檔案屬
使用者本機成果。不得 stage、commit、push、覆蓋、搬移、清理或刪除；fetch、pull、merge 與
分支操作也必須保留這些檔案。

本專案不使用 ADAD Task、Checkpoint、Source Lock、system map gate 或 ADAD 工具。legacy `system_map*.md`、`system_map*.yaml`、`scripts_map.md`、`checkpoints/` 與 `history/` 僅供歷史追溯，不是 SSOT、代辦系統、授權或實作 gate。

## 1. 開工順序與權威來源

每個任務依下列順序執行：

1. 記錄並保留 branch、HEAD、`git status --short`，再讀本檔與任務相關檔案。若存在 dirty paths，先保留並避免 reset/clean/stash 類操作。
2. 讀 `README.md` 與 `document/架構重整/00_開發者與Agent導覽.md`。
3. 讀 `document/架構重整/01_規格基線/00_Global_共同契約.md`、`15_正式規格索引與裁決總表.md`、對應 Domain 規格及最新補充裁決；目前正式收斂範圍為 `15`～`24`，以 `15` 為入口。
4. 只讀任務直接對應、仍 active 的 `02_決策與退役執行記錄/` Work Package／decision，以及 `03_追蹤清單與證據/` inventory／evidence；不要整目錄載入。
5. `04_已完成與上線封存/README.md` 是低頻歷史文件的 Git 復原入口。只有歷史追溯、incident／rollback、migration/cutover、舊 release 重現或稽核時，才從指定 Git commit 精準取回單一文件；日常任務不得還原或載入整批歷史。
6. 最後才讀 live schema、API、Domain、Subsystem、repository、caller 與測試，確認規格和現況是否漂移。

思考程式、資料與流程時，先從實際 business scenario、操作者、根事實與不可破壞的不變量出發，以第一性原理拆解責任，不從既有頁面、資料表或函式形狀反推需求。

權威順序為：人工最新明確裁決 → 已人工確認的正式規格 → 可追溯的既有業務規格與欄位權威文件 → 其他架構文件 → live 現況證據。live code、schema、測試、log、receipt 或 UI 能運作都不代表規格已改變；不一致時必須標示 `live-drift`，不得用現況覆蓋業務語意。

`02_決策與退役執行記錄/` 必須依文件文字及 `declared_status` 解讀；draft、gap、decision-complete 或 inventory 不自動授權實作、部署、刪除或外部副作用。`03_追蹤清單與證據/` 只保存 active 盤點與證據，不構成規格或操作授權。`04_已完成與上線封存/` 的內容僅供歷史追溯，權威低於 current SSOT，也不能作為新 mutation 授權。

任務開始時依 [Agent 任務分級與交付規範](document/架構重整/00_Agent任務分級與交付規範.md)
判斷 T0–T3、最小 durable artifacts 與驗證範圍。既有契約已涵蓋的 T1／T2 實作直接重用 current spec；
不得要求每個 slice 另建 spec、Work Package 或 receipt。只有契約缺口或 T3 邊界變更才回規格層；
Current register 只保存 owner、status、blocker 與下一個 material gate。

## 2. Global → Domain → Subsystem → Module 架構

- Global：`shared_kernel/` 與跨 Domain 契約，負責 actor、command envelope、version、fingerprint、idempotency、typed errors、BusinessClock、outer Unit of Work、receipt、outbox、migration、release 與跨域不變量；不得擁有 Domain 的金額、日期或狀態公式。
- Domain：`domains/<domain>/`，唯一擁有根事實、狀態機、不變量與 typed business rules；不得依賴 FastAPI、Streamlit 或 MySQL concrete adapter。
- Subsystem：`subsystems/<domain>/`，負責 Query／Preview／Apply、fresh-fact 驗證、交易編排、跨 Domain 協調、worker 與人工 recovery；不得重複定義 Domain 規則。
- Module／Adapter：`api/`、`ui/`、`line/`、`infrastructure/`、`scripts/`，只負責 transport、schema validation、顯示、typed-port 實作與維運入口；不得旁路寫入或重算 Domain 根事實。

依賴只能由外往內。Query 必須唯讀；Preview 必須零寫入；Apply 必須重新讀取並鎖定最新根事實後驗證。每個 mutation 只能有一個 outer Unit of Work 與 commit owner，repository／adapter 不得 hidden commit。外部副作用只能由已提交的 inbox、outbox 或 durable job 執行，外部失敗不得偽造成 Domain 成功或回滾已提交的 Domain transaction。

新增或變更 Subsystem 前，契約必須明確記錄 responsibility、non-goals、SSOT、根事實、衍生值、state machine、typed input／output／errors、transaction／lock boundary、idempotency、replay、stale、retry、timeout、conflict、partial failure、ports、outbox、異常警示、人工操作入口與 legacy exit。

Streamlit 是可替換的薄顯示層，只能呼叫後端 API 並顯示 typed result。UI API client 必須對應單一 bounded domain；跨 Domain endpoint 不得附加到既有 Domain client，共用認證只能透過明確的 shared transport composition。client 邊界必須將成功 payload 驗證為 Pydantic view 或其他 typed result，並把 transport／schema failure 轉成 typed client error；raw `dict` 不得穿透到 render function。

## 3. 架構與變更確認門檻

- production code、schema、migration 或 pytest 開始前，必須確認本次行為已被 current `Global → Domain → Subsystem → Module` 架構與正式規格涵蓋；依既有契約實作不需要重建或重新確認整體架構。
- 變更 owner、SSOT、根事實、跨域不變量、public interface、entry point、external provider／side effect、交易邊界、破壞性 schema、production data、deployment 或 cutover 時，必須停止施工並取得新的人工確認。
- 超出 current spec／Authority／write set 或驗收範圍時不得自行擴張；只有 observable contract 缺口才補 current spec，只有 material execution 確有跨步驟 consumer 時才建立或更新一份 living Work Package。
- 修改 API、資料模型、業務規則、migration、entry point 或外部副作用時，依 T0–T3 更新實際擁有該契約的 canonical artifact；不得機械要求 spec、decision、Work Package 與 evidence index 全部同時新增。
- API、Streamlit page 或 CLI 即使找不到 static caller，也不能自行認定可刪。必須依 `19_Global_Entry_Point_Governance.md` 逐項裁決，並同步 entrypoint review queue、replacement、focused regression 與 validator。
- schema 依 `db/schema_parts/` → `db/schema.sql` → versioned release metadata 的路徑管理，必須 additive、可驗證且可追溯；不得自行套用到正式資料庫。
- schema／migration 必須同時支援 fresh bootstrap 與 preserve-data source → candidate → verify；release chain、
  descriptor、read-only plan 與 developer upgrade path 缺一不可。DDL、system seed 與 row backfill 分開聲明。
- fresh bootstrap、preserve-data upgrade、fixture reset 與 production migration 是四條不同流程；
  `union_db`、production、reset、replacement、`--switch` 與未核准 DDL／backfill 均不得由一般驗收推導授權。

### 3.1 DB 變更路由

DB 變更的七個 gate、`PASS | BLOCKED | NOT_RUN` 狀態、`DB_CHANGE_NOT_READY` 結論、allowlisted
`lu_test_*` 受控驗收與禁止事項，只由
[`10_Global_保留資料Migration與Cutover_Subsystem.md`](document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md#9-agent-與開發者-db-變更執行門)
完整定義。本檔不重複操作細節。任何 schema／migration 變更必須讀該節並輸出 gate table；一般
API／UI／Domain 驗收只有在實際使用 DB 時才套用受控驗收規則。

## 4. 專案文件與檔案落點

同一資訊只能有一個owner：current規格放`01_規格基線/`；active decision／Work Package／gap放`02_決策與退役執行記錄/`；active inventory、final receipt與review queue放`03_追蹤清單與證據/`；不再active的歷史放`04_已完成與上線封存/`。測試放`tests/`，fixture放`tests/fixtures/`，跨層驗收契約放`validation/`，schema／release放`db/`，一次性輸出放ignored `scratch/<task-slug>/`。

證據採final receipt優先：原始stdout／stderr、完整HTTP dump、重跑journal、intermediate plan、重複candidate receipt及cache，在final receipt完成且沒有rollback／稽核依賴後應刪除，不得長期堆在`03`。Migration release、source backup、rollback receipt、不可變artifact與current incident evidence保留。刪除前精準搜尋inbound references；有current引用或唯一性不明時不刪。

## 5. 代辦與專案管理

- 共享代辦須有status、owner、scenario、scope、dependencies、write set、acceptance、tests與evidence；狀態限`draft | proposed | approved | in-progress | blocked | completed | superseded`。
- active索引只列current／approved／in-progress／blocked／awaiting-execution。completed／superseded在確認successor、inbound links、rollback責任與final receipt後移出；不另建「完成版」複本。
- 個人checklist只放ignored `scratch/`；production不得留下無owner／Work Package連結的TODO／FIXME。

## 6. 分層實作與驗證

- 驗證順序為Module → Subsystem → Domain → Global；先focused，最後才full suite。失敗以所屬層級修正，不只改單一assertion。
- Python使用`.venv\Scripts\python.exe -m pytest`、有限timeout與唯一`--basetemp .pytest_tmp/<task-slug>`。
- snapshot／golden／validation dataset視為受保護資產。直接第三方import須在`pyproject.toml`聲明並同步`uv.lock`。

## 7. Dirty worktree、Git 與協作

- 既有未提交、未追蹤與 ignored 修改都視為使用者成果。不得 reset、clean、stash、切換分支、建立 worktree、覆蓋、搬移或刪除無關 dirty paths；可使用已由人員或協調者明確提供的獨立 worktree，但不得自行建立或切換。
- 修改範圍只限本次任務直接需要的檔案；遇到重疊修改時，先辨認來源、差異與語意再動手。
- 不得自行 stage、commit、push、建立 PR 或操作遠端資源，除非使用者明確要求。
- 只有兩個以上互不依賴、寫入範圍不重疊且交接成本合理的工作才平行派工。子代理不得擴大範圍、修改共享檔案或自行 commit；主代理負責整合與最終自我檢查。
- 所有文字檔使用 strict UTF-8，預設無 BOM；不得用 replacement 或 ignore 隱藏解碼錯誤。
- secret、token、internal key、完整銀行帳號、raw webhook secret 與完整個資不得寫入 Git、規格、log、command argument、UI 或 receipt。證據只保留驗收所需的最小去敏內容。

### 多人協作與合併裁決

- 平行lane先凍結owner、base、scope、write set、acceptance與shared hot spots；共同README／index／catalog／manifest／release chain／lockfile同批次只有一位integration writer。
- 合併前重查base drift並列path、雙方意圖與`keep both | ours | theirs | successor | defer`；不得用Git側別代替語意裁決。
- 新identity先用`PROV-YYYYMMDD-<owner>-<topic>`，canonical ID由integration writer在fresh catalog上late-bind。已發布／已套用release與hash-locked artifact不可改號、覆寫或重算。

## 8. 交付前檢查

確認scope／owner／SSOT／交易與副作用邊界、dirty paths、文件與code可追溯、正確層級測試、`git diff --check`、strict UTF-8、敏感資訊及所有未完成／未授權／live-drift。DB變更另確認release chain、descriptor、fresh、preserve-data與developer acceptance。
