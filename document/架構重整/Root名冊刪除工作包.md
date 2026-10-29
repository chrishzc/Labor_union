# Root 案件刪除工作包

Authority：規格 33 RD-1 最新人工裁決，SPEC_READY／READY。月嫂永久刪除功能移除，保留退役／復職。案件未簽約時連同 case-owned 關聯資料永久刪除；任一相關月嫂或客戶曾簽回即禁止。

| 必要步驟 | 驗收 | 實作／oracle |
|---|---|---|
| 移除月嫂刪除能力 | RD-1b/f | StaffPage、staff router、typed kind 與 NAS procedure；API 不可達、既有退役測試 |
| 簽回 gate 與 case-owned cascade | RD-1c～f | coordinator／MySQL adapter／固定 case SQL；隔離 engine 驗 signed、關聯刪除、shared Client、其他案／月嫂保留、rollback、競態 |
| 明確永久刪除確認 | RD-1a/g | panel／client focused tests、TypeScript／build、本機前端更新 |
| closure | RD-A1～A5 | scoped architecture validator、diff／UTF-8、服務 GET readback |

Write set：原 registry-deletion 功能與直接 composition、專用 case SQL compiler、對應 spec／map／tests／NAS installer。其餘 dirty paths 保留。不操作既有業務資料，不安裝 NAS grants、不呼叫 provider、不提交 Git。

沿用既有 outer UoW、root fact、claim／receipt。未知依賴完整 rollback，不停用 FK；測試只新建本次隔離庫。簽回後案件及月嫂／共用來源不因案件刪除消失。最新驗證結果待本次執行，不沿用舊有關聯阻擋或月嫂刪除測試的成功宣稱。

## 2026-10-29 本機重啟與已核准保留資料升級

新增 Authority：使用者要求重啟前後端，並在得知啟動被新帳務結構阻擋後，明確同意「保留資料升級後重啟」。本節只擴充 localhost development `union_db` 的備份、候選驗證、同名保留資料置換與既有受管理 runtime 重啟；不是 NAS 部署、reset 或額外業務資料修改授權。

- current plan：`scratch/registry-restart/upgrade-preview.json`；待套僅 `1056_accounting_pricing.sql`，沒有 partial artifact。沿用正式 Migration 預設的 twins／subsidy backfill 選取與 preservation oracle，不自行刪掉必要 backfill；候選必須先通過既有資料保存驗證才可置換來源。
- source：localhost `union_db`；candidate：`union_db_local_20261029043512`。備份與 rollback／candidate receipts 沿用 `scratch/local_database_updates/<candidate>/`；SQL dump 含必要原資料，只保留於 ignored 本機目錄，不輸出內容。
- steps：正式 manifest／fresh engine gate → 停止同一 supervisor 擁有的 API、UI 與 writer workers → official dump／restore／apply-schema／verify-candidate → 同名置換及自動 rollback guard → schema gate → 原管理入口重啟及 GET-only readiness／新刪除 route 核對。現有帳號、MFA、業務與外部連線設定保留；不重新設定 Tunnel 或發送測試訊息。
- safe stop：候選未驗證不置換來源；來源 schema／data 漂移停止；置換失敗沿用 runner 的原備份自動還原。只使用本次受核准的 source／candidate，不刪除其他工作成果。
- gates：Scope／Inventory／Static PASS；fresh engine PASS（`lu_test_restart_schema_43168e3b0e1f`，772 statements，驗證 receipt `scratch/registry-restart/fresh-bootstrap-receipt.json`）；candidate／replacement／restart 尚在執行。
- 執行修正：預設 `union_db_local_20261029043512` 已完成 schema，但既有 subsidy backfill CLI 的 `lu_test_*` 限制拒絕該候選名稱；來源零變更。改用 `lu_test_union_db_restart_20261029_a6f9`，先驗來源資料／schema 仍等於原備份 checkpoint，再重用相同 dump／backup receipt。保留舊候選與診斷，不放寬回填工具 guard。
- 最新人工裁決取代上一項命名處理：使用者明確要求「不要改，直接用現有資料庫」「把只接受 lu_test_ 開頭的名稱這個限制移除」。已停止新候選流程；移除 prefix gate，沿用已 schema-applied 的 `union_db_local_20261029043512` 續做原 backfill／preservation 驗證，不再為名稱建立候選庫。工具 hash 透過新 v3 successor 記錄；保留舊 manifest、備份與其他候選，不覆寫既有證據。
- 後續同次執行：preservation 發現來源已提交政策仍被視為首次轉換，且舊 policy events 重算版本增量；修正 oracle、保留負例並以 v4 successor 綁定，writer 不變。使用者另明確同意「一併套用 1057，完成後重啟」；只在現有候選庫增量套用新增五表／singleton 的正式 1057，獨立 extension plan／receipt 保存在 `scratch/registry-restart/1057-extension/`，然後以 current catalog 驗全候選。來源仍維持 `union_db`，沒有改名或擴及其他庫。

### 本機升級與重啟最終 gates

| Gate | 結果 | Evidence |
|---|---|---|
| Scope | PASS | localhost development `union_db`，使用者明確核准保留資料升級、移除名稱限制、追加 1057 及重啟；仍使用既有 source／candidate 名稱。 |
| Change inventory | PASS | 1056 計價／分期及 1057 對帳的 schema＋singleton seed；canonical backfills 與保存 oracle；沒有新增任意資料修補、業務刪除或 production 操作。 |
| Static release | PASS | v4 工具 hash successor、正式 catalog／SQL／descriptor 與 validation manifest；v1／v2／v3 歷史 manifest 原樣保留。 |
| Descriptor | PASS | candidate 全部 current owned objects 驗證；1057 exact metadata，前後舊表 data fingerprints 相同。`scratch/registry-restart/1057-extension/engine.receipt.json`。 |
| Read-only plan | PASS | 原正式 plan 只有 1056；新增 1057 取得人工授權後以獨立 plan／artifact hash 審核。原始 plan／備份不覆寫。 |
| Engine verification | PASS | fresh 基線 772 statements；既有空基線與既有候選套用 1057 並驗舊資料不變；候選 378 張來源表保存驗證通過。來源同名置換後 388 張表與結構相符。 |
| Developer acceptance | PASS | 原管理器完成重建／啟動；API health 200、React 200，當時新刪除 routes 載入並驗證未登入讀取為 401（歷史服務證據；現行入口以 RD-1f 為準）；原 worker／Tunnel 程序 running。外部 Cloudflare 登入／真實 root 刪除業務資料未執行。 |

本機交付：`PASS`。source 仍為 `union_db`；備份及正式置換紀錄：`scratch/local_database_updates/union_db_local_20261029043512/source.sql`、`backup.receipt.json`、`replacement.receipt.json`。工具 hash 對應的 source snapshot 保存在同目錄 `tool-archive/`，不輸出 SQL dump 或憑證內容。

程式驗證：最新局部 pytest `42 passed, 2 skipped`（未執行 opt-in 舊合成資料重建測試）；TypeScript／Vite build PASS；scope architecture closure PASS（外部工作中的 errors 不納入本 slice）；strict UTF-8／scope diff check PASS。服務證據：`scratch/registry-restart/service-readiness.json`。前端版本 `react-admin-26e77e601f6112d4`，bundle `index-EndcHhaN.js`；supervisor PID 27996。

後續 NAS deployment／目標 grants 仍為 NOT_RUN，沒有以本機成功宣稱 NAS 已上線。僅本次建立的隔離庫／候選與備份被保留，沒有清理其他使用者成果；沒有 Git stage／commit／push。


## 最新 1058 保留資料更新授權

Qualification work_package identifier：`ROOT-CASE-DELETION-1058`。

使用者另明確核准「備份並保留資料更新後重啟」。Scope 僅 localhost development `union_db` 的 1058：在既有退款收據 `correction_type` enum 尾端追加 `refund_overage`；原值、ordinal 與資料不變，沒有回填。這是現行 launcher 的啟動相依需求，不更動案件／月嫂的資料列。

步驟：manifest／descriptor focused tests → 隔離 fresh、含三種舊 enum 的 source→dump→candidate→apply→verify → 原 evidence collector／qualification builder → 本機 read-only plan → 既有 writer 停止與 release-scoped dump／qualification fast path Apply → exactness／資料 fingerprints → 原管理入口重啟、API／UI GET readback。所有既有備份、歷史 receipt 與其他 dirty paths 保留。

安全停止：資格或資料保存驗證失敗不套用來源；不得為通過檢查而略過 qualification、修改 manifest 或重設資料庫。來源更新限已核准 1058，不自動追加其他 release。

## 本次最終驗證與交付（2026-10-29）

- PASS：月嫂刪除 UI、typed kind、專用 API 與 NAS 程序已移除；月嫂詳情在 root 條件下也不建立刪除 panel，既有退役／復職實際互動測試通過。
- PASS：案件僅以曾簽回阻擋；未簽約案件的配對／排班／帳務／歷程及 document/session-owned 待送任務同交易刪除；共用 Client、其他案件、月嫂及儲存來源保留。待送任務 IDs 先從 case-owned metadata 取得，不依賴稍後會刪除的文件仍存在。
- PASS：backend focused tests 33 passed；追加 1058 精確 SQL 辨識後的 predecessor regression 5 passed（含拒絕重排、移除、未知值、其他表）；NAS contract／predecessor 最後合跑 18 passed。React focused 62 passed，月嫂 root 僅退役／復職的最後重驗 5 passed。不把重跑重複加總。
- PASS：最新真 MySQL engine 13 passed，隔離庫 `lu_test_registry_delete_6e23cf24ef20`；native／NAS 程序都驗未簽約關聯刪除、任一方曾簽回拒絕（含舊 plan）、共用 Client、其他案任務與月嫂保留、同 key replay、audit rollback 與簽回競態。沒有刪除現有業務資料。
- PASS：TypeScript／production build、scope architecture closure、strict UTF-8、scope diff check。前端 bundle `/test/assets/index-C3GPy6dO.js`。
- PASS：原管理器已重新啟動 API、前端、原 worker 與 Tunnel。`scratch/registry-restart/case-signing-final-readiness.json`：API／前端 200、月嫂專用刪除路由消失、共用動作 pattern 僅 `retirement|reactivation`；舊 GET 404，舊 POST 由共用受保護動作路由拒絕為 401（非遺留的刪除 handler）。案件刪除路由存在，未登入 401。
- NOT_RUN：目標 NAS security installer／deployment；此項不屬本機交付，沒有宣稱目標 NAS grants 已套用。

| DB Gate | 結果 | Evidence |
|---|---|---|
| Scope | PASS | 使用者核准備份、保留資料更新 1058 與重啟；localhost development `union_db`，只有 enum 末尾追加。 |
| Change inventory | PASS | `1058_client_refund_overage_receipt.sql`，一條 ALTER、schema-only；無 seed／backfill／reset／replacement。 |
| Static release | PASS | current manifest／SQL hash／descriptor，predecessor 與精確 SQL 正負 regression 5 passed。 |
| Descriptor | PASS | 原三值 predecessor 與四值 successor 精確辨識；拒絕舊值重排，owned metadata exact。 |
| Read-only plan | PASS | `scratch/registry-restart/1058/live-plan.json`，只選已核准 1058。 |
| Engine verification | PASS | synthetic fresh／source→dump→candidate→verify；三種舊收據值與全體代表性資料 fingerprints 保留。`scratch/registry-restart/1058/evidence/`、正式 `validation/receipts/PROV-RD1058-local-additive-qualification-20261029.json`。 |
| Developer acceptance | PASS | canonical qualified runner 完成本機備份與 Apply，`scratch/registry-restart/1058/live-result.json` 為 current；原管理器啟動及 API／UI readback PASS。 |

本機 DB_CHANGE_READY／交付 PASS。來源仍名為 `union_db`。完整備份與 local baseline receipt 永久保留於 `scratch/local_database_updates/fast_additive/union_db.labor-union-client-refund-overage-receipt-2026-10-29-v1.backup.receipt.sql`／同名 `.json`；append-only journal 與 terminal receipt 位於相同目錄。正式工具紀錄 exact SQL 分類與 applied／verified，DDL 前後資料檢查通過；沒有繞過 qualification 或備份門。沒有 Git stage／commit／push。

## 案件刪除失敗修正（最新進行中）

使用者回報案件 115000178 刪除結果未明。唯讀確認案件存在、無成功刪除 receipt；後端兩次為 503。EXPLAIN 全部既有語句通過；實際案件有 14 個受不可刪除／不可改寫 trigger 保護的關聯，首個為 client_obligation_events 更新 guard。原 engine fixture 只建立 TABLE，漏載 trigger，因此舊 13 passed 不能證明完整 schema 下可刪除；該項完整可用性結論失效。

已核准 Authority：使用者明確同意「備份並驗證後更新保護規則」。修正限定 root、未簽約、本案、同一 outer UoW 的 active registry command claim；一般保護與已簽回拒絕仍保留。失敗／成功都清除 session context；舊 guard 拒絕回 typed 409 並 rollback，不誤報結果未明。

Authority 補充：自動核准審查曾拒絕未明列的共用 migration 工具擴充；使用者隨後明確同意「一併修正共用工具並驗證後更新」，核准共用 SQL 解析、fresh 產生流程、版本清單與生成檔路徑。受其他程式鎖定的舊生成檔原樣保留，current manifest 指向新生成檔，不強制解除檔案鎖。此授權不包含其他功能的 schema 更新。

已完成證據：完整 fresh engine PASS（389 tables／2 views／377 triggers）；含所有 triggers 的案件刪除 engine 19 passed，包含 native／NAS、簽回拒絕、假 context、越案拒絕、immutable rewrite 拒絕、舊 guard 失敗重現、同案修復後成功與 rollback。共用 parser／metadata／NAS contract 83 passed，API／coordinator focused 21 passed；generated release check、scoped architecture closure、strict UTF-8／diff check PASS。測試與 fresh 記錄位於 `scratch/registry-restart/delete-guard-fix/`。

正式 source fixture→dump→candidate→apply→verify 與 collector／qualification builder 已通過。`validation/receipts/PROV-REGISTRY-GUARDS-local-additive-qualification-20261029.json` 綁定本次 SQL／descriptor；包含未簽回與已簽回案件、排班、帳務、文件及待送任務的 synthetic 資料前後指紋相同。證據位於 `scratch/registry-restart/delete-guard-fix/evidence/`。

最新人工裁決：正式唯讀計畫待更新為 1059、1060；使用者選擇「只完成刪除修正驗證，暫不更新或重啟」。因此不更新現有 `union_db`、不停止或重啟服務、不刪除案件，也不套用 1059。此裁決取代先前的本機 Apply／restart 授權。現有網站尚未載入本次修正。

真實案件私有副本：live source 背景 writer 使還原後全庫比對不一致，正式 restore gate 正確拒絕，保留原失敗 receipt；該副本只能作診斷 fixture，不能作 live 升級資格證據。正式 preserve 資格由前述穩定 synthetic source／candidate 提供；隔離副本另驗 qualified 更新與提交前回滾，不能冒稱來源資料曾停止寫入。

隔離 fast path 實測為 **FAILED**：`blocked_duration_exceeded`，30 秒 guard 在 backup／locked fresh-read 後、第一條 DDL 前觸發。journal 只有 baseline／maintenance lock，無 statement_started；副本與現有來源都未因此執行 DDL。保留 `real-case-clone-qualified.log` 與該副本 release-scoped backup／journal，不延長上限或冒稱此更新路徑可用。此結果不推翻完整 fresh／preserve candidate 與功能 engine 的 PASS，但目前不能宣稱日常 fast Apply 已驗證可交付。

案件 115000178 私有副本功能驗證 **PASS**：副本單獨載入已驗證的 canonical guard fixture，確認 schema-only 前後資料一致、129 guard metadata exact；正式 coordinator／repository 完成案件及關聯刪除，在 outer commit 前驗證案件不存在及 context 已清除，隨即強制 rollback。回滾後全表 count／checksum／PK fingerprints 與前值相同。`scratch/registry-restart/delete-guard-fix/real-case-clone/functional-result.json`；此為隔離功能證據，不能取代失敗的 fast Apply 或宣稱原案件已刪除。

| DB Gate | 結果 | Evidence |
|---|---|---|
| Scope | PASS | 最新裁決只驗證；所有 mutation 限本次新隔離庫，現有 union_db 零 Apply／業務刪除／restart。 |
| Change inventory | PASS | 129 個條件式保護 trigger（258 statements）、同交易 claim context、parser／生成流程與 hash-bound metadata；無業務 backfill／provider effect。 |
| Static release | PASS | generated release／compact plan hash 與 inventory；parser／metadata／NAS contract 83 passed，API／coordinator 21 passed，plan contract 31 passed。 |
| Descriptor | PASS | synthetic fresh 與 preserve successor exact，完整／混合／缺少／未知改寫均有正負 oracle。 |
| Read-only plan | PASS | live-preview.json 正確列出待更新 1059、1060；未執行。 |
| Engine verification | PASS | 含全部 triggers 的 19 項 native／NAS engine tests；正式 source→backup→candidate→verify 資料保存及 qualification 通過。 |
| Qualified fast Apply | FAILED | 私有副本在第一條 DDL 前超過既有 30 秒限制；不放寬 deadline，不宣稱此路徑可用。 |
| Live developer acceptance | NOT_RUN | 使用者明確暫不更新或重啟；live-unchanged.json 為 PASS，原 API／UI 200，1059／1060 未套用，案件仍存在。 |

本次交付狀態：功能／preserve 驗證 PASS；日常 fast Apply FAILED；既有資料庫套用／重啟 NOT_RUN。NAS installation／deployment NOT_RUN。未 stage／commit／push，其他 dirty paths 保留。

## 更新工具分段計時修正（最新核准）

使用者明確要求照建議修正更新工具，在隔離副本完整驗證，暫不更新現有資料庫或重啟服務。Write set 限 canonical migration runner、updater 錯誤 transport、既有 local additive integration tests、對應 owner spec／map 與本工作包；不更動已驗證 SQL／descriptor、業務 writer 或原站服務。

修正：前置驗證及更新後驗證各 300 秒；DDL 額度維持最多 30 秒，等鎖最多 5 秒。驗證使用 bounded connection 與每次查詢前後 deadline check，保留所有 backup、identity、locked metadata／row fingerprints；單次 socket 不超過 30 秒。完成 receipt／journal 追加各階段／步驟耗時，錯誤保留階段代碼及去敏進度；已確認與未確認的 DDL 進度仍由原 journal 判定，不盲重試。

隔離驗證使用既有私有備份建立新 source，再經正式 backup／restore 建立穩定 candidate；只有新 `lu_test_guard_timing_*` 庫可 Apply。驗證完整 258 條 guard DDL、全表資料保存、案件 115000178 刪除提交前回滾與任一方簽回拒絕。既有 `union_db` 僅作最後唯讀確認，不讀出或輸出 PII／credential。最新完整結果待實際引擎驗證，不沿用先前 fast path 的 FAILED 或虛報本次已 PASS。

### 分段計時最終驗證

- **PASS**：更新工具、transport／維護入口及 guard descriptor 共 102 項 regression。慢速前置／後置驗證不耗用 DDL 額度；兩個驗證階段各自會停止；DDL 逾時保留已確認進度，未知結果拒絕 resume；locked source drift 零 DDL。補上 exact schema 但 journal 未完成時不得誤報成功，須走原 recovery。
- **PASS**：穩定私有 source `lu_test_guard_timing_source_0f9d05de5f` → 正式 backup／restore → candidate `lu_test_guard_timing_candidate_0f9d05de5f`。正式 qualified runner 僅在 candidate 套用 1060，258 條 DDL 完成，所有來源表資料保存。`scratch/registry-restart/delete-guard-fix/tool-phase-engine/` 保存 plan、原備份、restore receipt、release-scoped backup／journal、terminal receipt 與 state。
- **PASS**：candidate 的原案件 115000178 在正式 coordinator 刪除後、outer commit 前強制回滾；全表資料一致；追加 synthetic 月嫂簽回／客戶簽回兩種情境均 typed 拒絕，資料保留。沒有提交真實案件刪除。

| Apply 階段 | 實測 | 上限 |
|---|---:|---:|
| 前置驗證 | 93.641 秒 | 300 秒 |
| 結構修改 | 6.868 秒 | 30 秒 |
| 更新後驗證 | 12.948 秒 | 300 秒 |

前置細項：plan 66.206 秒、qualification／resume 2.299 秒、備份驗證 8.718 秒、等鎖 0.093 秒、locked metadata 7.774 秒、locked rows 8.546 秒。數字只涵蓋 canonical Apply，不包含建立隔離庫、備份還原及 updater 外層的其他 readonly plan；不宣稱全命令只執行 113 秒。原 DDL 上限足夠，沒有調高全域 30 秒限制。

| DB Gate | 結果 | Evidence |
|---|---|---|
| Scope | PASS | 本次執行只有兩個新 lu_test_guard_timing_* 庫可寫入；不執行 union_db Apply、業務刪除或服務 restart。 |
| Change inventory | PASS | 計時／有界 validation reads、去敏耗時／錯誤 transport、未完成 journal 重播保護；SQL／descriptor hash 不變。 |
| Static release | PASS | focused regression 102 passed；scope diff／strict UTF-8／architecture closure。 |
| Descriptor | PASS | candidate 所有 current owned metadata exact，guard successor 及 prerequisite readback 通過。 |
| Read-only plan | PASS | tool-phase-engine/plan.json 僅待套用 1060，未含其他 release。 |
| Engine verification | PASS | 正式 stable source backup／restore、qualified Apply、全表保存、案件 rollback／雙方簽回拒絕，phase timings 如上。 |
| Live Apply／restart | NOT_RUN | 本次沒有呼叫來源更新或 launcher，未進行 NAS installation／deployment。 |

**共享環境變動（不等同本次執行）：** 最終唯讀查核發現 union_db 已有 1059／1060 完成紀錄，台北時間分別為 2026-10-29 16:29:23、16:36:49；原案件仍存在，API／UI 均 200。這兩筆紀錄不同於本次 candidate 的寫入紀錄；不推測執行者或授權來源，不回復他人變更、不重啟服務。`tool-phase-engine/live-observation.json` 保存去敏事實；較早的 live-unchanged.json 僅代表當時狀態，不能冒充最新現況。本次交付為程式及隔離驗證 PASS，來源 Apply／restart NOT_RUN；沒有 Git stage／commit／push。
