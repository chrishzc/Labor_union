# Cloudflare 外網管理與 LINE：完整設定步驟

適用既有 NAS 專案 `labor-union-nas-dsm-20261020`。同一個 cloudflared 容器、網頁管理的 Tunnel，兩個 hostname 分別連管理 API 與 LINE API。原內網 DNS、DSM HTTPS 19443、反向代理及全部資料保持原位。工會裝置只用瀏覽器，不安裝 Tunnel 或匯入私人 CA。

本次是程式與設定交付，不是 NAS 部署；實際 Cloudflare Access、token、寄信、NAS 防火牆及 2 GB 負載仍須你依步驟驗收。Cloudflare 的 HTTPS 入口會處理經過它的管理流量；內網仍可不經 Cloudflare 直接使用。

## 1. 先填這份表，不要把秘密寄出

| 項目 | 需填／沿用 |
|---|---|
| Cloudflare 自有網域 | **需填**，在 Cloudflare 購買的網域，先確認狀態 Active。以下以 example.com 示範。 |
| 工會外網網址 | **需填**，例如 admin.example.com；人員開啟 https://admin.example.com/admin/。 |
| LINE 外網網址 | **需填**，例如 line.example.com；Webhook 為 https://line.example.com/webhook/line。 |
| 允許的信箱 | **需填**，逐一列出外網工會人員，與網站帳號分開管理。 |
| 原 NAS 專案與 .env | **沿用**，不改專案名稱、NAS_DATA_ROOT、原網域／IP／DSM bridge 位址或現有秘密；不拿範本覆蓋。 |
| Tunnel token | **需自行保存**到 NAS 原專案下 tunnel/token；本包沒有此檔案，不寫 .env、Compose、命令列或映像。 |

LINE API 啟動前，原 `.env` 需要有效的 LINE_CHANNEL_SECRET、LINE_CHANNEL_ACCESS_TOKEN、LINE_LOGIN_CHANNEL_ID、LINE_LIFF_ID。原本未填的值由你自行補充；交付程式不讀取／改寫你的實際 .env，也不以假值替代正式設定。尚未備妥時使用內網版 Compose，不能把 LINE 服務啟動失敗當成已完成。

## 2. 先保護管理 hostname，再發布路由

1. Cloudflare → Zero Trust，尚未初始化時先完成組織設定。
2. **Integrations → Identity providers → Add new identity provider → One-time PIN**。
3. **Access controls → Applications → Create new application → Self-hosted and private → Add public hostname**。
4. 名稱填「工會管理系統」，hostname 填 admin.example.com，**Path 留空，保護整個 hostname**。API、照片／履歷／PDF 下載與靜態畫面都必須在此範圍。
5. 建立 **Allow** 政策，Include 選 **Emails**，逐一填允許的完整信箱；登入方式只選此處採用的 One-time PIN。不要用 Everyone、公開 Bypass，或用 *.example.com 將 LINE 一起套入人員登入。
6. 儲存政策。記下管理應用的 Application Audience（AUD）及組織 team name，之後讓管理路由選到同一應用；這些不是網站 root 帳號。

Access 預設拒絕未匹配 Allow 的人。驗證信箱後仍須登入網站帳號／MFA；不自動建立網站帳號、不授予 root。信箱啟用其供應商提供的 MFA；人員離職要同時移除 Access 資格與停用網站帳號。

官方：[Access 應用](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)、[Email PIN](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/)。選單翻譯可能不同，以功能名稱為準。

## 3. 建立網頁管理 Tunnel 與保存 token

1. **Networking → Tunnels → Create a tunnel**，名稱可用 labor-union-nas。
2. 在連接器安裝頁選 Docker；只擷取該 Tunnel token，**不要把整段安裝命令貼入本專案或分享給他人**。
3. 用純文字編輯器將 token 本身存成無 BOM 的 UTF-8 純文字檔 `token`，不能存成 token.txt。不要保留 `--token` 前綴、引號或安裝命令。可有一個結尾換行。
4. File Station 在原專案建立 `tunnel` 資料夾，將 token 放進去；不要放到 app-data 或任何網站檔案目錄。若本來有本機管理模式的 config.yaml／credentials.json，保留不動，新版不使用它們。
5. 選單若要求先連線才能繼續，暫停；未啟動 NAS 連接器時，Tunnel 未連線正常。

新版使用 `tunnel run --token-file /run/cloudflare/token`；與舊的本機 YAML／credentials.json 模式不同，不能混用。此 token 只允許連接這條 Tunnel，不需要將 Cloudflare 帳戶全域 API key 放到 NAS。

官方：[建立 Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)、[token-file](https://developers.cloudflare.com/tunnel/reference/run-parameters/)。

## 4. NAS 上放檔案、權限與網段檢查

先完成 README 的憑證／備份目錄準備；若原目錄已有同名程式，先保存原版本再替換。另將包內 `nas_appliance.py` 放原專案，它只新增明確代理 IP 信任，唯讀掛入原映像，不需要 image build。此程式給 UID 1000 讀取，但僅管理者能修改；不得 chmod 777。

這份 host 程式與本包註明的 nas-secure-20261020 映像配套。未來更換映像時須一起核對／更新 host 程式並重驗，不能假設只換 image 就會更新這個唯讀掛載檔案；回復時也使用同一版本組合。

建立一個 **root、排程停用、手動執行**的 DSM「使用者定義指令碼」工作「工會 Tunnel 準備」，貼入：

```sh
set -eu
cd /volume1/docker/labor-union-nas-dsm-20261020
test -f .env
test -f nas_appliance.py
test -f compose.with-tunnel.yaml
test -f tunnel/token
test ! -L tunnel
test ! -L tunnel/token
chown 0:0 nas_appliance.py tunnel
chmod 644 nas_appliance.py
chmod 700 tunnel
chown 65532:65532 tunnel/token
chmod 400 tunnel/token
docker --host unix:///var/run/docker.sock compose --env-file .env -f compose.with-tunnel.yaml config --quiet
for net in $(docker --host unix:///var/run/docker.sock network ls -q); do
  docker --host unix:///var/run/docker.sock network inspect --format '{{.Name}} {{range .IPAM.Config}}{{.Subnet}} {{end}}' "$net"
done
echo 'Tunnel files prepared; no services started and no token printed.'
```

保護 tunnel/token 的 DSM ACL，只允許必要管理者／系統存取。400／700 是 POSIX 權限，不代替 DSM ACL。token 檔案 UID 65532 是 cloudflared 的執行身分；應用不掛此秘密，cloudflared 不掛 DB 密碼、業務檔案、簽發私鑰或 Docker socket。

核對上面列出的 Docker／LAN／VPN 網段，新增網段預設如下：

| 新網路 | 範圍 | 連接器 IP | API IP |
|---|---|---|---|
| management-tunnel | 172.31.251.0/29 | 172.31.251.2 | 172.31.251.3 |
| line-tunnel | 172.31.252.0/29 | 172.31.252.2 | 172.31.252.3 |

它們不能與其他網段重疊；原 management-egress／data 網路不改、不重建。若重疊，先停止套用，為新網路選一對未用網段，依 env-additions.example 同時設定 subnet／proxy IP／API IP；只新增相應設定，不替換原 .env。不要為這個目的修改既有 DB 或 DSM bridge 網路。

## 5. 套用完整 Tunnel 版 Compose，保留 .env 與資料

1. 先保存 NAS 當前 compose.yaml 到管理者保護的位置；保留原 .env、全部資料卷／檔案。
2. File Station 將 **compose.with-tunnel.yaml 複製成原專案的 compose.yaml**。這份是完整配置，只有 line-api 和 cloudflared 改為預設啟動；Worker profiles 不變，LINE Worker 仍最後只 --check。因此不用在原 .env 改 COMPOSE_PROFILES。
3. 在 Container Manager 原專案的 YAML 編輯區確認與新 compose.yaml 一致，使用原專案套用／建置動作。YAML 沒有 build 欄位，沿用已下載映像，不會建置新映像；先在「映像」下載 Compose 指定版本的 cloudflared。不要建立新專案名稱、不刪除或清除資料卷。
4. 首次套用需要重建相關 API 容器以載入唯讀程式和專用網路，可能短暫中斷 API；不是資料庫重新初始化，也不重設 root。正常啟動狀態為 DB／management-api／line-api healthy、Redis／cloudflared running，initialize／configure-security 成功退出。

Compose 結束碼 0 或 cloudflared 顯示 running，都不代表已連上 Cloudflare。必須另在 Cloudflare Tunnels 確認 **Healthy**，才進入路由與外網驗收；若不健康，只查錯誤狀態，不公開 token／完整設定或以略過 TLS／Access 驗證排錯。

這五個常駐容器的預設記憶體上限合計為 1856 MiB（管理 768、LINE 384、MySQL 512、Redis 64、Tunnel 128），不是實際用量。2 GB NAS 還需要供 DSM 使用，需在資源監控確認剩餘空間，逐項測上傳／PDF／匯入，不一次啟用所有 Worker。隔離主機測試不代表 2 GB 容量或尖峰負載已通過；遇到 OOM 保留資料與診斷，不清空 DB 重試。

若 GUI 仍有已知 undefined 問題，不重啟整個 Container Manager；可使用 **DSM 工作排程器的 root 一次性工作**，不需要 SSH。先確認既有 DB、Redis、configure-security 正常，手動執行以下只套用三個服務的工作：

```sh
set -eu
cd /volume1/docker/labor-union-nas-dsm-20261020
timeout -s TERM -k 10 240 docker --host unix:///var/run/docker.sock compose --env-file .env -p labor-union-nas-dsm-20261020 -f compose.yaml up -d --no-deps --no-build --pull never --wait --wait-timeout 180 management-api line-api cloudflared
```

結束碼非 0 就保留現場查原因，不反覆建立、不補造初始化標記。240 秒是此工作上限，並非保活等待；超時不能當成 Docker 已回復。套用後先確認原內網管理網址與帳號正常，再處理外網路由。

DSM 防火牆若擋住 Docker 轉送，需允許新增管理來源 172.31.251.2 到管理 API TCP 8443、新增 LINE 來源 172.31.252.2 到 LINE API TCP 8443 的必要流量（自訂網段時同步替換）。DSM GUI 若只能限制來源／埠，至少精確到各連接器單一來源 IP，並確認原 Docker 網路隔離仍有效；不以允許全部 Docker 網段、所有埠或停用防火牆排錯。兩個新 internal 網路分別只有連接器＋對應 API，cloudflared 沒加入 DB 網路。NAS 不發布 8443／3306／6379，路由器不開入站。

## 6. Cloudflare 新增兩個 Published application routes

Tunnel 連線後回到 **Routes → Add route → Published application**。先管理、後 LINE：

| 欄位 | 工會管理 | LINE |
|---|---|---|
| hostname | admin.example.com | line.example.com |
| Path | 留空 | 留空 |
| Service URL | https://management-api:8443 | https://line-api:8443 |
| Origin Server Name | management-api | line-api |
| CA Pool | /run/private-ca/ca.pem | /run/private-ca/ca.pem |
| No TLS Verify | 關閉 | 關閉 |
| Match SNI to host | 關閉 | 關閉 |
| HTTP Host Header | 留空，保留公開 hostname | 留空，保留公開 hostname |
| Protect with Access | 開啟，指定第 2 步的應用／AUD | 不套用人員 Access 驗證 |

進階欄位在 **Additional application settings**。管理應用保護整個 admin hostname，不只 /admin/。若 UI 要求輸入 Access team name／AUD，使用第 2 步該應用的值；沒有設定完成就不發布管理入口，不以關閉驗證排錯。

CA Pool 指 cloudflared 容器的公開 CA 檔案，不能填 NAS 主機路徑或 CA 私鑰。外部 hostname 不需要加入 API 私人憑證 SAN，TLS 透過 Origin Server Name 驗證原 service name。DNS 應由此路由指向 Tunnel，不另建立指向 NAS 公網 IP 的 A／AAAA 管理入口。

官方：[Origin TLS／Access 參數](https://developers.cloudflare.com/tunnel/reference/origin-parameters/)。Cloudflare Access 權限與網站業務角色不相互取代，也不把 Cf-Access-Authenticated-User-Email 當成網站登入憑證。

## 7. 路徑與快取規則

網域 → **Security → Security rules → Custom rule**，限定上述兩個 hostname，動作 **Block**，封鎖 `/internal` 與 `/internal/` 以下路徑。管理 hostname 再封鎖 `/setup`、`/setup/` 以下與 `/api/v1/admin/setup`，既有 root 已建立，外網不提供初始化。

到 **Cache Rules → Create rule**，對這兩個 hostname 選 **Bypass cache**。勿對 LINE Webhook 設人員登入或互動式 Challenge；LIFF 仍由後端驗證 LINE 身分與本人服務範圍。

官方：[安全規則](https://developers.cloudflare.com/waf/custom-rules/create-dashboard/)、[Cache Rules](https://developers.cloudflare.com/cache/how-to/cache-rules/create-dashboard/)。

## 8. LINE 後台與實際驗收

LINE Developers 的 Webhook URL 設為 `https://line.example.com/webhook/line`，LIFF endpoint 使用原本頁面路徑加新 LINE hostname，不能改指管理 hostname。先測 Verify 與綁定／本人查詢／受限申請，日誌照片仍本人範圍提交；核心資料異動仍經工會核准。正式 Channel／LIFF 設定與對外驗收使用你的資料，不使用交付測試的合成值。

- [ ] 無痕瀏覽器／手機行動網路開 admin hostname：先被 Access 擋住，沒有管理畫面、API 資料或可下載檔案。
- [ ] 未核准信箱不能通過；核准信箱通過後仍須網站帳號與 MFA。
- [ ] 工會帳號沒有 root 管理權限；直接呼叫 API／下載網址仍受相同保護。
- [ ] LINE hostname 不能開啟管理 API／畫面；兩個外網 hostname 的 internal 路徑都被擋住。
- [ ] 原內網 DDNS:19443 可用，Cloudflare 暫停時仍能從內網管理。
- [ ] 照片／履歷預覽下載、PDF、匯入、背景工作與慢請求實測；Cloudflare 大小／時間限制不能靠延長程式 timeout 繞過。
- [ ] 憑證維護實際輪替後 Tunnel 仍可驗證 origin；每日 03:00 SQL 備份持續正常。
- [ ] 最後 LINE Worker 只做啟動／--check，不在此階段執行工作週期或正式推播。

本機測試不代表上述 Cloudflare 實網項目已通過；看包內 validation.json 的 PASS／NOT_RUN。實網驗證通過前不宣稱外網已安全上線。

## 9. 快速停止外網與回復

有異常時先停用 Cloudflare 的兩條 public routes，或在原專案只停止 cloudflared；內網 API、DB／Redis 保留。若需 DSM 一次性工作：

```sh
set -eu
cd /volume1/docker/labor-union-nas-dsm-20261020
timeout -s TERM -k 10 60 docker --host unix:///var/run/docker.sock compose --env-file .env -p labor-union-nas-dsm-20261020 -f compose.yaml stop --timeout 20 cloudflared
```

復原設定時還原你保存的原 compose.yaml 及同版 host .py／.sh 程式，不改 .env／資料卷／網路，僅在必要時重建受影響 API 容器；不要刪資料或重新初始化。token 外洩則在 Cloudflare 重新產生並替換受保護 token 檔案，重建／啟動該連接器；不可把外洩 token 繼續當成有效秘密。兩個 hostname 不能指向同一組不分角色的管理路由。
