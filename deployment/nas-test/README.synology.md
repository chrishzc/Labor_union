# 群暉 Container Manager 測試包（不啟用 SSH）

沿用已下載的 `chris23144638/cecec:nas-test-20261016`，不需重建或重新上傳映像。這個小包只有部署設定與原版空白資料庫初始化檔，沒有密碼、憑證或正式資料。需要具備「專案」功能的 Container Manager；不同版本的按鈕文字可能略有差異。

## 1. 放置檔案

用 File Station 解壓到獨立資料夾，例如 `/volume1/docker/lu-nas-preview`。確認結構如下，不要多包一層資料夾：

```text
lu-nas-preview/
  01-prepare/docker-compose.yml
  02-app/docker-compose.yml
  03-line-check/docker-compose.yml
  settings/                       ← 一開始必須是空資料夾
  init/10-fresh-schema.sql
  init/20-restrict-app.sql
  init/99-ready.sh
  runtime/nas_test_runtime.py     ← 啟動檢查修正，唯讀掛入原映像
```

若解壓後沒有 `settings`，在 File Station 手動新增同名空資料夾。三個專案必須留在這個共同上層目錄，不能各自搬到不同地方。

本包沿用原測試包的 `lu-nas-preview-*` 資料卷；只適用尚未初始化的新測試。若已執行過原版 `prepare`，或已有同名專案／資料卷，先不要再啟動初始化，也不要刪資料，需另行確認既有狀態。不操作現有正式 MySQL。

本機整合驗證修正了原映像啟動檢查的一處 cursor 資料列格式錯誤；小包中的 `runtime/nas_test_runtime.py` 會以唯讀方式掛入相同位置，其他程式沿用原映像。不能省略這個檔案，也不需重新上傳映像。它仍強制 production／登入及 MySQL 伺服器憑證驗證，沒有停用 schema gate。

測試入口只啟用管理功能：移除原 LINE 子路由、`api.routes.line_*` 路由及 `/api/line/`、`/api/v1/line/`、`/webhook` 入口，保留管理員登入／MFA、其他管理 API 與 Private API。這些 LINE 頁面／Webhook／LIFF 本次不提供服務，也不需要拿假 LINE 金鑰滿足正式 LINE 啟動檢查。最後的 LINE Worker 僅走 Private API 的 `--check`，不代表 LINE 功能已上線；正式整合需恢復完整入口並完成真正的 LINE 設定與另一次驗收。

Docker Hub 必須維持 Private。映像頁面應已看到完整名稱與 `nas-test-20261016` 標籤。倉庫登入使用唯讀存取權杖；不要將權杖填入 Compose。MySQL、Redis 尚未下載時，主專案會下載官方映像。不要覆寫這個應用映像版本標籤。

應用容器設定為只用已下載的映像，不自動更新或重新下載；若出現找不到映像，請先在映像頁面核對完整名稱與標籤，不要改成其他版本或 `latest`。

## 2. 一次性初始化專案

Container Manager →「專案」→「新增／建立」：

- 專案名稱：`lu-nas-preview-prepare`。
- 路徑：`/volume1/docker/lu-nas-preview/01-prepare`。
- 來源：使用現有 Compose；若只有「上傳 docker-compose.yml」，上傳本包 `01-prepare` 中的檔案，路徑仍選上述目錄。
- 不設定 Web Station 網頁入口；完成後啟動專案。

在容器清單開啟該專案的 `prepare` 容器，查看日誌。成功會出現：

```text
Preview settings prepared. No secrets printed. TLS certificates expire in 90 days.
```

容器以退出碼 0 結束後顯示「已停止」是正常結果；它不是常駐服務，不要反覆按啟動。若非 0 或沒有成功訊息，先停止流程，查看日誌，不要重設資料卷。

初始化容器不連網，不開任何埠，僅暫時使用 root 建立權限及隨機密碼。常駐 API 仍以非 root 執行。`settings` 由 root 限制權限，File Station 可能無法直接瀏覽；不要為此放寬成所有人可讀。資料庫 TLS 測試憑證有效 90 天；到期後需更新，不能關閉驗證繞過。

## 3. 主專案

回到「專案 → 新增／建立」：

- 專案名稱：`lu-nas-preview`。
- 路徑：`/volume1/docker/lu-nas-preview/02-app`。
- 使用／上傳 `02-app/docker-compose.yml`。
- 不設定 Web Station 網頁入口，完成後啟動。

主專案只包含 `db`、`redis`、`api`，不包含一般 LINE Worker。前端由 API 提供，沒有額外前端伺服器。首次資料庫初始化可能需要數分鐘，等待資料庫、Redis 及 API 健康檢查通過；只有「執行中」不能當成通過。

新版匯入檔在原版 SQL 前加入 UTF-8 連線設定，避免中文種子資料被誤解碼；權限設定從原本 shell here-document 轉成相同 SQL，不改資料表、規則或種子值。最後一步才寫入資料卷內的初始化完成標記；匯入中途失敗不會因 MySQL 能回 ping 就顯示健康。不會自動修補先前失敗或既有資料卷。

| 容器 | CPU 上限 | 記憶體上限 |
|---|---:|---:|
| db | 0.50 核 | 512 MiB |
| redis | 0.10 核 | 64 MiB |
| api（含前端） | 0.50 核 | 768 MiB |
| 最後的一次性 line-check | 0.10 核 | 128 MiB |

這些是限制值，並非實測最低需求。上限不保證不會 OOM，NAS 系統也需要記憶體。首次初始化若失敗，先查看容器日誌及 DSM 記憶體，不刪資料卷重試。在主專案的 YAML 編輯器調整對應 `mem_limit` 或 `cpus` 後重新部署，一次只改一項。API 並行限制預設 8，超過會回 503，並非無限排隊。

## 4. 建立第一個管理員（使用介面內建終端機）

API 健康後，在「容器」選取主專案的 `api` →「動作 → 開啟終端機」。建立新的 bash／sh 終端機，不要附加到 API 的主要程序。在這個瀏覽器內的終端機只需輸入一次：

```text
python -m scripts.nas_test_runtime bootstrap-admin
```

依提示輸入帳號與兩次密碼（至少 16 字元）。密碼不回顯，不要加在指令後面、不放環境變數、不截圖傳送。看到 `Administrator created` 才算完成。已存在管理員時會拒絕覆寫；這不是密碼重設功能。

這是 Container Manager 的容器終端機，不是 SSH，也不需開啟 NAS SSH。仍需要輸入上面這一行；本包沒有新增免登入的網頁管理員註冊入口。使用 HTTPS 登入 DSM 操作此終端機；若瀏覽器終端機不可用，先解決 DSM／WebSocket 連線，不改用明文密碼檔。

## 5. 用 DSM HTTPS 反向代理取代 SSH 通道

API、MySQL 與 Redis 都不發布 NAS 連接埠。瀏覽器透過 DSM 內建的反向代理進入，DSM 直接連到同台 NAS 的 API 容器 bridge IP，不增加代理容器。舊版 Docker 對發布到 localhost 的埠有同網段隔離限制，因此 GUI 版也不發布 `127.0.0.1:18080`；不要自行加入 `ports`。

1. 先固定工會電腦與 NAS 的內網 IP。
2. 準備一個會解析到 NAS 內網 IP 的名稱，以及瀏覽器信任、名稱相符的伺服器憑證。可沿用 NAS 已有的合適憑證／名稱；內部 CA 則需先在工會電腦安裝受信任 CA。沒有此條件時，此步記為 BLOCKED，不改用內網明文 HTTP 或忽略憑證警告。
3. DSM「控制台 → 登入入口 → 進階 → 存取控制設定檔」，新增專用設定檔：第一條允許工會電腦的單一 IP（IPv4 /32），後面拒絕所有其他來源；IPv6 也不要另留允許全部。只套用在新網站，不改動既有 DSM 管理入口。
4. Container Manager 的 API 容器「詳細資料／網路」查看在 `lu-nas-preview-app` 網路上的 IPv4 位址，記下它；這是 Docker 內部位址，不是 NAS 內網 IP，也不是 MySQL 的 IP。DSM「反向代理伺服器 → 新增」，填寫下表，套用上述存取控制設定檔。不要勾選任何自動建立路由器轉發的選項。

| 欄位 | 設定 |
|---|---|
| 名稱 | `union-preview` |
| 來源通訊協定 | HTTPS |
| 來源主機名稱 | 你準備的 NAS 內網名稱 |
| 來源連接埠 | `18443`（先確認沒有其他服務使用） |
| 目的地通訊協定 | HTTP |
| 目的地主機名稱 | 剛查到的 API 容器 IPv4 位址 |
| 目的地連接埠 | `8080` |

5. DSM「控制台 → 安全性 → 憑證 → 設定」，為 `union-preview` 指派名稱相符的憑證。來源必須是 HTTPS，目的地 HTTP 僅走 NAS 自己的 Docker 虛擬網路。
6. NAS 防火牆針對 TCP `18443`，允許工會電腦 IP，接著拒絕其他來源；規則必須放在既有寬鬆允許規則之前，並核對使用中的網路介面／設定檔。不要封鎖既有 DSM 管理埠，不需開放 3306、6379、18080。不設定路由器埠轉發、UPnP、自動外網入口或 Cloudflare。
7. 工會電腦開啟 `https://你的NAS內網名稱:18443/admin/`，確認憑證無警告，再登入並綁定 MFA。管理員帳號與 DSM／Docker Hub 帳號各自獨立。

來源 IP 是網路限制，不能取代帳號、密碼與 MFA；本包不承諾同網段攻擊者無法冒用 IP。需從另一台未允許的內網裝置驗證拒絕，才可將來源限制標為通過。

API 重建或重新部署後，內部 IP 可能改變；請重新核對並更新反向代理目的地。出現 502 時先檢查 API 健康與此 IP，不以發布 API 埠或停用 TLS 解決。NAS 自訂 Docker 路由／防火牆也會影響隔離，需確認其他內網裝置不能直接連到容器 IP:8080、3306 或 6379；未驗證前不宣稱隔離通過。

## 6. 測試順序與停止

1. 記錄啟動前及啟動後 DSM CPU、記憶體、交換空間；容器頁面看統計資料。
2. 核對 db／redis／api 的健康狀態、資料庫 TLS 啟動檢查。空白測試庫沒有正式業務資料。
3. 確認未登入無法存取管理 API；登入與 MFA 後做少量查詢／操作。
4. 需要時一次測一份 PDF 或小量匯入；額外背景 worker 未啟動的工作不能以「已排隊」當完成。缺資料／模板的項目標 NOT_RUN。
5. 在容器頁面重新啟動 api，確認仍可登入及測試資料仍存在；備份／獨立還原未做就標 NOT_RUN。
6. 最後才考慮建立 LINE 檢查專案，見下一節。

停止使用主專案「停止」即可。保留初始化專案為已停止狀態。不要選清除／刪除資料卷、不要以重新初始化解決密碼錯誤。

## 7. LINE Worker 最後只檢查啟動

本包預設沒有 Google OIDC 服務身分，這項先記為 BLOCKED，不影響管理介面測試，也不必建立第三個專案。不得為了通過改成 shared key 或免登入。

已另外完成安全的 OIDC 設定且 API 健康後，才建立專案 `lu-nas-preview-line-check`，路徑選 `03-line-check`，使用該資料夾的 Compose。必須保留主專案的 `lu-nas-preview-app` 網路名稱；主專案需持續執行。

它只執行 `--check`，認證成功後退出 0；不輪詢、不收件、不投遞 LINE 訊息。缺少設定時非 0 結束是預期的 BLOCKED，不要反覆重啟或改成一般 LINE Worker。第三個專案沒有自動重啟。

OIDC 需由部署者另行提供合法的服務身分、API caller allowlist 及一致 audience；不隨本包附帶，也未在 NAS 驗證。

## 驗證範圍與來源

本包不含映像 tar，不會把你的私人倉庫改成公開，也不會連線 NAS 自動設定。來源映像及初始化 schema 沿用原版測試包；新包的本機驗證結果見同包 `verification.json`（若有）。NAS 實機介面、DSM HTTPS／來源限制、登入／MFA、備份還原需依上述順序實測，未做不得宣稱通過。

- 群暉專案：https://kb.synology.com/sv-se/DSM/help/ContainerManager/docker_project?version=7
- 群暉容器與內建終端機：https://kb.synology.com/index.php/th-th/DSM/help/ContainerManager/docker_container?version=7
- DSM 反向代理與來源存取控制：https://kb.synology.com/index.php/th-th/DSM/help/DSM/AdminCenter/system_login_portal_advanced?version=7
- Docker 埠發布及舊版 localhost 限制：https://docs.docker.com/engine/network/port-publishing/
