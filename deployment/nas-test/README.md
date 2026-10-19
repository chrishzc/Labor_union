# NAS 輕量登入測試包

用途：DS220+／2 GB 的隔離試跑。只開登入模式；先測管理介面與資料庫；LINE Worker 最後只檢查啟動與認證，不執行收件／投遞工作。本包不等於正式上線，不自動開外網或操作既有資料庫。

前提：NAS 要支援 **Docker Compose v2**，以 `sudo docker compose version` 確認。若只有舊版 `docker-compose`，先確認 DSM／Docker 套件版本，不要直接替換指令套用。

## 第一次使用

1. 將測試包解壓到 NAS 專用資料夾，例如 `/volume1/docker/lu-nas-preview`，不要放進既有 MySQL 資料目錄。
2. 若包含 `app-image.tar`，在 Container Manager 的映像匯入，或執行 `sudo docker load -i app-image.tar`。若尚未附映像，依下方建置說明在電腦完成；NAS 不需要編譯。首次啟動 MySQL／Redis 仍會從 Docker Hub 下載官方映像；映像的磁碟大小不等於運行時記憶體。
3. 透過 NAS SSH 進入這個資料夾，依序執行：

```sh
sudo sh nas.sh prepare
sudo sh nas.sh database
sudo docker compose ps
```

`prepare` 產生隨機密碼、MFA 加密金鑰、90 天測試 TLS 憑證與持久化目錄，不輸出秘密；設定／資料已存在就拒絕覆寫。MySQL 只在**新測試資料卷第一次啟動**匯入 hash-bound current fresh schema。不要用歷史 release SQL 替換 `init/10-fresh-schema.sql`。

等待資料庫 healthy；首次初始化可能超過數分鐘。再建立管理員、啟動 API：

```sh
sudo sh nas.sh admin
sudo sh nas.sh start
sudo sh nas.sh status
```

管理員密碼互動輸入，不寫在指令或設定檔；至少 16 字元，已存在 root 時拒絕覆寫。首次登入須完成 MFA 綁定。`settings` 包含秘密，應限制權限並另做安全備份；不要傳回聊天、上傳 Docker Hub 或納入 Git。

預設僅發布 **NAS 自己的 127.0.0.1:18080**。在工會電腦保持以下 SSH 通道開啟：

```sh
ssh -N -L 18080:127.0.0.1:18080 你的NAS帳號@NAS內網IP
```

再於工會電腦瀏覽器開啟 `http://127.0.0.1:18080/admin/`。此處 HTTP 僅走兩端 loopback，跨設備傳輸由 SSH 加密；它不是公開網站 HTTPS 部署。用完可停止通道並依原設定關閉不需要的 SSH。不要把 `NAS_BIND_IP` 改成 `0.0.0.0` 或對外轉發。

## 測試順序

1. **基線**：啟動前記錄 DSM CPU、可用記憶體及交換空間。
2. **資料庫**：確認 db／redis healthy；MySQL 無 host port；API 以 CA 與 `db` 名稱驗證 TLS。啟動會唯讀核對 current tables/views；runtime 帳號無 DDL/TRIGGER 權限，trigger 的 runtime metadata 不在這項查核範圍。
3. **登入與基本操作**：未登入 API 應拒絕；登入＋MFA 後查詢與少量操作可用。空資料畫面是合法結果。沒有合成業務資料的功能請標 `NOT_RUN`，不要連正式資料補測。
4. **較重功能**：一次只測一份合約 PDF 或小量匯入。有些操作需要額外背景 worker；本包不啟動它們，排隊中不能當成完成。缺少模板／資料時同樣標 `NOT_RUN`。
5. **資源／重啟／備份**：記錄 `sudo sh nas.sh status`；測 `sudo docker compose restart api` 後重新登入、確認先前測試資料仍在；資料庫備份與獨立還原另外驗證，未做不得標通過。
6. **外網**：本包未配置 Cloudflare／VPN，先標 `NOT_RUN`；如另行配置，核對管理授權與 `/internal` 等私有入口未對外開放。
7. **最後才檢查 LINE Worker**：見下一節；不執行正常輪詢、不使用 `--once`。

## LINE Worker：最後只檢查啟動

```sh
sudo sh nas.sh line-check
```

它只呼叫無工作副作用的 Private API 認證握手，成功後退出；不呼叫 `run_line_cycle`。本包沒有一般 LINE worker 服務。預設 `settings/line-oidc.json` 是空設定，**檢查預期會 blocked**，直到部署者提供合法 Google OIDC 服務身分：

- 用戶端依現有 `fetch_id_token` 契約，將可簽發 ID token 的服務帳號設定安全地放在該檔，保留只有 UID 1000 能讀取的權限；不要把內容貼到聊天或放入映像。
- 在 `settings/app.env` 設 `INTERNAL_SERVICE_OIDC_ALLOWED_CALLERS=line-worker=實際服務帳號email`。
- API 與 worker 的 audience 必須一致；修改後以 `sudo docker compose up -d api` 重建 API，再檢查。
- 不以開發 shared key、免登入或偽造 token 代替。缺少身分時，記為 `BLOCKED`；不影響前面管理介面測試。

## 調高資源

將同一資料夾的 `limits.env.example` 複製為 `.env`，可逐項調整（不放秘密）：

```dotenv
API_CPUS=0.50
API_MEMORY=768m
API_CONCURRENCY=8
MYSQL_CPUS=0.50
MYSQL_MEMORY=512m
REDIS_CPUS=0.10
REDIS_MEMORY=64m
LINE_CPUS=0.10
LINE_MEMORY=128m
```

變更後執行 `sudo docker compose up -d api db redis`。一次只調一項，再重測。CPU 上限可增加延遲；記憶體過低會 OOM 終止。API 並行超限會回 503，不會保證無限排隊；瀏覽器同時載入資源被拒絕時先減少操作或調高並行值。資料庫完整初始化也可能需要暫時較高上限，不要因初始化失敗就刪資料卷重來，先查看日誌及原因。

停止：`sudo sh nas.sh stop`。**不要使用 `down -v`、刪除資料卷或重新指向既有 MySQL volume。** Redis maxmemory 為 32 MB、採 noeviction，超限應回報錯誤，不會靜默丟棄資料。保留 MySQL 原本交易持久性設定。

## 電腦上重新建置

在原專案執行 `python -m scripts.package_nas_preview --output scratch/新的目錄`，依該目錄的 `bundle.json` 傳入三個 build arguments：`SOURCE_REF`、`PREVIOUS_SOURCE_REF`、`API_REVISION`。對該目錄的 `build-context` 執行 `docker build --platform linux/amd64 ... -t labor-union-nas-test:local build-context`。再執行 `docker save -o app-image.tar labor-union-nas-test:local`，連同 Compose／init／說明移至 NAS。

映像包含目前工作區程式（包括既有未提交程式），不含本機 `.env`、憑證、資料庫實體檔。previous React 是從實際 Git revision 重建，並非已部署版本的回復驗收。兩份 artifact 不可相同；若前端未改變，需選擇真正不同且相容的歷史版本，不可改 hash 偽造。未推送 Docker Hub；若未來使用，先檢查內容並使用私有倉庫與固定 digest。
