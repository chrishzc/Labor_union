# Windows 遠端入口

## Windows 統一管理入口（目前操作方式）

日常雙擊專案根目錄的 **`Windows管理.bat`**。選單提供啟動全部、停止全部、套用更新／整組重啟、只更新前端、狀態／版本、備份資料庫、安全升級資料庫、復原資料庫備份、首次安裝程式依賴及檢查程式環境；不再顯示「產生部署包」。關閉選單不會停止背景服務；離開前或切換主機前，請明確選「停止全部」。

資料庫操作集中在 **6 備份、7 安全升級、8 復原備份**，委派同一套 NAS 維護工具，保留中文確認、獨立正式機設定及原庫保留流程。備份可在線上進行；升級／復原若偵測到本機服務仍在執行，會要求先選「2 停止全部」，不自行停止或重啟服務。每日備份時間仍在「稽核與系統 → 資料庫備份」設定，預設 18:00。設定與復原限制見 [NAS 維護操作說明](README.md#nas-正式資料庫備份升級復原)。

| 用途 | 固定入口 |
|---|---|
| 本機操作 | `http://localhost:5173/admin/` |
| 遠端操作 | `https://chrishzc.com/test/` |
| LINE Webhook | `https://line.chrishzc.com/webhook/line` |

本機 `/admin/` 與遠端 `/test/` 由同一個 loopback 5173 Gateway、同一份不可變 artifact 提供；本機畫面也使用該 artifact 的 `/test/` 資源與 API。`/admin/` 別名只接受 localhost／127.0.0.1 Host，不公開成額外遠端入口。網站帳密、MFA、權限驗證保留，API 8000 仍只綁 loopback。

啟動全部會先建置前端、唯讀檢查 DB current schema、啟動既有 Redis，再交給原 supervisor 啟動 API、前端、Tunnel、monitor、durable／incident workers，以及原設定啟用的 LINE／knowledge workers。遠端連線不會停用背景工作或推播。資料庫、帳號與檔案由操作者準備，不自動初始化、遷移、清空或換庫。

「套用更新／整組重啟」針對已放到本機的新版程式：先建置成功，再整組停止並重啟，因此會套用你修改的設定。它不會自行 Git pull、下載其他版本或同步其他主機；依賴清單改變時，先停止、執行安裝依賴，再啟動。「只更新前端」保留 API／workers／Tunnel 的原程序並有前端失敗回復。完整更新若新後端啟動失敗會明確報錯，不宣稱自動回復整個後端；保留原程式版本以人工回復。

一般管理、檢查、建置、封裝與前端更新不解析或改寫 `.env`。只有明確選擇資料庫升級／復原，才由 NAS 維護工具在確認與副本驗證後切換資料庫設定。完整啟動／重啟時，原應用程式及其既有 preflight／supervisor 正常載入自己需要的設定；不把設定值輸出到管理選單或部署包。正常背景工作仍可能處理真實待辦與推播，測試驗證不另外建立訊息。

命令列同樣只有根目錄入口：

```powershell
.\Windows管理.bat -Action start
.\Windows管理.bat -Action stop
.\Windows管理.bat -Action update
.\Windows管理.bat -Action frontend
.\Windows管理.bat -Action status
.\Windows管理.bat -Action check
.\Windows管理.bat -Action database-backup
.\Windows管理.bat -Action database-upgrade
.\Windows管理.bat -Action database-restore
.\Windows管理.bat -Action package
```

`start` 預設包含 Tunnel；缺少 token 或 cloudflared 即報錯。明確只供地端使用時可加 `-LocalOnly`，背景工作仍正常啟動。`check` 僅查程式與工具路徑，不讀設定、不連 DB 或外部平台，不代表 DB、登入、推播或 Tunnel 已通過實際驗收。完整停止需要同一 Windows 使用者、相符的專案路徑與 PID／native start time；身分或清理無法確認就拒絕切換，絕不按埠或全機程序名稱強制終止。

### 搬到另一台 Windows

1. 維護人員在有 Git 的開發主機執行 `Windows管理.bat -Action package`（已移出日常選單）。輸出於 `scratch/windows-remote/packages/windows-*.zip`；包內 `windows-release.json` 記錄程式檔案雜湊與 release ID。這是目前工作目錄的程式來源包，包含尚未提交但符合既有 source 過濾規則的程式變更；不是已發布的 Docker 映像，也不複製本機虛擬環境。
2. 在新 Windows 解壓縮到獨立資料夾。安裝 Python 3.14（含 `py` launcher）、相容專案的 Node.js／npm、Docker Desktop 及原生 cloudflared。開發用程式包不包含這些工具；不要把舊機 `.venv` 或 `node_modules` 搬過去。
3. 雙擊管理入口，選「首次安裝程式依賴」；它建立本機 `.venv`、依 `requirements.txt` 安裝 Python 套件、`npm ci` 及 Playwright Chromium。此步驟需要網路，不安裝或更改 Cloudflare／Docker／DB 設定。
4. 由你準備該機自己的 `.env`、資料庫／current schema、帳號、檔案根目錄及 LINE Channel 設定。部署包排除 `.env*`、金鑰、token、ignored 檔案、資料與執行紀錄，不是備份／資料搬遷包。
5. 按下節人工放置共用 Tunnel 的 token。舊主機先選「停止全部」，確認整組停止及 Cloudflare 舊 connector 離線後，才在新機選「啟動全部」。

各主機資料與帳號獨立；網址相同不代表資料同步。切換主機後可能需要重新登入。共用 Tunnel token 可以同時建立多個 connector，**沒有自動跨主機互斥**；不能只停 Tunnel 而讓舊機背景工作繼續跑。共用網址的主機需配置相符的 LINE Channel 才能接收相同 Webhook。其他主機下一次啟用前，人工部署相同 release。

### Cloudflare Tunnel 純人工設定

以下全部由人員在 Cloudflare 後台與 Windows 操作；管理入口不呼叫 Cloudflare 帳戶 API、不更改 DNS／Access／Worker。既有設定正確時只核對，不另建重複 Tunnel，不改 `chrishzc.com` 原根 DNS／`personal web` Tunnel。

1. 在 Cloudflare 後台 **Networking → Tunnels**（部分介面位於 Zero Trust → Networks → Connectors）選既有 **`labor-union-windows`**。所有 Windows 共用此 Tunnel；若是全新環境才先建立這個 remotely-managed Tunnel。安裝原生 Windows cloudflared，程式可從 PATH 或 `C:\Program Files (x86)\cloudflared\cloudflared.exe` 找到。**不要執行安裝指令中的 `service install`**；由管理入口啟停 connector，避免獨立 Windows 服務在另一台啟動後仍自動連線。[官方建立步驟](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)
2. 在 **Zero Trust → Access controls → Applications** 建立／核對同一個 Self-hosted 應用，包含 `chrishzc.com/test` 與整個 `lu-windows-origin.chrishzc.com`，保護 prefix 及其全部子路徑。Allow policy 只列你指定的完整 Email，登入方法使用 One-time PIN；不要加入 Everyone／Bypass。記下應用 AUD 與 team domain 的名稱（目前為 `chrishzc`）。保留網站本身帳密與 MFA。[官方 Access 步驟](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
3. 在 Tunnel 的 Routes／Published application routes 核對下表；Path 保留前綴、不 strip，未匹配回 404。不用 5174 分流。管理路由的 Additional application settings → HTTP Host Header 設為 `chrishzc.com`，Access 驗證設為 required、team `chrishzc`、AUD 填上一步該應用的值。Webhook 路由 Host Header 設為 `line.chrishzc.com`，**不啟用人員 Access JWT 驗證**。[官方 origin 設定](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/origin-parameters/)

| Hostname | Path（正規表示式） | Service |
|---|---|---|
| `lu-windows-origin.chrishzc.com` | `^/test(/.*)?$` | `http://127.0.0.1:5173` |
| `line.chrishzc.com` | `^/webhook/line/?$` | `http://127.0.0.1:8000` |

4. 原根網站已使用另一條 Tunnel，所以在 **Workers & Pages** 核對／建立 `labor-union-windows-path`，貼上 `deployment/windows-remote/path-router.mjs` 的 module 程式。Routes 只設 `chrishzc.com/test` 與 `chrishzc.com/test/*`，關閉 workers.dev 與 preview URL。它轉送到上表受保護 origin；原根網站其他路徑保留。origin 與 LINE DNS 使用 proxied CNAME 指向本 Tunnel 的 `<Tunnel UUID>.cfargotunnel.com`；後台建立 published route 通常會自動建立，請確認沒有重複記錄。不要把原根 DNS 改指這條 Tunnel。
5. 在 Tunnel 的安裝／新增 connector 畫面，人工取得安裝指令最後的 **Tunnel token 本身**（不是整串命令、不是帳戶 API key）。每台主機個別建立受限目錄與檔案；在專案根目錄以 PowerShell 執行以下命令，然後在記事本貼上 token，儲存為無副檔名 `tunnel-token`、UTF-8，不要貼進命令列、Git、聊天或 `.env`。只在你自己的電腦操作，不需提供 token 給 Agent。

```powershell
$tunnelFolder = Join-Path (Get-Location) 'scratch\windows-remote\cloudflare-state'
New-Item -ItemType Directory -Path $tunnelFolder -Force | Out-Null
$tunnelUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
icacls $tunnelFolder /inheritance:r /grant:r "${tunnelUser}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F'
notepad (Join-Path $tunnelFolder 'tunnel-token')
# 儲存後，確認檔名沒有被加上 .txt，並限制檔案本身的權限：
icacls (Join-Path $tunnelFolder 'tunnel-token') /inheritance:r /grant:r "${tunnelUser}:F" 'SYSTEM:F'
```

管理入口以 `cloudflared tunnel --no-autoupdate run --token-file <檔案路徑>` 啟動，token 值不放在命令參數。持有此 token 的人可以啟動該 Tunnel，請另外保管，不隨程式部署包配送。[官方 token-file 參數](https://developers.cloudflare.com/tunnel/reference/run-parameters/)

6. 確認舊主機整組停止，再選「啟動全部」。在 Cloudflare 檢查新 connector Healthy；用瀏覽器開 `https://chrishzc.com/test/` 完成指定 Email PIN、原網站登入與 MFA。`Cloudflare Tunnel: running` 只代表本機程序存活，不能代替這一步。
7. LINE Developers 的 Webhook URL 固定填 `https://line.chrishzc.com/webhook/line`，開啟 Use webhook；這個 hostname 不可納入上述人員 Access 應用，也不要用全域 Bypass 解決。由你自行按 Verify 確認官方簽章請求成功；不要另發聊天測試訊息。Webhook 後端保留 LINE 簽章驗證與既有 inbox／去重流程。若帳戶另有全域封鎖未匹配應用的設定，需先確認 Webhook hostname 可到達，不能只看 Tunnel Healthy。

本次驗證：`PASS` — 39 項 focused tests、實際 TypeScript／Vite artifact 建置、管理入口的環境／停止狀態查核、來源 ZIP 排除秘密及 architecture closure。`NOT_RUN` — 新 Windows 實機安裝、整組真實服務啟動、Cloudflare 設定寫入／新一輪登入與真實 LINE 推播。唯讀查核時既有 API／5173 未運行，管理入口確認沒有遺留程序後顯示 Stopped；本次沒有為驗證啟動真實 provider cycle。

## 整併前操作說明與歷史紀錄

以下只保留舊入口與既往驗收紀錄供對照；日常操作以上述統一管理入口為準，關閉選單不會停服務，請明確選「停止全部」。過往 PASS 不代表新主機或本次尚未執行的真實 LINE 推播已驗證。

目前指定網址：`https://chrishzc.com/test/`。這是 Windows 測試／操作入口，沿用現有資料庫、帳號、MFA 與背景工作，不是 NAS 部署。

## 準備與啟動

在專案目錄執行：

```bat
scripts\launchers\start_windows_remote.bat --prepare
```

這一步只檢查 TypeScript、建置並驗證網頁 artifact，輸出在 ignored `scratch/windows-remote/` 的獨立目錄。不連 DB、不啟動服務或 Tunnel、不改 `.env`。

正式要啟動這個 Windows 入口時，先關閉原本佔用 8000／5173 的本機服務，再執行：

```bat
scripts\launchers\start_windows_remote.bat
```

入口會重新建置畫面，強制啟用網站登入與 MFA，再委派既有啟動程式完成 DB schema 唯讀檢查、Redis、API 與已設定背景工作。背景工作可能依既有設定處理業務／外部通知；`--prepare` 不會執行它們。DB 不相容時停止，不自行升級。既有 root 帳號、MFA 與資料保留；帳號尚未建立時仍依原本的受控 bootstrap 流程處理。

本機開啟 `http://127.0.0.1:5173/test/`，應顯示登入畫面。API 仍在 `127.0.0.1:8000`，畫面入口僅綁 `127.0.0.1:5173`。遠端入口只提供 `/test/` 的建置檔案及 `/test/api/`，不提供 Vite source、`/internal`、`/docs`、開發免密碼 session 或其他根路徑。原本 `.env` 的免登入設定沒有被改寫；之後仍可使用原本本機 launcher。

`--dry-run` 只執行既有 DB 設定預檢，不連 DB 或啟動服務；它不代表建置、登入、資料庫或外網已通過驗證。停止時在啟動視窗按 Ctrl+C，沿用 supervisor 只清理本次程序的流程。

## 只更新並重啟前端

既有遠端服務運行時，使用：

```bat
scripts\launchers\start_windows_remote.bat --update-frontend
```

此模式先完成 TypeScript／前端建置與 manifest 驗證，再由目前 supervisor 只重啟 loopback 5173 的 Remote React。它不進入完整啟動器，不讀取 DB／`.env`，不啟動 Redis，不重新初始化內部憑證，不重啟 API、背景工作或 Tunnel。Gateway 沿用 production 登入要求，啟動時無 Bearer 的 admission 請求在取得 token 前回 401，不開啟 DB 連線。

建置／驗證失敗時保留原前端；新版啟動或 static version 回讀失敗時回復原 artifact。前端失敗不連帶停止其他服務；命令非零時先確認對應 response／supervisor log，不把逾時當作已完成。

第一次對舊版啟動器執行時，會先核對既有程序的 role、PID、native start time，再以新版 supervisor 接手原服務；非前端程序不變。控制狀態位於 ignored `scratch/windows-remote/frontend-control/state.json`，包含目前 supervisor 身分、已載入的控制程式版本及各服務身分；請求／結果使用唯一 ID。接手後不能再以原啟動視窗或舊 supervisor PID 判斷目前監督程序，後續整套停止／重啟須先確認這份目前狀態。此入口僅支援前端更新，不提供整套服務停止命令。

完整重新啟動仍使用原本無參數／`--connect` 流程，保留既有 DB gate、背景工作與登入安全檢查；`--update-frontend` 不代表已執行那些檢查。

## 已設定 Tunnel 時的連線模式

```bat
scripts\launchers\start_windows_remote.bat --connect
```

此模式在網站 readiness 通過後，由同一 supervisor 啟動已安裝的 cloudflared，以受限 `scratch/windows-remote/cloudflare-state/tunnel-token` 檔案認證；沿用與無參數模式相同的背景工作及推播啟動規則：LINE 依原本 preflight，知識庫依原本啟用設定，其餘標準 Worker 正常啟動。遠端連線不再額外停用任何背景程序。不要分享此目錄、token 或 runtime log；`scratch/` 已排除 Git。關閉視窗／Ctrl+C 沿用 owned cleanup，僅停止本次程序，保留 MySQL 資料與 Redis。

## Cloudflare 路由與存取設定

本 launcher 不安裝 cloudflared。只有 `--connect` 讀取已保存在本機的 token-file 並啟動 connector；Cloudflare 設定另由管理 API 建立，不從 launcher 取得帳戶全域憑證。

1. 先為 `chrishzc.com/test` 與其子路徑設定 Access，僅允許指定完整 Email，保留網站登入／MFA。入口、API、下載與建置資源均位於此前綴。
2. 確認 `chrishzc.com` 既有網站／Tunnel 的路由。保留根網站及其他路徑，只將 `/test` 與 `/test/` 子路徑導至 `http://127.0.0.1:5173`，保留原路徑，不移除前綴。路徑條件必須有 segment 邊界，不包含 `/testing`。
3. 讓 connector 驗證對應 Access token，對此前綴 bypass cache。只有指定 Email 政策完成後才發布。Tunnel 必須在這台 Windows 或能抵達此 loopback origin 的同機程序執行，不直接使用 Docker 裡的 localhost。
4. 用手機行動網路驗證：未核准信箱拒絕、核准信箱仍須網站登入與 MFA、API 未帶網站 session 回 401、匯入／PDF／下載正常、原根網站不受影響。Cloudflare 的上傳大小／等待時間限制仍需實測。

這次保留 root DNS 與原 personal web Tunnel，另新增 `lu-windows-origin.chrishzc.com`、`labor-union-windows` Tunnel 及 `labor-union-windows-path` Worker。Worker 僅匹配 `chrishzc.com/test` 與 `chrishzc.com/test/*`，同一 Access 應用保護 prefix 與 origin；connector 驗同一 AUD。登入後 Worker 僅轉送 Access cookie 與網站 Bearer，不傳原根網站其他 cookie，回應不快取。

外網的 Email PIN、網站 MFA、匯入與業務操作仍須實際操作驗證；Tunnel healthy 或登入前阻擋不能代替上述驗收。

## 2026-10-28 首次連線交付狀態

- `PASS`：既有 Docker MySQL `mysql_db` 啟動並通過唯讀 current schema gate；Windows API／靜態入口與專用 Tunnel 已啟動，Tunnel healthy、4 connections。
- `PASS`：本機 UI 200、未登入 API 401、私人路徑 404；外網 prefix／API／origin 均導向 Access，偽造 Access token 仍遭拒絕。Access 政策只有使用者當輪指定的單一完整信箱，不使用 Everyone／Bypass。
- `PASS`：原根 DNS 與 personal web Tunnel configuration version 2 完全保留。根網站在變更前後均回 502；不將錯誤頁的動態 Ray ID／內容雜湊差異視為原網站程式變更。
- `PASS`（使用者實測回報，2026-10-28）：已完成外網登入並進入網站操作畫面。Agent 未讀取或代填驗證碼、密碼或 MFA 秘密。
- `NOT_RUN`：登入後業務異動驗證；自動背景工作、推播及 schema 變更本次均未執行。

資源定位（不是秘密）：Access app `94f2b768-f1a8-42e7-aca1-8819bd440343`；Tunnel `ab30c078-41f4-4bac-932e-f1fe86edc3b5`；origin DNS `f6d26dbb3ace40ed05711d389df6497a`；Worker `labor-union-windows-path`；兩條 route IDs 為 `21c5fbee71a347d98d612e710ffb2fea`、`098e93ba7dca4669836ac0f84044bdc7`。本機受限目錄的 `connection-receipt.json` 保存同次狀態，不含憑證。

停止遠端服務時，先在啟動視窗 Ctrl+C，supervisor 清理本次 API／靜態入口／connector。若此回合由 Agent 啟動，請要求停止本次遠端服務，由 Agent 對該次程序執行同一停止流程。要還原 Cloudflare 路徑時，只處理以上新增的兩條 Worker routes，保留原 root DNS、既有 Tunnel 與資料；Access 與 origin 的退役另行確認，不因停止連線就刪除憑證或資料。

## 2026-10-28 恢復正常背景工作（初次檢查）

依使用者明確指示，`--connect` 已移除遠端專用的背景停用分支，並已實際重新啟動。LINE、Runtime Monitor、Durable Background Worker、Incident Maintenance Worker、Knowledge Retrieval Worker 均已依既有設定啟動；未另外關閉原本的推播或處理佇列。

- `PASS`：16 項 Windows supervisor 測試；其中四種本機／遠端與知識庫啟用組合，驗證相同工作啟動集合，即使殘留舊 WEB_ONLY 環境值也不再停用。
- `PASS`：批次業務、監控、異常維護、知識庫已實際完成正常工作週期；本機畫面 200、未登入 API 401、公網 Access 302，Tunnel healthy、4 connections。
- `FAILED`：LINE 工作週期仍因既有 Orders 結案事件缺少 LINE 身分，回 `line_terminal_closure_subject_missing`／503。程序已啟動，但不能宣稱 LINE 全部功能或推播已恢復健康；此原因已由既有心跳紀錄的唯讀查核確認。未猜測身分、改寫來源事件、刪除佇列或繞過正式 consumer 驗證。
- `NOT_RUN`：schema／migration／資料重置、額外測試推播；沒有為驗證額外執行 LINE 工作週期。正常已授權 Worker 的排程與工作流程維持運行。

受限目錄的 `normal-operations-receipt.json` 保存本次啟動與驗證；首次連線的 `connection-receipt.json` 保留原階段紀錄。

## 2026-10-28 候選新增修正的前端換版

為遵守本次「不讀取 DB」的要求，已將 `/test` 靜態畫面切至獨立 loopback `5174` 程序；`/test/api/` 繼續走既有 `5173` Gateway。原 API、背景工作及 Tunnel 程序保持運作，Access、網站登入與 MFA 規則沿用現況。專用 Tunnel configuration 為 version 2，API 優先規則與畫面規則均保留 connector Access 驗證。

- Current 前端：`react-admin-7ae12cd39eeea227`；5 個靜態檔案均經 HTTP 回讀並核對 manifest digest，包含 `assets/index-CsNYCnR6.js`。
- 本次只建置及供應靜態檔案，未呼叫 API、未讀取 DB。外網入口及 origin 未登入時均導向原 Access；登入後的實際操作留給使用者驗證。
- 此獨立前端不受原 supervisor 清理。程序身分／啟動時間保存在 ignored `scratch/candidate-leave-deploy/frontend-process.json`，換版紀錄在同目錄 `deployment-receipt.json`；停止前須重新核對程序身分，不以舊 PID 直接終止程序。
- 舊前端與當時的 Tunnel configuration 保留，歷史回復資料在同目錄 `routing-before.json`。後續已新增 LINE Webhook 路由，不能整份套回這份舊 config；管理前端收回 5173 時只修改最新 config 的管理 ingress，保留 LINE、Access 與其他設定。此段為當時獨立前端換版的歷史狀態，後續更新以新版控制狀態與實際 Tunnel readback 為準。

## LINE Webhook（2026-10-28）

LINE Developers → Messaging API → Webhook settings → Webhook URL：

```text
https://line.chrishzc.com/webhook/line
```

此 hostname 由現有 Windows Tunnel 精確轉送 `/webhook/line`（含可選結尾斜線）到執行中的 `127.0.0.1:8000` canonical API，不套人員 Email Access。LINE 簽章／大小限制／payload／inbox 驗證仍由原後端處理。管理 API、`/test/`、私人 `/internal` 及其他路徑均回 404；原管理 Access 與既有 ingress 保留。DNS record ID：`e06c0c229957d6f65d9795c4c111ab44`；本次新增時 Tunnel config version 2 → 3，未覆蓋先前已分流至 5173／5174 的管理路由。

`PASS`：公網 GET Webhook 200、無 Access redirect；無簽章與錯誤簽章 POST 均 401；非 Webhook 路徑 404；原管理介面仍 302 至 Access。

`NOT_RUN`：LINE 官方帶簽章 Verify、實際事件接收；Agent 依使用者限制未讀取或修改 `.env`，未取得 LINE secret／access token、未更改 LINE 後台。使用者貼上網址並儲存、開啟 Use webhook，再按 Verify；顯示 Success 後，從 LINE 傳一則訊息驗證真實事件。GET 200 與拒絕偽造簽章不等於已完成官方 Verify 或業務事件處理。既有結案事件缺身分錯誤仍獨立列管，不由本次接線改寫。

回復僅移除 `line.chrishzc.com` 的精確新增 ingress／DNS；不得整份還原舊 Tunnel config，以免覆蓋其他進行中的設定。

## 2026-10-28 前端單獨更新完成（目前狀態）

- `PASS`：實際執行 `start_windows_remote.bat --update-frontend`，接手執行中的舊控制版本並只重啟 Remote React。前端為 `react-admin-7ae12cd39eeea227`，包含候選加入成功且回讀完成後解除離開保護的修正；5 個靜態檔案均經 HTTP 回讀核對 digest。
- `PASS`：API、LINE Worker、Runtime Monitor、Durable Background Worker、Incident Maintenance Worker、Knowledge Retrieval Worker 與 Tunnel 共 7 個非前端服務，更新前後 PID／native start time 完全相同；API 實際 listener identity 亦不變。
- `PASS`：Tunnel config version 4，管理 origin 的 `^/test(/.*)?$` 統一轉送 `127.0.0.1:5173`，原 API 優先分流已合併。LINE Webhook 與其他 ingress 完全保留，Access 設定不變；Tunnel healthy、4 connections，公網管理頁未登入仍導向原 Access。
- `PASS`：已按原始部署紀錄的 PID／native start time、腳本與父子關係核對後停止 5174 靜態前端；5174 無 listener、無 Tunnel route，原 artifact 保留。前述 5174 換版段落僅為歷史紀錄，無需再照其舊回復流程操作。
- `PASS`：26 項局部隔離測試，包含真實 Windows 假服務接手、連續兩次前端更新、啟動失敗回復、損壞 artifact、過期 request 與 PID identity 拒絕；controller 版本比對變更後重跑直接受影響的 4 項亦通過。
- `NOT_RUN`：本次 Agent 更新流程的 DB 存取、schema／migration、額外業務／推播操作與登入後人工操作驗收。原本背景服務仍依既有授權正常運作。

本機 ignored `scratch/frontend-5173-update/` 保留 before／after identities、最新路由備份、5174 停止紀錄與最終驗證；目前 supervisor 身分仍以 `scratch/windows-remote/frontend-control/state.json` 為準。往後只更新畫面使用 `--update-frontend`，不需再次修改 Cloudflare 路由或額外啟動 5174。

## 2026-10-28 LINE 背景工作 503 修復（目前狀態）

根因是 Orders 合法的 NULL source subject（案件尚未綁定 LINE）被 consumer 在讀取現況前拒絕。修正沿用原 `noop_not_staff`：先核對 owner 尚未綁定、Orders 版本、terminal 狀態與 capability，再由既有 LINE outer UoW 保存同一冪等收據。不補造 LINE 身分、不修改 Orders outbox、不建立通知／選單 intent；真正身分衝突、stale／capability 不符仍零寫入拒絕。

- `PASS`：20 項 terminal-closure 契約測試、26 項記憶體 provider 的派送測試（另含 10 subtests）、架構檢查與 diff check。
- `PASS`：重啟後正常 LINE 排程連續成功週期回 200，無 503；心跳無錯誤。原事件已自動建立 1 筆 noop 收據，未有 LINE receipt 的待處理結案事件降至 0。
- `PASS`：後端／遠端 Gateway／公開 Webhook 回 200，管理入口仍由 Access 保護。未讀取或修改 `.env`，測試時設 `PYTHON_DOTENV_DISABLED=1`；資料狀態由 Docker MySQL 唯讀查核，不讀取檔案內的 DB 憑證。
- `NOT_RUN`：LINE 端實際訊息投遞。目前 delivery tasks／attempts 都為 0，無既有送達紀錄可核對；依使用者要求，沒有人工觸發工作週期或發送測試訊息。後續自然產生的正常通知才能作實際送達證據。

受限目錄的 `line-worker-repair-receipt.json` 保存本次結果。先前 `normal-operations-receipt.json` 的 LINE 503 是修復前的階段紀錄。
