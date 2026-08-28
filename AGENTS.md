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
- 本機 MySQL 的標準執行環境是 Docker `mysql_db` container；`mysql` 與 `mysqldump` 不要求存在於主機 `PATH`。當主機 client 缺失時，`scripts.update_local_database` 應自動偵測運行中的 `mysql_db`，或明確傳入 `--mysql-container mysql_db`。先確認 Docker daemon 可存取；不得因主機 `PATH` 缺少 client 而跳過 database engine gate或改用 mock。依 2026-08-21 人工裁決，本機 development／validation 的 allowlist `lu_test_*` DB 可使用目前已設定的帳號（包括 root）執行已核准 Work Package 的受控驗收；root 不得因此用於 `union_db`、production target、未核准 schema／migration、reset、replacement 或 `--switch`。
- `scripts.update_local_database --apply` 是開發者本機的完整 replacement flow：candidate 驗證後會替換 configured source，不能作為純 engine gate。純 disposable candidate 驗證使用 `scripts.migrate_preserved_database_additive_schema --rehearsal --apply`／`--verify`，並明確傳入 `--mysql-container mysql_db`、source、candidate 與既有 plan／operation receipts；不得執行 `--switch`。若 source 的既有 owned object 為 `partial` 或 `drift`，runner 必須 fail closed，先處理該 baseline 再驗證新 release。
- DDL、system seed 與既有業務資料 backfill 必須在 release metadata 中分開聲明。任何 row migration 都要有 dry-run、影響筆數／fingerprint、unresolved review、replay 與 rollback evidence；不得把未宣告的資料轉換藏在 schema part，也不得因開發者本機需要升級而擴張成 production data migration 授權。

### 3.1 資料庫變更執行門

只要 diff、錯誤訊息或規格出現 table／column／constraint／index／trigger／view／seed／backfill 變更，依序執行下列 gate；不得跳到直接修改 SQL：

1. **Scope gate**：指出 business scenario、owner、正式規格及 active 且已核准的 Work Package。若只有已封存／completed 工作包，或 write set／acceptance 未涵蓋這次 migration 修復，先建立 proposed gap／Work Package 並取得人工核准；此時結果為 `BLOCKED_SCOPE`。
2. **Change inventory**：列出 `schema-only`、`system-seed`、`business-row-backfill`、`destructive` 四類變更及各自 source artifact、target object、資料效果、replay、rollback、unresolved policy。無法分類時結果為 `BLOCKED_CLASSIFICATION`。
3. **Static release gate**：確認 schema part、fresh-bootstrap assembly／manifest、canonical release chain、manifest hash／dependency、owned-object descriptor 與開發者操作文件全部互相引用。Runner 實際解析出的 latest release id 與 artifacts 必須包含本次 release；只因檔案存在於 `db/migration_releases/` 不算通過。
4. **Descriptor gate**：新表與 altered parent columns 都要驗證完整 column contract、indexes、foreign keys、checks、triggers 與 views；`absent／exact／partial／drift` 必須可機械區分，未知 partial／drift 固定 fail closed。
5. **Read-only plan gate**：`scripts/launchers/update_local_database.bat --dry-run` 只驗證 launcher wiring／依賴，不是 DB migration plan。真正的唯讀本機 plan 使用 `.venv\Scripts\python.exe -m scripts.update_local_database`；輸出必須含 latest release id、待套／續跑／exact artifacts 與 blocked reason，且不得寫 DB。
6. **Engine verification gate**：schema／migration 變更仍須先跑 metadata／manifest／plan focused tests，再以 disposable DB 驗證 fresh bootstrap，最後以含上一支援版 schema 與代表性舊資料的 disposable source 驗證 dump → candidate → apply → verify。純 API／UI／Domain mutation 驗收不再強制建立 disposable DB；可依 3.2 在既有 allowlist 開發測試 DB 取得真實 MySQL evidence。沒有任何真實 MySQL evidence 時只能標 `BLOCKED_ENGINE_EVIDENCE`，不得以 mock 或 compile 取代。
7. **Developer acceptance gate**：只在上述全部 PASS 後，才驗證本機 launcher 實際更新；必須保存 source backup、candidate／replacement receipts、舊資料 preservation、new object exactness、unresolved rows 與 rollback evidence。未經明確授權不得操作任何既有 `union_db`。

每次分析或交付必須輸出一張 gate 結果表，狀態只能使用 `PASS | BLOCKED | NOT_RUN`，並附證據路徑或命令。只要任一必要 gate 為 `BLOCKED`／`NOT_RUN`，總結固定為 `DB_CHANGE_NOT_READY`；不得使用「測試大致正常」或「fresh DB 可建立」宣稱完成。

### 3.2 既有開發測試 DB 的受控驗收裁決

2026-08-21 人工已撤銷「既有 DB 只能 GET」與「所有 DB 驗收必須使用 non-root disposable DB」兩項
blanket restriction。這項 current 裁決適用於 Phase 3～6 及後續本機 API／UI／Domain 驗收，並取代 active
文件中僅因上述 blanket restriction 而留下的舊 blocker；歷史 receipt 保留當時 `NOT_RUN` 事實。

- 允許目標：`APP_ENV=development` 或等價 validation profile，且資料庫名稱通過 `lu_test_*` allowlist；每次
  執行前都要回讀 environment、host、database 與 credential class，target 不符即 fail closed。
- 允許帳號：使用目前開發環境已設定的 credential，包括 root；不再要求先建立 non-root 帳號。
- 允許操作：已核准 Work Package 明列的 Query／Preview／Apply、API、browser、worker replay 及受控測試資料
  建立／修改／清理。每次 mutation 要使用唯一 scenario identity，先盤點目標 rows，只修改本次 owned rows，
  保存 receipt／before-after readback，並以 scoped cleanup 或明確保留策略結束；不得清理不屬於本次的資料。
- disposable DB 改為選配隔離工具，不再是一般 mutation／browser gate 的必要條件；若現有資料不足，可依
  Work Package 選擇補齊既有測試 DB 或另建 disposable DB。
- 仍禁止：`union_db`、任何 production DB／provider、未核准 DDL、migration、seed／backfill、reset、source
  replacement、`--switch`、全庫清理及其他破壞性操作。schema／migration 變更仍須完整通過 3.1 的 disposable
  fresh-bootstrap 與 preserve-data candidate gates，不能用既有 DB runtime 測試取代。
- 本裁決不擴張任何 Work Package 的業務 scope、owner、public contract、external side effect 或 write set；若
  某包另有特定資料安全限制（例如 HCM 不合成／不上傳測試 XLSX），該限制仍有效。

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
