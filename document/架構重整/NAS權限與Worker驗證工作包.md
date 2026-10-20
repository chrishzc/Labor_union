# NAS 權限與 Worker 驗證工作包

狀態：DB_PHASE_COMPLETE；LOCAL_SCOPED_APPLICATION_VALIDATED；MONITOR_PASSED；NAS_E2E_NOT_RUN；NOT_DEPLOYABLE。
work_package_id：NAS-SECURITY-20261019。
後續範圍（私人照片後端）：依 NAS-LINE-04，將 NAS 公開照片／日誌入口接到受限私人 transport，沿用原 Scheduling owner、controlled-file storage 與現有資料格式。這次不修改任何 Compose／前端、不產生部署包，不操作 NAS、provider 或既有資料。驗收：私人機器身分隔離、原始 LINE token 重新驗證、本人服務範圍、跨檔案拒絕、重送／單一交易與公開 transport 不觸碰檔案；環境不足的既有 NOT_RUN 不改標 PASS。
Authority：2026-10-19 最新指示重試 Docker 核准，以隔離 MySQL 驗證權限與交易，通過後重新產生初始化結構。僅操作自行建立的 localhost lu_test_*；不碰既有資料，不打包、建置或上傳映像。
後續 Authority：以隔離環境驗證登入／網頁建立 root、管理介面、需求核准、日誌照片、PDF、匯入及背景工作；LINE Worker 最後只確認能啟動。不碰既有資料，不打包或上傳映像。沿用先前程式與權限修正授權；沒有真實 provider effect、NAS deployment 或未定義 schema 的追加授權。
基線：main / 17561b386aa6ec63d5942881cd03858b68f980c4，開始時 clean。
正式規格：`01_規格基線/17_External_Integration_LINE_Access正式規格.md` NAS-AUTH-01、NAS-DB-01/02/03、NAS-WORKER-01/02、NAS-LINE-01/02/03；registration 呈現依 29 §4；migration 依 10 §9。

convergence: {status: LOCAL_ACCEPTANCE_COMPLETE, blockers: [], deferred: [WINDOWS_TESTCLIENT_14, NAS_DSM_2GB, REAL_PROVIDER_E2E]}

## 範圍、來源與驗收對照

| 契約 | current source／重用 | 保留工作 | 直接 oracle |
|---|---|---|---|
| NAS-AUTH-01 / DB-01/02 | 既有十類 writer、UoW 與 API／React typed contract | 固定用途程序、adapter delegation、逐功能授權，原有 UI 行為保留 | 合法功能成功、直接 DELETE 拒絕、跨對象／stale 拒絕、outer rollback |
| NAS-DB-03 | NAS initialize、canonical schema／migration、mysql adapter | 非覆寫安裝／升級、分離服務連線與 secrets、部署設定 | disposable fresh + preserve-data candidate；SHOW GRANTS 與各身分負例 |
| NAS-WORKER-01/02 | private_operations client/auth/operation-service gate | NAS 獨立 token、verifier、HTTPS/CA、初始化與掛載 | 身分不可冒充、憑證撤銷、缺檔／明文拒絕、無 DB credential；既有 local runtime regression |
| NAS-LINE-01 | provisional registration、identity application、LIFF registration | 保存申請／工會核准、管理入口、additive migration | 提交無 Client、核准一次、競爭與 replay、既有資料保留 |
| NAS-LINE-02 | Customer Service intake、Scheduling diary/media | 在受限身分下保留既有行為 | 申請不改核心、本人成功／他人拒絕、日誌提醒與照片關聯 |

## 順序與效果上限

1. 規格與 static；Worker 邊界與 focused tests。
2. DB descriptor／installer plan；隔離 MySQL fresh、preserve-data、程序與 grants 驗證。
3. 原 writer／API／UI regression，登入／root／申請／日誌照片。
4. PDF／匯入／背景工作與重啟持久化；最後 LINE Worker check-only。
5. NAS 實機及真實 Cloudflare／LINE E2E 需環境，沒有執行證據標 NOT_RUN。

只可編輯本次 source、direct tests、正式規格、受影響 map 與 deployment；不 stage/commit/push、不切 branch、不部署、不上傳 Hub、不發 provider、不 reset 既有 DB。DB runtime 僅自行建立的 localhost `lu_test_*`；真實現有 DB 先唯讀 plan，非空／partial／unknown 停止，不覆寫。失敗保留診斷；不用 fallback 到 broad grants 或 production local key 過關。

## 驗證紀錄

| 狀態 | 驗證 | 實際結果及限制 |
|---|---|---|
| PASS | Python focused regression | 最後合併執行 149 passed、14 deselected；其後新增 readonly CLI 不讀 runtime 密碼的 oracle，該 module 11 passed。合計 150 個不同離線情境通過。包含 credential、profile／column scope、必要 grants 缺漏、申請／核准／舊 receipt、model rollback、合法功能與 retention；不是 MySQL 引擎通過。 |
| PASS | 新需求核准管理頁 | 3 項 Vitest：session／version、未確認核准結果拒絕、查看內容及失敗保留。 |
| PASS（原 3 項失敗已補齊） | 既有客戶名冊 UI regression | 原先 36 passed／3 failed，基線同樣失敗。依正式規格 33 的 2026-10-16 公會編號＋姓名／資料待確認規則校正舊預期，並替無 HCM lineage 的 fixture 補上 bounded 空查詢 mock，避免誤連 localhost。最後 39 passed；原重試、正式換人回讀、日期與草稿保留 assertions 不變。沒有修改 production 名冊顯示以迎合舊測試。 |
| PASS | 前端 build | TypeScript 與 Vite 成功；既有 bundle 大小 warning，不代表瀏覽器／NAS E2E 通過。 |
| PASS | 靜態／架構 | 最終 51 個新增或修改 Python 檔 AST、strict UTF-8、current release／compact bindings、architecture closure（零 errors／warnings）與 git diff --check。 |
| NOT_RUN／先前 BLOCKED | Windows TestClient integration（前階段） | 前階段略過 13 個 Private API TestClient 與 1 個 legacy asyncio 情境；Windows asyncio socketpair 在進入 endpoint 前阻塞，未更改 framework 或 production 行為以繞過。後續 Linux 真實 HTTPS／browser 結果另列，不代表這些 Windows 測試已通過。 |
| PASS | MySQL／Docker | Docker 核准恢復；僅新建本機 43319 專用 MySQL 8.0.46 與獨立資料卷。最終 engine 63 passed，涵蓋 4 profiles、TLS／明文拒絕、26 程序成功／stale、直接 DELETE／DDL／越權程序拒絕、真正 commit／rollback、鎖及 LINE 申請核准重送。未碰既有 DB／NAS。 |
| PASS | 本輪受影響 focused regression | 49 passed；最後 scope 判定另以 policy／descriptor 13 passed，以及完整 engine 63 passed 複驗。與前次離線測試有重疊，不加總為不同情境。 |
| PASS | Preserve-data candidate | 以前版 canonical compact 建立 synthetic source，含既有 Client、BeClass、completed registration 與 LINE 投影；canonical dump → restore → apply → verify 通過，舊欄投影保留。strict collector／qualification builder 產生 hash-bound receipt，未改真實來源或切換環境。 |
| PASS | Compact fresh schema | canonical builder 從自建 synthetic source 重產 v46；371 tables、377 triggers、1 view、758 statements。SQL 比前版只增加四個申請欄位；hash／來源綁定通過。另建新空庫直接載入生成物，current descriptor、系統空業務表及公開權限 installer 驗證通過。 |
| PASS | 公開設定與 launcher | configure 預設 plan 實際零帳號／程序／舊帳號異動；apply 後四 profile exact、模擬舊 scoped nas_app 撤權鎖定，Client／網站帳號仍為零。實際 Windows launcher 明確指定隔離 env，唯讀 require-current 的輸出為 current。 |
| NOT_RUN | 交付／實機 | Docker image build／push、DSM GUI／HTTPS／資源量測、Cloudflare／LINE provider E2E 未執行；後續本機應用結果另列。 |

UI 基線比較 evidence：`scratch/nas-security-20261019/registry-baseline-results.json` 與 `registry-current-results.json`；同三個 failing case 已實際比較。比較只替換原頁面模組以隔離新增分頁，不宣稱整庫舊版測試已通過。

必要 MySQL 執行前提已由官方契約及實際 engine 核對：FOR UPDATE 使用限定本庫的 LOCK TABLES 保留原有鎖定，未替 LINE 增加核心 DML。database wildcard 依 partial_revokes 處理；只有 exact schema／object scope 可自動調整，未知跨庫／wildcard legacy grants 停止，不擅自撤銷其他資料庫權限。

本輪修正實際驗證發現的 descriptor 載入／canonical 四欄投影缺漏、PyMySQL percent 與 metadata alias 問題、JSON_TABLE 字元排序衝突，以及申請重送重建 timestamped 回覆造成的 idempotency conflict。知識 request child snapshot 的 NULL 不可繞過 stale guard；相關負例已在 engine 驗證。

## 本輪 DB 執行門

| Gate | 狀態 | Evidence |
|---|---|---|
| Scope | PASS | 本工作包及最新人工指示；只操作自行新建 localhost lu_test_*。 |
| Change inventory | PASS | schema-only 四欄，無 business backfill；安全 DDL 僅專屬帳號／固定程序；刪除／替換僅作用於 synthetic scenario fixtures，既有資料零異動。 |
| Static release | PASS | canonical ordered chain 含 1052、release／descriptor hash、fresh assembly／validation manifest 驗證通過。 |
| Descriptor | PASS | 四欄 absent／exact／partial／drift regression，fresh 與 preserve candidate 引擎 exact。 |
| Read-only plan | PASS | canonical predecessor plan、configure 零寫入 plan、Windows launcher require-current。 |
| Engine | PASS | `scratch/nas-security-20261019/engine-final-scope.xml`；63 passed；fresh／preserve receipt 如下。 |
| Developer acceptance | PASS | `scratch/nas-security-20261019/compact-delivery-verification.json`；生成 SQL 新庫初始化、設定入口及實際 Windows launcher（僅隔離 env、唯讀）通過。 |

正式 qualification：`validation/receipts/PROV-NAS-REGISTRATION-local-additive-qualification-20261019.json`；supporting dumps／receipts 在 `scratch/nas-security-20261019/preserve-7a49db563f63/`。其他 evidence：`compact-generation.json`、`focused-final.xml`，均在同一 scratch 工作目錄。失敗的測試庫與 journal 保留，沒有 reset 或以原地重播掩蓋問題。

前一 DB 階段結束已停止專用 MySQL 測試容器以釋放資源；容器、獨立資料卷、各測試庫與診斷仍保留。原有 Redis 容器未操作。

索引配置器使用 MAX(index_version)+1，因此 cleanup 保留鎖定交易內先移除舊 artifact、再 commit 的原始順序；失敗不 commit 且回報 reconciliation，避免改成 commit 後清檔造成版本重用競爭。檔案不具 SQL rollback 原子性，仍需實際 DB／檔案失敗驗證。

## 後續隔離完整應用驗證

使用已存在的本機 r2 runtime 映像、唯讀掛載本次 source、獨立 MySQL／Redis／settings／files named volumes，以及所有設為 internal 的 Docker 網路；未建置或下載新映像、未發布 host port。前端只編譯成測試用靜態檔。最後完整重驗環境為 `lu-nas-init-final-20261019`，資料庫固定 `lu_test_nas_preview`，與原有服務及先前 DB 引擎環境完全分開；前一 `lu-nas-app3-20261019` 保留所有資料及診斷。

| 狀態 | 實際驗證 | 證據與限制 |
|---|---|---|
| PASS | fresh MySQL CLI bootstrap／exact grants／strict API TLS | 真實 Docker MySQL CLI 初始化中文 seeds；四 DB profiles 保留受限權限。HTTP client 驗證私有 CA 與服務主機名，沒有關閉 TLS 驗證。 |
| PASS | 真實瀏覽器建立 root、MFA、登入與管理頁 | Playwright Chromium 操作 `/setup`；第二次建立拒絕、setup 不簽發 session；完成 MFA 綁定後重新登入。已檢視管理頁及核准畫面截圖。瀏覽器允許自簽測試憑證，僅 HTTP client 的 strict TLS 結果證明私有 CA；不冒稱 DSM 憑證部署通過。 |
| PASS | root／一般工會人員隔離 | root 建立一般人員；一般人員 MFA 登入、查詢、合法假日新增及指定刪除成功；帳號中心 403；root 停權後原 session 401。日常 API 不使用 MySQL root。 |
| PASS | LINE 需求申請 → 人工核准 | 真正 token verifier、public ASGI app 及 line DB profile；只把外部 LINE 驗證回應替換為 synthetic fixture。申請不建 Client／BeClass；瀏覽器人工核准才建立、綁定；同申請重送不重複建立。 |
| PASS | 本人日誌、照片及跨人拒絕 | 真正 owner Preview／Apply、line profile 與 controlled storage，提交本人服務日誌及合成 JPEG，附件與日誌同交易保存，他人不能讀取或提交。LINE provider 驗證回應為 fixture，並非真實 LINE 登入。 |
| PASS | PDF | 真正完整契約預覽、Chromium PDF、受控保存、登入下載及重送同版本。產出約 2 MB，已檢視首張頁面，中文字正常；沒有更換輕量化 renderer。 |
| PASS | Excel 匯入 | 合成 XLSX 經真實 HTTP Preview／Apply，第一次建檔、第二次取代關聯、同 workbook 重送一致，staff 不重複建立；P05 固定程序與 management profile 實際執行。此列是月嫂歷史 workbook 情境，不宣稱所有帳務匯入種類皆已 E2E。 |
| PASS（限定情境） | durable／knowledge／incident 背景週期 | 真正獨立 token、HTTPS API、非空佇列領取、預期 owner 拒絕、一次執行、closed 終態回讀與心跳；incident 維護週期成功。knowledge 缺少索引的失敗能保存；沒有啟用 Gemini／付費模型或成功生成知識答案，不宣稱 AI provider E2E 通過。 |
| PASS（原缺表失敗已修正） | runtime-monitor 保存週期 | 使用者取消個別偏好表後，依 NAS-LINE-03 改用既有固定規則；移除缺表查詢與選用 fallback，必要表的 1142／1146 仍向上傳播。隔離 runtime-monitor 使用獨立 token、私人 CA、原受限 DB profile 完成一次週期，11 項 observation 與 heartbeat 真正提交；API／React probe healthy。不新增表或放寬 grants。 |
| PASS | DB／API 重啟持久化 | 停管理 API、重啟同一專用 MySQL，再啟動 API；帳號、root、MFA、業務與日誌／附件數量一致，session 可用、setup 保持關閉，PDF 與照片下載 digest 一致。 |
| PASS | 真實 LINE API 與合成 Webhook | 獨立 HTTPS origin 啟動，無效簽章 401、正確合成簽章入列及去重成功；公開 origin 管理帳號／setup 404、未認證 private check 拒絕。未連 LINE 平台或 Cloudflare。 |
| PASS | LINE Worker check-only，最後執行 | 最終新環境在其他應用測試後執行 `--check`，啟動及私人 CA／獨立機器認證通過；沒有跑 cycle 或 provider。前後 inbox、delivery、attempt 及 worker cycle heartbeat 數量完全相同。 |
| PASS | focused regression／架構 | Python 39 passed；前端相關 11 passed（既有 React act warning）。closure errors／warnings 均零，53 個變動 Python strict UTF-8／AST 與 compact hash／inventory 通過。 |
| PASS | 最終網頁編譯及實際資料載入 | 最後 TypeScript／Vite build 通過（既有 chunk warning）；載入 `react-final-verified`，真實 Chromium 等到名冊中的合成客戶資料出現，再確認 job 終態可回讀，沒有把 loading 框架當成完成。 |
| NOT_RUN | 實機及外部 | DSM／NAS 2 GB 實機與負載、真實 LINE Login／LIFF／訊息收送、Cloudflare Tunnel、Gemini provider；Docker image build／push 均未執行。 |

本階段修正六個實際整合缺口：MySQL CLI 的 UTF-8 設定、私人 API 憑證 strict chain extension、直接 LIFF 申請的 verified platform-user 紀錄、LINE controlled media 的 append-only command claim 權限、管理端 PDF final-preview HMAC key 自動產生，以及 job 公開失敗分類與 canonical ErrorCategory 對齊（同步兩個前端 decoder）。沒有新增人工啟用碼、弱化 HTTPS／MFA，或放寬核心資料 DML。

PDF 首次失敗另有測試工具因素：fixture ASGI 以 root 建立共用 staging 子目錄，正式 API 使用 UID 1000 無法寫入。只修正本次隔離卷的 fixture 檔案擁有者後通過；正式 source 的 API 皆使用 UID 1000，沒有為此增加 production chmod／chown fallback。

名冊的後續完整讀取曾因自建日誌 fixture 的 `service_days=0` 而被既有契約拒絕。直接 UPDATE 該測試訂單被自動審查拒絕，未執行，也沒有間接修補；正式 owner 流程的前置條件不適用此最小 fixture，因此保留舊環境，另外從空 MySQL 卷建立正確初始 fixture（service_days=1）完整重驗，名冊實際資料載入通過。這是測試輸入問題，未改 production validation 或資料庫規則。

最後新環境的 LINE 日誌／照片測試直接以 UID 1000 執行；全部提交與身分 assertions 已完成，但追加 root 建立的 evidence 檔失敗。後續改為依 UID 分開保存測試紀錄，僅重新查詢已提交的日誌與附件及跨人拒絕；沒有重送提交或修改資料。新環境 PDF 不需要額外檔案權限修補，fresh 自動產生的 HMAC key 直接可用；重啟後照片／PDF bytes digest 仍一致。

診斷及 supporting evidence 在 `scratch/nas-app-20261019/`：`checks.jsonl`、`focused-final.xml`、`architecture-closure.json`、`management-after-login.png`、`registration-approved.png`、`isolated-client-contract.pdf`、`pdf-first-page.png`、`pdf-result.json`、`worker-heartbeats.json`、`persistence-before.json`。測試帳密／TOTP／session 僅在 ignored 私有 fixture 檔與專屬 Docker 卷，沒有寫入此文件或輸出。第一次及第二次初始化失敗環境保留，不重設或刪除以掩蓋錯誤。
最後完整重驗的 evidence 在同目錄 `final-run/`，使用獨立 `checks.jsonl`／`checks-1000.jsonl`、截圖、PDF、心跳及持久化基準；沒有沿用舊帳密或覆寫舊 evidence。啟動設定為 `compose.application-final.yaml`。fresh initializer 的 PDF secret／UTF-8 與重跑不覆寫檢查另有 `initializer-fingerprint.json`（只含 ignored 內容指紋，不含秘密值）。
本輪結束已停止最終應用及前幾組測試的服務以釋放資源，容器、資料卷和 evidence 全部保留；未停止使用者原有 `union_redis`。未打包、建置或上傳映像，沒有操作 NAS、原有資料庫或外部 provider。

初步用量僅為 Windows Docker 的單次觀察：management 約 284 MiB、MySQL 約 388 MiB；並非 NAS 效能測試，也不代表所有容器加 DSM 能在 2 GB 可靠同時運作。

操作及接續順序由 `deployment/nas/README.md` 承接。既有 Docker Hub 映像未改變；本機主要應用流程及完整監測保存週期已有證據；NAS 實機與外部 provider 仍未驗證，不是可直接發布的版本。


## 2026-10-19 補齊未通過項目

Authority：使用者接受既有申請表四個新增欄位、取消告警偏好表，並明確保留三類環境不足的 NOT_RUN，只補齊目前失敗。此輪沒有 schema／migration、新表或帳號新增；沒有重新初始化或擴權。

- **PASS：** 42 項 Python focused regression（監測、固定分類查詢／拒絕編輯、target CAS／交易與權限設定）。真實必需表錯誤不被當成選用表缺失吞掉。
- **PASS：** 前端 41 項（客戶名冊 39、固定告警分類 2）；最後文字校對後，受影響告警 2 項再次通過。TypeScript／Vite build 及 artifact attestation 通過，仍有既有 chunk 大小提示。
- **PASS：** 真實 HTTPS GET 回讀固定規則、舊 PATCH 回 409／`line_alert_preferences_fixed`、不存在對象 404；修正告警 API 原先缺少 `current_version` 導致共用錯誤處理器把具體原因改成 generic conflict 的格式問題。
- **PASS：** 真正 Chromium 開啟最後編譯畫面，分類唯讀、不採用舊瀏覽器偏好、不發 PATCH；系統健康分類在群組被過濾，訊息預覽及原 target 暫停／重設控制保留。畫面文字同步表達固定規則。
- **PASS：** 監測完整保存、技術告警對象透過既有 owner／outer UoW 和 management profile 建立，前後核心業務／帳號／檔案數量不變。資料庫未建立告警偏好表。
- **PASS：** LINE Worker 最後只跑 `--check`；前後 inbox、delivery、attempt、cycle heartbeat 數量一致，不消耗佇列、不發 provider。

監測週期通過不等於所有服務皆 healthy：LINE Worker 按指示沒有執行 cycle，因此 line_worker 無正常週期心跳而呈 critical；未設定外部網址與未常駐 knowledge worker 的檢查呈 unknown。這些狀態如實保存，不停用檢查或偽造 heartbeat。

證據：`scratch/nas-fixes-20261019/backend-final.xml`、`frontend-final.xml`、`live-checks.jsonl`、`monitor-status.json`、`fixed-alert-rules-full.png`、`architecture-closure.json`。驗證沿用同一 `lu-nas-init-final-20261019` 隔離專案的卷；`compose.verify.yaml` 只替換已核對的網頁 artifact 與增加 evidence 掛載，未打包或上傳 Docker image。

三類 NOT_RUN 保留：Windows TestClient／legacy asyncio 14 項、DSM／NAS 2 GB 實機與負載、真實 Cloudflare／LINE／外部 AI 服務。不得以本機通過取代這些結果。測試後停止本次隔離服務並保留卷及 evidence；使用者原有服務不受影響。


## 2026-10-19 私人照片後端交付（Compose／前端後續處理）

本階段只完成後端程式與權限規則，沒有修改／建立 Compose、前端或部署包，沒有搬移既有檔案或更新既有 DB 的 grants。不是 NAS 已完成檔案隔離的證據。

- NAS `line_app` 的照片上傳、日誌 Query／Preview／Apply 與本人附件下載只呼叫私人 HTTPS，沒有本機 storage fallback。原上傳與日誌網址、Schema、idempotency key 沿用；既有 local／管理端 handlers 仍由私人 routes 重用，Scheduling owner／outer UoW 不變。
- `line-media-proxy` 使用獨立 token，僅能進入 `/internal/v1/line-media/`；不能呼叫其他 Worker 的 check／執行入口。私人端重驗原始 LINE ID token、current binding 及服務範圍，不能用 flow 或宣稱的 staff ID 取代。未知／撤銷憑證、錯服務、明文、錯 CA、設定缺漏皆拒絕。
- 私人 endpoint 將重用 handlers 的 legacy HTTP error 轉為完整 Global typed error，避免管理端 error middleware 抹掉具體原因。NAS stale Preview 明確回 409，沒有 blind retry。
- 本人附件下載先查本人日誌，再核對 attachment file_id、Scheduling owner／案件／照片用途，才讀取受控 bytes；維持 digest 驗證與 JPEG／PNG 格式；上傳容量改由下述設定決定，已存附件不套用新上傳容量，回應 private no-store／nosniff，不提供任意路徑、檔案總覽或刪除入口。本人合法附件遇儲存權限／掛載失敗時回 503，不誤報成不存在；跨人／跨附件仍 404。
- 公開 LINE DB profile 對受控檔案 facts、日誌主檔／附件／完成事件改為 SELECT。維持原 LINE 通知 outbox／checkpoint、LINE 專用媒體及必要 command claim 權限。僅修改 installer／startup expected grants；未 apply 到任何原有 schema。management 原合法操作保留，無新表／欄位／migration，未重產 schema SQL。

驗證：離線 auth／NAS composition／權限 policy／日誌 owner／封閉 transport error focused 55 passed；本輪新 UUID lu_test schema 的 canonical fresh bootstrap、4 profiles／26 routines 與完整 engine regression 64 passed。Linux 非 root、唯讀 root filesystem、cap_drop ALL、無外網容器中的真實 HTTPS／ASGI／檔案測試 7 組通過，涵蓋正常日誌與照片、重送、stale、跨人、跨附件、內部檔案拒絕、錯格式／大小、設定缺漏、機器憑證越權／撤銷與 TLS 拒絕；最後以實際 `scripts.run_line_worker --check` CLI 確認啟動與認證，不執行 work cycle。該 HTTPS 測試的 LINE provider 回應與 repositories 為合成 fixtures；MySQL engine 結果分開記錄，不能合稱全應用 E2E。

證據：`scratch/nas-private-media-20261019/focused-final.xml`、`engine-bootstrap.json`、`engine.xml`、`linux-https-final-3.log`、`architecture-closure.json`。測試 SQL 僅本輪新建 schema，舊環境保留；測試服務結束後停止，資料卷與 evidence 保留。TLS 負例中的連線中止訊息是預期拒絕，不能當成服務正常週期錯誤。

### 前端後續可串接的能力

下列路徑共用 `/api/v1/line/staff-self-service`，LINE token 放 request body／multipart，不放 URL。

| 能力 | 方法與路徑 | 前端需要處理 |
|---|---|---|
| 上傳寶寶／餐食照片 | POST `/service-day-media` | 檔案、assignment、日期、kind；保留 Idempotency-Key，顯示上傳結果與失敗 |
| 日誌預覽 | POST `/service-day-logs/preview` | 日誌與 staging 附件；顯示 blockers、保存 fingerprint |
| 日誌提交 | POST `/service-day-logs/apply` | 明確確認、原 fingerprint／key；未知結果用同 key 核對，成功後回讀 |
| 本人日誌與附件關聯 | POST `/service-day-logs/{log_id}/query` | 日誌文字、完成狀態與 opaque 附件 ID；不顯示 NAS 路徑 |
| 本人已保存照片 | POST `/service-day-logs/{log_id}/photos/{file_id}/download` | authenticated fetch → Blob 預覽／下載；離開畫面釋放 Object URL；不使用公開 img URL 或 token query |

後續 UI 實作已沿既有頁面補照片選擇預覽、確認／提交／回讀、已保存照片預覽／下載及身分失效處理。履歷保留版本上傳／下載並補所選與已存 PDF 預覽、載入／失敗／空值區分。檔案操作顯示等待狀態；不新增內容辨識、照片原地覆寫／刪除、多張附件或斷點續傳。

### 檔案大小與等待時間（程式設定，未準備 Compose）

| 環境設定 | 相容預設 | 作用 |
|---|---|---|
| `FILE_PHOTO_MAX_BYTES` | `10485760` | 日誌照片單檔上限，正整數 bytes；不是餐食內容辨識 |
| `FILE_RESUME_MAX_BYTES` | `20971520` | 履歷 PDF 單檔上限，正整數 bytes；其他受控文件維持原上限 |
| `FILE_TRANSFER_TIMEOUT_SECONDS` | `60` | 檔案操作等待秒數；`0` 關閉應用程式的這個計時器，外層網路仍可能中斷 |

環境值作為尚未保存設定時的初值；下述真實設定頁的持久化值優先，後續檔案操作重新讀取。公開 LINE 經私人 HTTPS 取得權威容量／等待時間，不以公開端舊環境值縮小容量。管理 UI 從 authenticated `/api/v1/storage/transfer-settings` 取得設定，不把上限寫死在前端。原 10／20 MiB 僅相容預設，不是新增業務需求；超過時明確拒收，不壓縮、不截斷、不覆寫舊版本。已存照片不因日後調低上傳上限而禁止下載。

等待包含檔案傳輸與回應本文讀取。逾時不代表未儲存；日誌保留原 Apply key 供同操作重試，履歷保留既有操作識別與暫存進度。大小可調不等於可無限增大：目前 workflow/storage 仍以 bytes 傳遞，未在本次引入串流儲存介面；較大檔案須在 NAS 容量測試後設定。儲存 adapter 的 staging/read 容量同步使用 runtime 設定，設定保存時保留既有較大讀取容量，降低新上傳上限不阻止舊檔下載。

本次 focused 驗證：前端／傳輸 41 passed；隔離 Linux API／容量／格式／中文下載檔名 28 passed；私人真實 HTTPS 8 組 passed（LINE Worker CLI 僅最後 `--check`，不跑業務週期）；TypeScript noEmit passed。瀏覽器以合成 API 回應驗證照片／PDF 實際預覽、下載、超限、登入失效及相同 key 重試，畫面與結果位於 `scratch/nas-file-ui-20261019/`。這些不代表真實 NAS、LINE provider 或全應用 DB E2E 通過；Windows 原生 asyncio socketpair 受環境限制，對應 API 情境已在隔離 Linux 執行。不準備 Compose、打包或上傳映像，未異動既有資料庫。

### 後續部署設定的必要條件（本輪未準備）

- 代理端要有 `LINE_MEDIA_API_BASE_URL`、`LINE_MEDIA_SERVICE_TOKEN_FILE`、`LINE_MEDIA_API_CA_FILE`，只接受 HTTPS／明確 CA，沒有 shared key 或本機檔案 fallback。
- `prepare_credentials` 支援 `line-media-proxy` 獨立身分與 API verifier；目前 NAS initializer 明確維持原五個 Worker 的既有掛載契約，不會偷偷在唯讀 root 建第六個憑證目錄。未來 Compose／安全升級須一併準備新 proxy token、管理端 verifier 與掛載，不可只填 URL。
- 既有 Compose 仍具有舊的共同受控檔案掛載；本輪沒有改動。因此部署前必須移除公開 LINE 的正式照片／履歷／合約／備份掛載，準備私人通道及正確 UID／GID、DSM ACL、根目錄與憑證權限，再執行實機驗收。這些未完成前不得宣稱遭控制的 LINE 程式已被 OS 阻止讀寫正式檔案。
- 既有 Windows 14 項、NAS／DSM／2 GB 實機與真實 Cloudflare／LINE／外部 AI 的 NOT_RUN 繼續保留。這輪沒有重跑既有前端、PDF／匯入 E2E 或發送 provider。


### 預覽調整與原設計核對（2026-10-19）

檔案等待預設依人工要求改為 60 秒；移除獨立預覽中的照片／履歷截圖分頁，正式照片與履歷功能保留。原始 NAS 文件已整併為正式規格 30；Git history 中的原規劃分訂單 `orders/{case_no}/`、月嫂 `caregivers/{staff_id}/` 兩大專區，現行共同契約 00 §2.2 及 30 §8–§13 仍要求業務分類、暫存、隔離備份與對帳。當前程式只有單一 `CONTROLLED_FILE_STORAGE_ROOT`，邏輯分類與實體路徑不能混為一談；多個實體根目錄、搬移與掛載尚未實作或套用。獨立預覽位於 `scratch/nas-file-settings-preview-20261019/index.html`，僅示例、不連後端。


### 真實檔案設定頁實作（2026-10-19）

依人工確認的預覽實作「稽核與系統 → 檔案設定」，不顯示原設計分類，也不增加照片／履歷獨立頁。實際讀取、編輯、變更預覽、確認保存與重新讀取均接至後端；一般工會人員保留業務檔案操作，設定完整路徑僅 root 可讀寫。

設定保存於 `FILE_SETTINGS_PATH` 指定的持久化 JSON；未指定時沿用正式規格 30 §13A 的預設位置。使用原子替換、程序間鎖與版本比對，不新增 DB 表或搬檔。部署時須為管理服務配置該設定檔的可寫持久化位置，公開 LINE 不掛載它。容量與等待時間後續操作生效；NAS source path 僅保存部署需求，待掛載調整，不是已切換或已驗證 DSM 權限。

驗證 PASS：新 UI 7 項與既有履歷／傳輸 41 項（共 48 項）、隔離 Linux API 44 項、私人實際 HTTPS 8 組（最後僅 LINE Worker --check）、TypeScript noEmit、架構 closure 零 errors／warnings；實際 Chromium 桌面／手機渲染、驗證提示、預覽前不寫入、保存後重新讀取及待部署狀態均通過。瀏覽器使用合成 API 回應，真實 JSON 保存由 API 測試分開驗證，未宣稱全應用 DB E2E。畫面與結果位於 `scratch/nas-file-settings-live-20261019/`。未準備 Compose、打包、上傳或異動既有資料。NAS／DSM／外部 provider 驗證仍為 NOT_RUN。


### 路徑改為唯讀（2026-10-19 後續人工確認）

取代上一階段的可編輯部署備註：設定頁只顯示目前 runtime 的容器內儲存根目錄，不猜測 NAS host source path，不提供路徑修改，也不顯示待部署備註。PUT 只接受容量、等待時間及 expected_version；舊 JSON 路徑備註忽略，容量與版本保留。真正 NAS 掛載留待 Compose，本輪不修改部署檔或環境檔。

PASS：前端設定／履歷傳輸 12 項、隔離 API 24 項、私人 HTTPS 8 組（LINE Worker 最後僅 --check）、TypeScript noEmit、架構 closure 零 errors／warnings；對正在執行的完整管理介面與真實 API 進行唯讀瀏覽器驗證，確認路徑無輸入框、容量與時間可編輯、變更預覽不含路徑，未 PUT 設定或修改業務資料。畫面與結果在 `scratch/nas-manual-ui-20261019/readonly-path-*`。手動檢查後端已重啟載入最新版，前端服務維持啟動。


### Container Manager Compose／環境範本（2026-10-19）

依人工授權更新 `deployment/nas/compose.yaml`、新增 `.env.example`、同步 Tunnel 範例與既有 README。單檔 Compose 預設基本組，透過同目錄 `.env` 的 COMPOSE_PROFILES 分別啟動 durable／knowledge／incident／monitor／line／tunnel／line-check；LINE Worker 只最後 --check。管理入口綁指定 NAS IPv4，公開 LINE 不掛受控業務檔案；新增專用私人媒體網路、照片代理 token 掛載及傳輸設定 JSON 持久化位置。

為使範本可用，fresh initializer 補六個獨立 token、NAS IPv4／可選 hostname SAN 及公開 CA 副本，並在更改權限／產生設定前拒絕非空檔案根目錄。已有標記安裝不補造憑證，不是 preserve-data 升級工具。本次沒有套用任何 NAS／既有 DB／資料卷，沒有建立新部署，沒有包檔、build、pull 或上傳映像。

PASS：以暫存 `.env` 無 CLI --profile 解析基本組加七個階段、組合 profile、必填值拒絕及隔離模型；24 項離線／隔離初始化和憑證測試通過；私人實際 HTTPS 8 組通過，最後以 LINE Worker CLI --check 驗證啟動及認證，不進 work cycle。初始化測試以暫存檔、合成 DB 公開 CA 及 stub base preparation 驗證，不宣稱 MySQL bootstrap 或 DSM 已通過。第一次 fixture 缺少 DB CA 副本，補齊 fixture 後重驗通過，沒有為此改 production 邏輯。架構 closure 零 errors／warnings；git diff --check／strict UTF-8／Python AST 通過。模型結果於 `scratch/nas-compose-gui-20261019/`。

NOT_RUN：DSM Container Manager 實機、ACL／來源限制／CA 匯入、NAS 2 GB 完整負載、真實 LINE／Cloudflare／provider、映像 build／push 與既有資料升級。新映像尚未交付，範本 NAS_IMAGE 刻意留白，不允許默默回退舊包。


### 本機新映像建置（2026-10-19 後續人工授權）

依使用者明確授權建置 `chris23144638/cecec:nas-secure-20261019`（linux/amd64），只載入本機 Docker，未 push／部署。以獨立 secret-filtered context 建置，3430 個檔案約 37 MB，包含當前 working tree；歷史 UI 由 HEAD 真實來源編譯，並非宣稱已部署的 rollback。修正 secure context 漏帶 mysql-client.cnf，輸出 .env.example 僅放外部交付目錄；補強 .env／token／套件登入檔排除並產生 context 專用 .dockerignore。沒有讀取或掛載既有 DB／業務資料卷。

PASS：排除規則 9 項；目前／歷史 UI 的 TypeScript 與 Vite build；前端 manifest／資產 digest；新映像在非 root、唯讀、無網路容器中檢查最新 source 五個 hash、fresh SQL 與初始化副本一致、UTF-8 MySQL 設定、必要模組載入、六身分宣告，應用／前端／setup 目錄無 .env、憑證或 token。沒有執行初始化、資料庫 bootstrap、登入／全應用 E2E、LINE work cycle 或 provider。

npm audit 回報 5 項既有開發依賴（3 critical、1 high、1 moderate），為 Vitest／mocker、happy-dom、tinypool 與 source-map-js；lockfile 均標示 dev，應用程式來源未引用這些套件，最終映像只複製編譯後前端，沒有 Node node_modules。未自動升級或 fix；此檢查不等於完整漏洞掃描。原始 audit 與 build metadata 位於 ignored scratch，只含依賴資訊，未收集實際部署帳密。

結果、image ID、context hash、公開 build metadata 及外部部署範本在 `scratch/nas-image-20261019-local/`。image_build=passed，image_published=false；NAS／DSM／外部服務仍 NOT_RUN。

### 五項 npm 告警修補與本機 r2 重建（2026-10-19 後續人工授權）

Authority：修正五項告警、保留原功能，驗證後重建本機 Docker 映像；不包入 `.env`、不 push、不操作既有資料。Vitest／mocker 鎖定 4.1.11、happy-dom 20.8.9、source-map-js 1.2.2；tinypool 隨 Vitest 升級移除。正式依賴完整 lock entries 未變，本機安裝與 secure current／previous 建置各自 audit 都為 0 告警。歷史應用原始碼保持；只有其他 manifest 事實及正式依賴鎖定身分相同時，才能共用修補後建置 manifests，否則拒絕產生 secure 包。

PASS：91 項登入／權限導覽／需求申請／檔案設定／履歷／客戶編輯測試、13 項打包與來源排除測試、TypeScript／兩版 Vite build、架構 closure 零 errors／warnings、git diff --check。Vitest 4 對 undefined spy 與 disabled fieldset 的行為較嚴格，僅補測試用對話框 mock，以及兩個按鈕及一個 PDF 選擇器的 ready 等待；保留全部原斷言，沒有修改業務 UI。新舊映像 current／previous 各三個實際 HTML／JS／CSS 資產 hash 完全一致。

FAILED（完整前端套件）：最後一次全量執行 1931 項，1819 passed、110 failed、2 skipped。110 項中 109 個相同失敗情境在升級前套件重現（其中 4 項等待訂金鎖情境的錯誤訊息不同，不能以此宣稱完整相容性通過）；新增的 1 項履歷 ready 時機已修正，包含在後續 91 項全通的 focused run。未重寫既有業務 oracle 或修正無關功能，不宣稱 full suite passed。其餘 DSM、NAS 負載、外部 provider 與完整應用 E2E 本輪 NOT_RUN。

PASS：本機映像 `chris23144638/cecec:nas-secure-20261019-r2`，linux/amd64，image ID `sha256:63b572853bfa7b80f857861fe24dca1af1cfb00db03ee4b15776fc31f21f981a`。隔離 context 3430 檔、無 `.env`／憑證／token，context hash `2bc2ffc1e580712d3bf351cb17f98bbabe6aefd96a80e3b71b031cf22adbcb11`；非 root、唯讀、無網路新容器驗證七個來源 hash、兩版前端 manifest、fresh SQL／副本一致及模組載入通過。沒有啟動初始化／DB／worker、掛載既有資料卷、部署或上傳。公開 build metadata 與外部 Compose 範本位於 `scratch/nas-image-20261019-auditfix-final/`；`.env.example` 只在映像外，NAS_IMAGE 仍由操作者在取得映像後填入。

### 前端失敗測試修復與建置停止門（2026-10-19）

最新 Authority：先修正測試，保留原功能、權限與業務驗證；正式程式若需要補功能先交人工確認。必要測試全部通過前不得建置／上傳映像，不得異動既有資料。上節 r2 的 PASS 僅代表當時 image build／靜態檢查完成，**不是應用驗收通過，也不是可部署或交付的版本**；本輪沒有重新建置、上傳或部署。

本輪修改 32 個既有前端測試檔：補齊單頁名冊的終止游標與新增唯讀依賴替身、合成登入前置條件、等待欄位／按鈕真正可操作、對應目前名稱與畫面步驟。分頁重複游標拒絕的共用 fixture 與 client 負向驗證未放寬；無效密碼／空白原因改驗 handler 不發送操作，仍保留原長度與原因限制。歷史排班仍驗證日期未完成時禁止建立、正式 Preview／Apply／回讀、導覽鎖定與原 idempotency key 重試。異常頁導航期待值依正式規格 06 §8 的 2026-10-16 退役裁決同步，導航清單完整性與唯一性檢查保留。沒有刪除測試，也沒有新增 skip／only／todo。

FAILED：完整前端執行 1931 項，1917 passed、12 failed、2 原有 skipped。其後只同步退役導航期待值，重跑 registry／retirement 兩檔 13 項全部通過；以每檔最後有效結果合併為 1918 passed、11 failed、2 skipped。此合併數字不是宣稱另一次完整全套執行。原先 109 個共同失敗情境已消除 98 個，其餘 11 個失敗斷言保留。完整與後續單檔輸出、任務前測試副本及摘要位於 `scratch/nas-test-repair-20261019/`。

| 尚未通過 | 數量 | 證據與後續確認範圍 |
|---|---:|---|
| Finance 同頁名冊 GET 預算 | 1 | `finance_entry_cutover.test.tsx` 期待一次、實際兩次。App 的 StaffIdentityProvider 及 FinancePage 各讀一次完整名冊。未將上限改成兩次；建議修正正式程式共用讀取，需人工確認後施工。 |
| 舊手動等待訂金鎖流程 | 7 | `order_workbench_v2_waiting_deposit_lock.test.tsx` 仍要求手動 Preview／Apply 按鈕、lock id 文案與 callback；目前正式規格 02 及推薦頁採自動保留。這些失敗不等於後端鎖定功能不存在。後續須把衝突、fingerprint／identity、重複建立與正式回讀檢查接到自動流程的適當驗證邊界，不能直接刪掉舊檢查換取通過。 |
| 歷史案件舊操作位置 | 3 | `order_workbench_v2_historical_drawer.test.tsx` 有一項仍在 Drawer 操作歷史帳務完成，目前入口移至 Finance；另兩項在重啟後期待舊獨立開始日面板，目前無指派案件使用日期工作區。須確認跨頁／日期工作區的驗證接法，保留 Query → Preview → Apply → 正式回讀及父層刷新檢查，不能直接略過後半段。 |

PASS：自動排班既有純記憶體後端單元測試 7 項；驗證 Query 不 enqueue、占用衝突不派送、確認不足不 Preview／派送、財務條件恢復後續辦、重複 discovery 使用同一正式命令、已有指派不重複套用、失敗命令不盲目重新入列。這 7 項不能冒充尚未通過的 7 項舊 UI 測試已完成遷移。

PASS：TypeScript noEmit、架構 closure（零 errors／warnings）、git diff --check、修改測試 strict UTF-8。比對任務開始時 1640 個正式程式與部署檔案 hash 全部未變；未改 DB 權限、schema、SQL、Compose、環境檔、正式 UI 或既有資料。既有環境不足項目仍維持 NOT_RUN，未以本輪單元測試宣稱 NAS／DSM、真實 LINE／Cloudflare 或完整 DB E2E 已驗證。

### 名冊共用讀取與現行流程驗證遷移（2026-10-19）

Authority：人工同意修正名冊重複讀取，並將另十項失敗接至目前自動流程、帳務頁與日期工作區；保留原功能、完整業務驗證，不放寬權限或刪除斷言。必要測試全通前不得建置／上傳，不操作既有資料。本輪沒有建置、上傳、部署或資料庫操作。

FinancePage 改用登入工作階段既有 StaffIdentityProvider 的名冊與刷新能力；仍保留獨立使用 FinancePage 時的既有查詢。名冊 GET 預算維持一次，手動刷新只增加一次名冊與一次帳務查詢；provider 出錯不另外發送查詢繞過錯誤。

等待訂金鎖測試改接實際自動狀態與日期工作區，保留占用衝突、日期阻擋、查詢未完成不寫入、重複操作及正式回讀檢查。fingerprint／命令身分／重複 discovery 的檢查放在實際負責派送的後端 owner 單元測試；另保留正式鎖定 writer 的衝突與無 hidden commit 驗證。歷史帳務完成改由實際 Finance 入口執行 Query → Preview → Confirm → Apply，再返回同一案件驗證新事實；歷史重啟後使用實際日期工作區，僅儲存開始日，不誤觸確認服務日期或案件補登 writer。完整前端執行另發現一個非同步焦點斷言時機問題，改等待原本相同焦點斷言，未更改 UI 行為。

PASS：後端 scheduling／waiting-deposit-lock 純記憶體單元測試 67 項；TypeScript noEmit；架構 closure 零 errors／warnings。完整前端一次執行為 1933 項：1930 passed、1 failed、2 原有 skipped；其中焦點失敗已修正並通過後續 focused run。遷移時補上目前實際成功文案的負向斷言後，最新四檔 focused run 為 53 項：51 passed、2 failed，無 skipped。這些是不同批次結果，不宣稱最新程式已完整全套通過。沒有新增 skip／only／todo。

FAILED／待人工確認：自動排班狀態回報 effective、但正式指派回讀為空或案件不一致時，MatchingScheduleAndAssignmentActions 雖會擋住父頁完成 callback，仍提前顯示「排班已生效，月嫂預留檔期已轉為正式班表。」兩個負向測試保留失敗，沒有刪減斷言。最小修正提案是等正式回讀一致後才發布成功狀態；已提出人工確認，本記錄時尚未套用該正式程式變更。

證據位於 `scratch/nas-test-completion-20261019/`：完整／focused JSON、67 項後端結果、typecheck、architecture closure、任務前檔案副本與未套用修正提案。正式程式目前僅 StaffIdentityProvider／FinancePage 兩檔變更；沒有修改 DB 權限、schema、SQL、Compose 或環境檔。先前 r2 映像仍不是已驗收版本；NAS／DSM、外部 provider、完整 DB E2E 與既有環境不足項目維持 NOT_RUN。

### 自動排班成功狀態修正（2026-10-20 人工確認）

人工明確同意前述最小修正。MatchingScheduleAndAssignmentActions 將自動排班狀態更新移到正式回讀驗證與完成 callback 之後，並再次確認元件未取消；正式回讀為空或案件不一致時，保留錯誤提示，不發布「已生效」狀態，也不通知父頁完成。未改權限、業務條件、API、資料庫或重試規則。

PASS：修正相關兩檔前端測試 16 項全通，包含原先兩個失敗的負向情境與成功回讀情境；TypeScript noEmit；架構 closure 零 errors／warnings。沿用未變動後端的 67 項有效單元測試結果。比對原先 1640 個正式程式／部署檔案，僅名冊 provider、FinancePage 與本次排班呈現三檔變更。完整前端重驗結果另記於下方。

PASS：修正後完整前端執行 1933 項，1931 passed、0 failed、2 原有 skipped，結果為 `frontend-full-fixed.json`；沒有新增 skip／only／todo，前述兩個正式回讀負向斷言均保留並通過。原有 skipped 為 Finance same-run source-review owner readback 與 MySQL Preview client／panel 情境，未以本輪測試宣稱其已執行。git diff --check 與本輪修改檔案 strict UTF-8 通過。

本輪授權的名冊修正與流程驗證遷移已完成；NAS／DSM、外部 provider、完整 DB E2E 與既有環境不足項目仍為 NOT_RUN。沒有建置、上傳映像或操作既有資料；即使本輪必要測試已通過，也沒有自行啟動後續映像建置。先前 r2 不包含本輪修正，不應作為本輪已驗收程式的映像。

### 修正後新映像本機建置（2026-10-20 後續人工授權）

Authority：使用者要求建置新的 Docker 映像，`.env` 不包入；延續僅本機、不上傳、不操作既有資料的邊界。建置前沿用完整前端 1931 passed／0 failed／2 原有 skipped、後端相關 67 項及型別／架構檢查通過結果，正式程式未再修改。

PASS：`chris23144638/cecec:nas-secure-20261020`，linux/amd64，本機映像識別 `sha256:33b4d0aa8c65526bc20e03eecb256dce83ed80e8f4934d932677789ea7cb1eda`。獨立建置 context 3430 個檔案、37,090,639 bytes，hash `b259457f52aad0fb5667ee30241d90f7e56f277c8449e429adaedcebb6cdbcb0`；7 項既有排除測試通過，實際 context 無 `.env`／私鑰／token 檔，九個最新來源檔核對一致。`.env.example` 僅置於映像外的部署資料夾，沒有讀取本機 `.env`。

PASS：目前／歷史兩版 TypeScript 與 Vite 編譯；Docker 建置成功並僅載入本機。用 UID/GID 1000、唯讀、無網路、無權限能力、只掛本次驗證檔的新短暫容器，驗證六個 runtime 來源 hash、兩版前端 artifact／source ref、fresh SQL 與初始化副本、UTF-8 MySQL 設定、必要模組載入及六服務身分。應用／前端／setup 目錄無 `.env`／私鑰／token 檔，runtime 無 Node node_modules；此驗證不代表一般 Docker 預設使用非 root，日常身分仍由 Compose 指定。

本次未啟動初始化、服務、DB bootstrap 或 LINE cycle，沒有使用既有資料卷、push、部署或修改 DB。NAS／DSM、實際負載、外部 provider 與完整應用 DB E2E 仍 NOT_RUN。完整 metadata、context hash 清單、建置及驗證結果位於 `scratch/nas-image-20261020-final/`；這次初始未完成的 context 位於 `scratch/nas-image-20261020-local/`，未用於建置，沒有刪除其他成果。部署 README 已指向新 tag；實際 `.env` 仍須在映像外準備。

### Docker Hub 上傳（2026-10-20 後續人工授權）

使用者明確要求上傳指定映像，不部署 NAS 或異動既有資料。上傳前兩次匿名 Docker Hub API 查詢均回報 `chris23144638/cecec` 的 `is_private=false`，原先私人倉庫要求因此暫停；使用者知悉 Public 狀態後明確同意繼續。未修改倉庫可見性、登入設定或 `.env`，沿用 Docker 既有認證。

PASS：本機映像識別與先前驗證結果一致；`docker push chris23144638/cecec:nas-secure-20261020` 成功。之後獨立從 Docker Hub 讀取 tag manifest，digest 為 `sha256:33b4d0aa8c65526bc20e03eecb256dce83ed80e8f4934d932677789ea7cb1eda`，與本機已驗證映像及 push 回報一致。上傳紀錄、遠端 manifest 與更新 metadata 位於 `scratch/nas-image-20261020-final/`。沒有重建映像、部署 NAS、啟動應用／資料庫、掛載既有資料卷或修改既有資料；原有 NAS／DSM／外部服務 NOT_RUN 狀態不變。

### 本機 Docker 測試資料卷清理（2026-10-20 人工授權）

使用者要求移除不再需要的本機資料。核對 Compose 來源、資料卷建立資訊與所有容器掛載後，移除 150 個已結束 NAS 隔離測試的 named volumes，以及 10 個經唯讀檢查確認只含 `lu_test_pr_runtime_*`／`lu_test_buffer_*` 測試庫的匿名卷。刪除前再次核對本機 desktop-linux 引擎、精確名稱、建立時間與沒有容器引用；使用指定名稱的 volume rm，沒有 prune 或 force。前述隔離環境的資料卷已結束保留，Compose、診斷與驗證紀錄仍留存，日後重驗須重新建立獨立測試環境。

PASS：160 個測試卷全部刪除；Docker 資料卷使用量由約 12.15 GB 降為 5.186 GB，清除約 6.96 GB 測試資料。原有 `labor_union_mysql-data`、Redis 匿名卷、三個既有容器及最新映像均保留，Redis 維持 healthy，未啟停 MySQL 或存取 NAS；沒有刪除專案來源、測試程式、映像或建置快取。限定清單、來源證據、刪除收據與事後核對位於 `scratch/docker-cleanup-20261020/`。

### Synology DDNS／Let’s Encrypt／DSM 內網入口（2026-10-20 人工授權）

使用者採用新入口並確認 NAS 尚未啟動，這次為新安裝；要求先確認映像、交付 Compose／`.env`／無 SSH 群暉步驟，管理介面只供內網且不動既有資料。沒有操作 NAS、登記真實網域、申請憑證、重建／上傳映像或連接既有 DB。

既有映像 `chris23144638/cecec:nas-secure-20261020` 可沿用：HTTPS、目前 Host／Origin 的首次 root 保護及相對路徑前端已具備。管理入口改由 DSM 公信憑證處理；考量 Docker <28 的 localhost 發布限制，Compose 移除管理 API 的 host ports，改用 management-egress 的固定 bridge subnet／API IP 作同機 DSM HTTPS 目的地，不增加代理容器。文件以 DSM 專屬來源 port 19443、管理子網域、內網 DNS、允許內網來源／其餘拒絕及防火牆限制完成部署路徑。內部 DB／Worker TLS、機器憑證、業務權限與所有應用程式碼不變。

安全範圍：瀏覽器到 DSM 使用公信憑證，無需每台電腦匯入專案 CA；DSM 到同機 Docker bridge 保留 HTTPS，但原生 GUI 未提供可據以確認的上游私人 CA 信任設定，沒有宣稱此段已驗證憑證鏈／名稱。這是本次明確交付限制，不能視作端到端上游驗證已完成；Worker／DB 既有 strict CA 驗證不變。DSM 公信憑證續期亦不會延長既有 90 天內部測試憑證效期。管理入口不經 Cloudflare Tunnel；原有 LINE 完整對外參數接線與 Worker 持續運作不在本次修改內。

PASS：已上傳映像的無網路、唯讀、非 root 隔離檢查 15 項，包含四個來源 hash、實際 HTTPS、代理 Host 含 19443、首次 root 記憶體替身寫入一次、異源／缺 Origin／重複建立與明文 HTTP 拒絕、實際編譯前端與 JS／CSS；未啟動任何真實資料庫。Compose 基本、七個單獨 profiles 與全部組合共九種解析通過，所有服務均無 host ports，固定 IP 與 subnet 一致，LINE Worker 仍只 --check。

PASS：映像原生 Linux 的部署與 root 契約兩檔共 39 項全通，保留全部情境。Windows 原始執行收集停滯後只停止本次兩個測試程序；關閉無關自動外掛後為 38 passed／1 failed（缺 Linux `/opt/nas/init/mysql-client.cnf`），未以刪斷言或放寬邏輯處理。改在既有映像執行並唯讀掛既有 pytest 工具與直接測試檔；補齊 py.py 與 Cloudflare 範本的測試掛載後，Linux 39 項全通，未安裝依賴或重建映像。架構 closure 零 errors／warnings。GUI DSM 實機、LAN／WAN／IPv6 隔離、DNS、Let’s Encrypt／續期及實際檔案傳輸均為 NOT_RUN，須依手冊驗收，不冒稱已部署。

Source of truth 為 `deployment/nas/compose.yaml`、`.env.example`、`README.md`，formal 18 §2.1 與 runtime-supervision leaf 已同步入口事實。交付為 `scratch/nas-dsm-ddns-20261020-delivery/compose.yaml`、`.env`、`README.md`；必要值、未使用網段檢查及 DSM 逐步操作皆在檔內。隔離結果與任務前副本在 `scratch/nas-dsm-ddns-20261020-validation/`。沒有讀取實際本機 `.env`、覆寫既有成果或留下測試資料卷。

### DS220+ 正式 Compose 與維護演練（2026-10-20 人工授權）

Authority：使用者要求正式 Compose 統一為目前 NAS 可用版本，補齊重啟、保留資料重建、更新與回復流程，先用隔離環境驗證；不操作 NAS 上既有資料，測試通過前不打包或上傳。本輪沒有建置／上傳／NAS 操作，也未修改真實 .env 或日常應用程式。

正式 `deployment/nas/compose.yaml` 與 NAS 手上 `scratch/nas-dsm-ddns-20261020-security-diagnostic/compose.yaml` 的解析模型完全一致：移除不支援的 NanoCPUS，保留原記憶體、掛載、TLS、權限與 profiles；data 引用原專案既有 internal 網路，Compose 不回收它。選用 Tunnel overlay 亦移除 NanoCPUS。.env.example 區分新安裝與既有安裝；README 補上限定專案的停止／依賴順序啟動、保留資料強制重建、無 DB 變更換版、失敗回復、冷備份命令及新空卷還原程序。DB migration 仍走既有正式 gate，不重跑 fresh schema、不將映像回退誤稱 DB 回滾。

PASS：34 項相關 NAS 靜態／單元測試；1 項真實 Docker 整合測試，七個順序階段全部通過，最終約 4 分 15 秒。root／工會測試帳號由 HTTPS API 建立，完成 MFA；原 session、root-only 帳號中心、setup 關閉、帳密 hash、MFA ciphertext、私人憑證／設定及四個檔案根目錄的測試內容，在停止再啟動、強制重建及 tag→digest 套用後保留。故障注入讓候選 API 退出 17，套用命令確實回報失敗；還原原配置後服務恢復。全部 writer 停止且 MySQL 正常退出後，完整冷備份到獨立目錄，再還原至另一組新卷／新檔案目錄；原 root 與工會帳號的實際 TOTP 登入及檔案回讀通過，API→Redis PING 亦通過。

本機 Windows 的舊離線 initializer fixture 依賴 Linux /opt、/app 資產而失敗，改由 fixture 明確提供容器資產及可核對的 chown 呼叫；保留原不可覆寫與 hash 比較斷言，另補字元集檔內容與檔案根目錄 UID 1000 指派斷言，沒有修改正式 runtime 或放寬業務／權限驗證。新增 opt-in lifecycle test 與 container probe 歸既有 runtime-supervision Module root，預設不啟動 Docker。

PASS：全部 profiles 解析、正式／NAS handoff 模型相等、記憶體與無 host ports／build／CPU 配額檢查、備份 shell 的 UTF-8／LF 語法與既有映像 GNU tar 可用性檢查。去敏整合結果位於 `scratch/nas-lifecycle-bf45b9c64f/result.json`，兩組測試容器均已停止，測試卷與冷備份保留供查核；沒有全域 prune、刪除舊卷或存取既有 DB。

限制／NOT_RUN：沿用既有應用映像 `sha256:33b4d0aa8c65526bc20e03eecb256dce83ed80e8f4934d932677789ea7cb1eda`，tag→digest 不涉及不同程式碼版本，不代表未來版本或 schema migration 相容性已驗證。NAS Container Manager undefined、DSM 特有 ACL、防火牆、2 GB 容量、整機開機及真實外部 LINE／Cloudflare 收送均未由本機 Docker 演練替代；NAS 真實資料、網路與入口不變。先前已交付 scratch 包保留歷史原樣，後續維護唯一來源改用正式 deployment/nas 文件。

最後檢查：本次十個檔案 strict UTF-8／空白與 scoped git diff --check PASS。架構 closure 在較早快照為 PASS；最終全工作區執行為 FAILED，唯一原因是本次開始時未在 dirty 清單、亦不在本次 write set 的 `ui_react/src/tests/client_beclass_workbook_client.test.ts` 出現 `TEST_OUTSIDE_ARCHITECTURE_OWNER`。未改寫、搬移或刪除此其他成果，也未將較早快照冒充最終工作區全通過；這不改變上述本機 NAS 隔離演練 PASS，但全工作區架構 gate 尚未完成。
