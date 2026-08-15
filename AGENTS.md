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
5. `04_已完成與上線封存/` 是低頻歷史區，日常任務禁止預設或遞迴讀取。只有歷史追溯、incident／rollback、migration/cutover、舊 release 重現、稽核，或 current SSOT 明確引用 archive identity 時，才先精準搜尋 manifest，再讀命中的單一文件。
6. 最後才讀 live schema、API、Domain、Subsystem、repository、caller 與測試，確認規格和現況是否漂移。

思考程式、資料與流程時，先從實際 business scenario、操作者、根事實與不可破壞的不變量出發，以第一性原理拆解責任，不從既有頁面、資料表或函式形狀反推需求。

權威順序為：人工最新明確裁決 → 已人工確認的正式規格 → 可追溯的既有業務規格與欄位權威文件 → 其他架構文件 → live 現況證據。live code、schema、測試、log、receipt 或 UI 能運作都不代表規格已改變；不一致時必須標示 `live-drift`，不得用現況覆蓋業務語意。

`02_決策與退役執行記錄/` 必須依文件文字及 `declared_status` 解讀；draft、gap、decision-complete 或 inventory 不自動授權實作、部署、刪除或外部副作用。`03_追蹤清單與證據/` 只保存 active 盤點與證據，不構成規格或操作授權。`04_已完成與上線封存/` 的內容僅供歷史追溯，權威低於 current SSOT，也不能作為新 mutation 授權。

## 2. Global → Domain → Subsystem → Module 架構

- Global：`shared_kernel/` 與跨 Domain 契約，負責 actor、command envelope、version、fingerprint、idempotency、typed errors、BusinessClock、outer Unit of Work、receipt、outbox、migration、release 與跨域不變量；不得擁有 Domain 的金額、日期或狀態公式。
- Domain：`domains/<domain>/`，唯一擁有根事實、狀態機、不變量與 typed business rules；不得依賴 FastAPI、Streamlit 或 MySQL concrete adapter。
- Subsystem：`subsystems/<domain>/`，負責 Query／Preview／Apply、fresh-fact 驗證、交易編排、跨 Domain 協調、worker 與人工 recovery；不得重複定義 Domain 規則。
- Module／Adapter：`api/`、`ui/`、`line/`、`infrastructure/`、`scripts/`，只負責 transport、schema validation、顯示、typed-port 實作與維運入口；不得旁路寫入或重算 Domain 根事實。

依賴只能由外往內。Query 必須唯讀；Preview 必須零寫入；Apply 必須重新讀取並鎖定最新根事實後驗證。每個 mutation 只能有一個 outer Unit of Work 與 commit owner，repository／adapter 不得 hidden commit。外部副作用只能由已提交的 inbox、outbox 或 durable job 執行，外部失敗不得偽造成 Domain 成功或回滾已提交的 Domain transaction。

新增或變更 Subsystem 前，契約必須明確記錄 responsibility、non-goals、SSOT、根事實、衍生值、state machine、typed input／output／errors、transaction／lock boundary、idempotency、replay、stale、retry、timeout、conflict、partial failure、ports、outbox、異常警示、人工操作入口與 legacy exit。

Streamlit 是可替換的薄顯示層，只能呼叫後端 API 並顯示 typed result。UI API client 必須對應單一 bounded domain；跨 Domain endpoint 不得附加到既有 Domain client，共用認證只能透過明確的 shared transport composition。client 邊界必須將成功 payload 驗證為 Pydantic view 或其他 typed result，並把 transport／schema failure 轉成 typed client error；raw `dict` 不得穿透到 render function。

## 3. 架構與變更確認門檻

- production code、schema、migration 或 pytest 開始前，必須先具備已人工確認且涵蓋本次範圍的整體 `Global → Domain → Subsystem → Module` 架構。
- 變更 owner、SSOT、根事實、跨域不變量、public interface、entry point、external provider／side effect、交易邊界、破壞性 schema、production data、deployment 或 cutover 時，必須停止施工並取得新的人工確認。
- 超出既有 Work Package、write set 或驗收範圍時，不得自行擴張；先補規格或另立 decision／Work Package。
- 修改 API、資料模型、業務規則、migration、entry point 或外部副作用時，必須同步更新對應正式規格、decision／Work Package 與 evidence index；不得只改 code 和 tests。
- API、Streamlit page 或 CLI 即使找不到 static caller，也不能自行認定可刪。必須依 `19_Global_Entry_Point_Governance.md` 逐項裁決，並同步 entrypoint review queue、replacement、focused regression 與 validator。
- schema 依 `db/schema_parts/` → `db/schema.sql` → versioned release metadata 的路徑管理，必須 additive、可驗證且可追溯；不得自行套用到正式資料庫。
- 每次 schema、欄位、constraint、index、trigger、view 或 seed／backfill 變更，都必須同時交付開發者本機資料庫升級路徑；不得只讓 fresh bootstrap 或 disposable test DB 能建立成功。release 必須被 canonical migration chain／catalog 明確收錄，descriptor 必須涵蓋 altered parent columns 與所有 owned objects，且唯讀 migration preview 必須能列出該 release／artifact。未通過 preserve-data source → candidate → verify 驗證前，不得宣稱該 schema 變更完成。
- `start_local_development` 不負責套用 schema。保留既有資料使用 `scripts/launchers/update_local_database.bat`；捨棄資料並回到模板使用 `reset_DB.bat`，但 fixture 缺失時必須 fail closed。fresh bootstrap、preserve-data upgrade、fixture reset 與 production migration 是四條不同流程，不得互相替代或隱式串接。
- 本機 MySQL 的標準執行環境是 Docker `mysql_db` container；`mysql` 與 `mysqldump` 不要求存在於主機 `PATH`。當主機 client 缺失時，`scripts.update_local_database` 應自動偵測運行中的 `mysql_db`，或明確傳入 `--mysql-container mysql_db`。先確認 Docker daemon 可存取；不得因主機 `PATH` 缺少 client 而跳過 database engine gate、改用 mock，或直接操作 container 內 root 帳號。
- `scripts.update_local_database --apply` 是開發者本機的完整 replacement flow：candidate 驗證後會替換 configured source，不能作為純 engine gate。純 disposable candidate 驗證使用 `scripts.migrate_preserved_database_additive_schema --rehearsal --apply`／`--verify`，並明確傳入 `--mysql-container mysql_db`、source、candidate 與既有 plan／operation receipts；不得執行 `--switch`。若 source 的既有 owned object 為 `partial` 或 `drift`，runner 必須 fail closed，先處理該 baseline 再驗證新 release。
- DDL、system seed 與既有業務資料 backfill 必須在 release metadata 中分開聲明。任何 row migration 都要有 dry-run、影響筆數／fingerprint、unresolved review、replay 與 rollback evidence；不得把未宣告的資料轉換藏在 schema part，也不得因開發者本機需要升級而擴張成 production data migration 授權。

### 3.1 資料庫變更執行門

只要 diff、錯誤訊息或規格出現 table／column／constraint／index／trigger／view／seed／backfill 變更，依序執行下列 gate；不得跳到直接修改 SQL：

1. **Scope gate**：指出 business scenario、owner、正式規格及 active 且已核准的 Work Package。若只有已封存／completed 工作包，或 write set／acceptance 未涵蓋這次 migration 修復，先建立 proposed gap／Work Package 並取得人工核准；此時結果為 `BLOCKED_SCOPE`。
2. **Change inventory**：列出 `schema-only`、`system-seed`、`business-row-backfill`、`destructive` 四類變更及各自 source artifact、target object、資料效果、replay、rollback、unresolved policy。無法分類時結果為 `BLOCKED_CLASSIFICATION`。
3. **Static release gate**：確認 schema part、fresh-bootstrap assembly／manifest、canonical release chain、manifest hash／dependency、owned-object descriptor 與開發者操作文件全部互相引用。Runner 實際解析出的 latest release id 與 artifacts 必須包含本次 release；只因檔案存在於 `db/migration_releases/` 不算通過。
4. **Descriptor gate**：新表與 altered parent columns 都要驗證完整 column contract、indexes、foreign keys、checks、triggers 與 views；`absent／exact／partial／drift` 必須可機械區分，未知 partial／drift 固定 fail closed。
5. **Read-only plan gate**：`scripts/launchers/update_local_database.bat --dry-run` 只驗證 launcher wiring／依賴，不是 DB migration plan。真正的唯讀本機 plan 使用 `.venv\Scripts\python.exe -m scripts.update_local_database`；輸出必須含 latest release id、待套／續跑／exact artifacts 與 blocked reason，且不得寫 DB。
6. **Engine verification gate**：先跑 metadata／manifest／plan focused tests，再以 disposable DB 驗證 fresh bootstrap，最後以含上一支援版 schema 與代表性舊資料的 disposable source 驗證 dump → candidate → apply → verify。沒有真實 MySQL evidence 時只能標 `BLOCKED_ENGINE_EVIDENCE`，不得以 mock 或 compile 取代。
7. **Developer acceptance gate**：只在上述全部 PASS 後，才驗證本機 launcher 實際更新；必須保存 source backup、candidate／replacement receipts、舊資料 preservation、new object exactness、unresolved rows 與 rollback evidence。未經明確授權不得操作任何既有 `union_db`。

每次分析或交付必須輸出一張 gate 結果表，狀態只能使用 `PASS | BLOCKED | NOT_RUN`，並附證據路徑或命令。只要任一必要 gate 為 `BLOCKED`／`NOT_RUN`，總結固定為 `DB_CHANGE_NOT_READY`；不得使用「測試大致正常」或「fresh DB 可建立」宣稱完成。

## 4. 專案文件與檔案落點

新增檔案前先分類；同一資訊只能有一個 canonical owner，不得在 `document/`、根目錄與 Agent 暫存區建立競爭 SSOT。

| 類型 | 正式位置 | 規則 |
|---|---|---|
| Global／Domain 正式規格 | `document/架構重整/01_規格基線/` | 更新正式規格索引；人工確認前標明 draft／proposed，不得冒充 approved。 |
| 架構裁決、Work Package、gap、退役或執行記錄 | `document/架構重整/02_決策與退役執行記錄/` | 記錄 `doc_type`、`declared_status`、date、owner、scope、write set、acceptance 與 out-of-scope，並更新該目錄 `README.md`。 |
| 盤點、人工 review queue、正式 evidence／receipt | `document/架構重整/03_追蹤清單與證據/` | evidence 放其 `evidence/`，更新索引或 manifest；證據不等於授權。 |
| 已完成／已上線／已被取代的低頻歷史文件 | `document/架構重整/04_已完成與上線封存/` | 只封存不再 active 的 Work Package、superseded 舊規格與 closed release／receipt；現行正式規格即使已上線仍留在 `01`。封存前須通過 archive gate、更新 inbound links 與 manifest；Agent 日常不得全文載入。 |
| 功能提案與尚未核准的共享開發計畫 | `document/功能開發計畫/` | 一個 initiative 一份文件，必須標明狀態、owner、Domain、範圍、依賴、驗收條件與更新日期；若影響架構，核准後收斂到 `01`／`02`，不得保留雙 SSOT。 |
| 不改變業務／架構契約的通用技術 ADR | `document/架構重整/02_決策與退役執行記錄/` | 使用明確 `doc_type: architecture-decision`；若涉及 owner、SSOT、交易或部署裁決，同樣在此記錄完整 Work Package／裁決。 |
| 穩定的開發指南與通用 pattern | `AGENTS.md` 或 `document/架構重整/00_開發者與Agent導覽.md` | 不得在此放正式業務規格、共同代辦或驗收授權。 |
| pytest 測試程式 | `tests/` | `test_<business_behavior>.py`；新檔按 Domain／Subsystem／integration／global 邊界歸類，既有平鋪測試只在相關任務中逐步收斂。 |
| 測試 helper 與 pytest fixture code | `tests/support/`、`tests/conftest.py` | 不得把測試專用邏輯放進 production module 或 `scripts/`。 |
| 測試專用靜態資料 | `tests/fixtures/<domain>/` | 僅可放最小、去敏、可版本化的 deterministic input；禁止正式資料與個資。 |
| 跨層機器可讀驗收契約 | `validation/` | `scenarios/`、`expected/`、`fixtures/`、`receipts/` 等必須由 manifest／規格引用；canonical input 與可再生 output 必須分開，未經人工確認不得把現有產物升格為 SSOT。 |
| schema、release 與維運工具 | `db/schema_parts/`、`db/migration_releases/`、正式規格指定的 cutover release 目錄、`scripts/` | SQL、release metadata 與 operator entry 分開；script 必須有明確輸入、輸出、環境與安全邊界。 |
| 個人／Agent 暫存、探索、一次性輸出 | `scratch/<task-slug>/` | Git ignored；不得被 production、tests、正式規格或交付流程依賴。 |
| runtime／debug log | `logs/` 或 `scratch/<task-slug>/logs/` | Git ignored；需長期保存時提煉成去敏 receipt，不提交原始 log。 |

根目錄只放長期有效的 entry point、專案設定、共同索引與治理文件。禁止新增 root `tmp_*`、`.pytest_tmp_*`、`.codex_tmp_*`、`*.log`、cache、臨時簡報或 generated output。pytest 暫存使用唯一的 `--basetemp .pytest_tmp/<task-slug>` 或 OS temp，避免多 Agent 共用。既有 dirty／ignored 暫存物不得因本規範被自動刪除；清理仍需確認用途與授權。

## 5. 代辦與專案管理

- 團隊共同代辦必須可版本化、可追蹤且有唯一 owner。功能提案放 `document/功能開發計畫/`；已進入正式架構執行的工作放 `02_決策與退役執行記錄/` 的 Work Package／gap package。
- 每個共享代辦至少記錄：status、priority、owner、business scenario、Domain／Subsystem、scope、out-of-scope、dependencies、write set、acceptance、required tests、decision／evidence links、updated date。
- 狀態使用明確且有限的集合：`draft`、`proposed`、`approved`、`in-progress`、`blocked`、`completed`、`superseded`；`completed` 必須連結驗收證據，`blocked` 必須記錄阻塞條件與人工入口。
- 個人或 Agent 的即時 checklist 放 `scratch/<task-slug>/`，不提交且不構成團隊承諾。不得使用 root `task*.md`、`PROJECT_SPEC.md`、`implementation_plan.md`、checkpoint 或 code comment TODO 作為正式 backlog。
- production code 中不得留下沒有 owner／issue／Work Package 連結的 `TODO`、`FIXME` 或暫時繞過；無法在本任務完成時，回寫正式代辦並使程式 fail closed。
- 工作完成後先在原代辦更新 `completed`、evidence／index 與 release 結果，不另建「完成版」複本。符合 archive gate 後可把不再 active 的 Work Package／舊版本文件移至 `04_已完成與上線封存/`；被取代文件標示 `superseded` 並連結 successor，不靜默覆寫歷史裁決。
- 「已實作」不等於「可封存」；仍約束 current production 的正式規格永遠留在 `01_規格基線/`。只有 current successor 已完整承接語意，且舊文件不含 active blocker、操作入口或 rollback 責任時，才可封存舊版本。
- 封存不是依檔名或 status 自動搬移。必須確認 completion／deployment receipt、release identity（如適用）、successor、inbound links、content digest、restore triggers，並更新 `04_已完成與上線封存/archive_manifest.json`。沒有唯一判定時留在原位並進人工 review queue。
- active 索引只保留 current／in-progress／blocked／awaiting-execution 文件與必要的一行 archive pointer；不得把 archive 全目錄或完整 manifest 注入一般 Agent 上下文。

## 6. 分層實作與驗證

- 架構完整確認後，才可依互不重疊的 Source／write set 平行撰寫 production code 與測試。
- Module 驗證局部 input、output、invariant、exception 與 dependency。
- Subsystem 驗證 Module 編排、資料形狀、狀態機、交易、replay、partial failure、stale 與 conflict。
- Domain 驗證從根事實到最終結果的端到端運作。
- Global 驗證跨 Domain 不變量、entry point、migration、release 與外部副作用主流程。
- schema／migration 變更至少驗證兩條路徑：空白 disposable DB 的 fresh bootstrap，以及含舊版資料的 preserve-data candidate upgrade。後者必須確認舊表 row count、primary keys、原欄位 projection 與 source fingerprint 不變，新欄位／objects exact，且 partial／drift fail closed。
- 測試失敗時，以失敗所屬層級作為整體修正單位；不得只修單一 assertion 而破壞同層契約或跨層不變量。
- 測試資料、candidate、fixture、正式資料庫與外部服務必須明確隔離。任何 snapshot、golden artifact 或 validation dataset 都視為受保護測試資產，除非使用者明確指定，不得刪除、重產或套用至正式資料。
- Python 測試使用專案 `.venv\Scripts\python.exe -m pytest`，指定有限 timeout；先跑受影響 Module，再依 Subsystem、Domain、Global 逐層擴大，必要時使用 `-W error`。
- 每個 production、script 或 test 的直接第三方 import，都必須在 `pyproject.toml` 的 `dependencies` 或適當 dependency group 明確聲明；不得依賴 transitive package 恰好存在。變更相依後同步更新 `uv.lock`。

## 7. Dirty worktree、Git 與協作

- 既有未提交、未追蹤與 ignored 修改都視為使用者成果。不得 reset、clean、stash、切換分支、建立 worktree、覆蓋、搬移或刪除無關 dirty paths；可使用已由人員或協調者明確提供的獨立 worktree，但不得自行建立或切換。
- 修改範圍只限本次任務直接需要的檔案；遇到重疊修改時，先辨認來源、差異與語意再動手。
- 不得自行 stage、commit、push、建立 PR 或操作遠端資源，除非使用者明確要求。
- 只有兩個以上互不依賴、寫入範圍不重疊且交接成本合理的工作才平行派工。子代理不得擴大範圍、修改共享檔案或自行 commit；主代理負責整合與最終自我檢查。
- 所有文字檔使用 strict UTF-8，預設無 BOM；不得用 replacement 或 ignore 隱藏解碼錯誤。
- secret、token、internal key、完整銀行帳號、raw webhook secret 與完整個資不得寫入 Git、規格、log、command argument、UI 或 receipt。證據只保留驗收所需的最小去敏內容。

### 多人協作與合併裁決

- 任務以人可讀的 Work Package／issue／標題，加上 owner、scope、write set 與 base ref 識別。commit SHA 可作為證據，但不得要求或使用內容 hash／fingerprint 作為任務身分、worktree 或 branch 名稱、協作鎖、進度紀錄或衝突裁決依據。
- hash 只用於既有契約明確要求的不可變、可重現 artifact 完整性，例如 migration SQL、release／descriptor metadata、generated validation release、已核准 snapshot／golden artifact 與其 receipt。hash 不代表 owner、業務授權、任務狀態，也不能決定哪一側變更應保留。
- 平行工作開始前，協調者必須記錄各 lane 的 owner、base ref、scope、out-of-scope、exact write set、acceptance 與 shared hot spots。`AGENTS.md`、共同 README／index、catalog、manifest、release chain、lockfile、generated authority 與共享 fixture 在同一協作批次只能有一位 integration writer；其他作者只交付自己的內容檔及精確 index delta，不直接競寫 hot spot。
- handoff、配號與合併前必須比較目前 integration target 與原 base ref，並重查 write set、shared hot spots 及 canonical catalog 自開工後的變更。發現 base drift 時先重讀受影響規格與 diff、重做衝突盤點；不得沿用舊的 next number、index order、manifest position 或驗收假設。
- 合併或共同編輯前，先建立最小衝突盤點：path、各方意圖與 owner、語意分類、建議處置（`keep both`、`ours`、`theirs`、`successor`、`defer`）。非純文字格式衝突不得自行定案；須由相關 owner 或人工確認處置。
- 新增帶 ordinal、正式規格編號、Work Package ID、schema part ordinal 或 release ID 的 artifact 時，必須先確認其 namespace 與 canonical catalog owner。平行 lane 一律先使用人可讀、無整數占位的 provisional identity，例如 `PROV-YYYYMMDD-<owner>-<topic>`；不得自行以「目前最大值 + 1」、README 的 next number 或另一 namespace 的空號宣稱 canonical identity，也不得先修改 shared index。
- canonical ID 只由 integration writer 在最新 integration target 上 late-bind：先精準檢查 active catalog、相關 archive manifest、release chain 及未追蹤檔案，再於同一整合變更中完成配號、檔名、frontmatter、inbound links、catalog／index／manifest。README 或索引記載的目前最大值只能作觀察提示，不是 reservation；catalog 不完整、owner 不明或 base drift 未解決時維持 provisional 並 fail closed。
- provisional／draft 且尚未被核准、發布、套用或成為 inbound reference 的 identity 可由 integration writer 改名；已進入 canonical catalog、已被引用、已核准、已發布或已套用的 identity 不得為解決碰撞而改號或覆寫。不同業務 lane 保留並分配不同 canonical ID；同一語意須比較契約與驗收證據後指定 successor／superseded／defer，不得以 Git 的 `ours`／`theirs` 取代語意裁決。
- release ID、schema part ordinal 與文件／Work Package 編號是不同 namespace，不互相借號。已發布或已套用的 migration SQL、release／descriptor metadata 與 digest bytes 永遠不可改號、覆寫或重算；碰撞或修正只能建立有明確 dependency 的 successor artifact，並重跑資料庫變更執行門。
- 合併協調者只在各 lane 內容 freeze 且語意裁決完成後，一次整合 shared catalog、index 與 manifest order。每次協調完成都要記錄 provisional → canonical mapping、保留、取代、延後項目、仍待驗證的 gate 及最新 base ref。

## 8. 交付前檢查

1. 變更是否對應一個明確 business scenario、Domain／Subsystem 與已核准範圍？
2. owner、SSOT、根事實、衍生值、交易與外部副作用邊界是否仍清楚？
3. 新檔案是否放在本規範指定位置，且沒有建立雙 SSOT 或 root 暫存？
4. 規格、代辦、code、tests、validation contract、receipt 與索引是否互相可追溯？
5. 是否保護所有既有 dirty paths，且每一行 diff 都屬於本任務？
6. 若涉及平行工作或新 identity，是否完成 base-drift／namespace／collision 檢查，由唯一 integration writer 配號並更新 shared hot spots？
7. 是否完成正確層級的測試、`git diff --check`、UTF-8 與敏感資訊檢查？
8. 是否明確揭露未完成、未授權、live-drift、skip、風險與需要人工處理的項目？
9. 若有 DB 變更，canonical release chain、owned-object descriptor、fresh bootstrap、preserve-data dry-run／candidate 驗證與開發者操作文件是否同步完成？

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- Agents and operators must first run from the project root, then invoke the project-local wrapper `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\graphify.ps1`, followed directly by the Graphify subcommand and arguments; do not insert `--` and do not use bare `graphify`. This process-scoped policy option does not change user or system policy, and the wrapper resolves only `.venv\Scripts\graphify.exe` without changing `PATH`.
- For codebase questions, first run `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\graphify.ps1 query "<question>"` when graphify-out/graph.json exists. Use `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\graphify.ps1 path "<A>" "<B>"` for relationships and `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\graphify.ps1 explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If `graphify-out/graph.json` is missing or stale, or the project wrapper／`.venv` executable is unavailable, report that state and use authorised source reads. Do not install Graphify, use bare `graphify`, or substitute an inline BFS/NetworkX traversal or any other fallback graph query.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- Do not run `graphify update` for the frozen-base/freshness workflow. Only an explicitly authorised full Base build may refresh its graph evidence.
