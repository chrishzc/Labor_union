# 群暉 DDNS／Let’s Encrypt／內網管理反向代理

既有 NAS 整合維護設定：先讀 [DSM-SETUP.md](DSM-SETUP.md)，一次準備完整 Compose、憑證維護與每日 03:00 不停機 SQL 備份；原 `.env` 保留，日後才由 DSM 建立兩個排程。以下部署／生命週期內容另供操作參考，不是安裝排程時必須重建專案的步驟。

每日不停機 SQL 備份：另保存 [SQL-BACKUPS.md](SQL-BACKUPS.md) 與 `backup-database.sh`，由 DSM 每日 03:00 執行並永久保留本專案 SQL；不改 Compose／.env，不包含實體檔案／金鑰，不能代替下方完整冷備份。首次路徑／通知／容量與實際排程需在 DSM 設定。

內部憑證維護：另保存 [CERTIFICATES.md](CERTIFICATES.md)、`maintain-certificates.sh` 與 `nas_certificate_maintenance.py`（來源 `scripts/nas_certificate_maintenance.py`）。由 DSM 每日排程執行，未完成 DSM 設定就不會自動續期。`certificates` 是手動維護 profile，不加入一般 COMPOSE_PROFILES，不啟動 LINE 工作，也不修復 Container Manager 的 undefined 問題。

沿用已上傳映像 `chris23144638/cecec:nas-secure-20261020`（linux/amd64），不需修改、重建或重新上傳映像。程式已提供 HTTPS、依目前 Host 驗證的首次 root 建立、相對路徑前端與受限代理標頭信任。本次只調部署入口；沒有連接 NAS、申請實際網域或變更既有資料。NAS／DSM 實機驗證仍須完成。

```text
內網瀏覽器 → https://admin.你的DDNS名稱.synology.me:19443
           → DSM 反向代理（Let’s Encrypt 憑證＋來源 IP 存取控制）
           → https://NAS_PROXY_API_IP:8443（同機 Docker 私有網路）
           → management-api
```

管理容器不發布任何 NAS 主機埠；MySQL、Redis、LINE API 也不發布。DSM 直接存取管理容器的固定 bridge IP。瀏覽器不需要匯入專案 CA。DSM→容器保留 HTTPS，但此 GUI 方案不宣稱 DSM 已驗證上游私人 CA 鏈／名稱；原生反向代理說明沒有提供該信任設定，本機 Linux bridge 與不發布埠是此段的存取邊界。Worker／DB 的既有 CA 與身分驗證不變。若組織要求此段也必須嚴格驗證上游憑證，不能把本文件當成已滿足該要求。

本份現在承接 **DS220+ 現有安裝的維護**：正式 Compose 已對齊 NAS 修正版，取消不支援的 `cpus` 配額，保留原記憶體、安全性、掛載及服務功能。`data` 引用既有 `${COMPOSE_PROJECT_NAME}_data` 外部管理網路；這裡的 external 指生命週期由 Compose 外管理，實際網路仍須是 `internal=true`，不代表開放 Internet。現有 NAS 的資料網段為 `172.24.0.0/16`，更新時不重建或改名。

**既有安裝更新不可重填新專案名稱、清空資料夾或複製範本覆蓋 .env。** 詳見下方「重啟、重建、更新與回復」。新安裝／隔離測試才使用新名稱、空白 bind roots 與獨立資料卷，並須預先準備對應 internal data 網路；本檔不會替新環境建立該外部管理網路。已存在的初始化標記只驗證，不自動換證或覆寫秘密。

## 準備檔案與填寫 .env

下次建置映像並搭配本版 Compose 時，應付帳款 Excel 使用 `ACCOUNTS_PAYABLE_ARCHIVE_ROOT=/data/accounts-payable-archive`，實際保存於 `${NAS_DATA_ROOT}/app-data/accounts-payable-archive/<年度>/`。此目錄沿用管理容器可寫的持久掛載，包含在 app-data 備份內；封存失敗不回傳成功下載。舊映像尚未包含此路徑修正，單獨更新 Compose 不會修正舊程式；不需另加公開下載目錄或放寬容器唯讀設定。

把 `compose.yaml`、`.env` 放在 NAS 同一專案資料夾；`.env` 由 `.env.example` 複製，不命名成 `.env.txt`。不要搬用開發機實際 `.env`。範本不含實際帳密，DB 密碼及六組服務 token 由初始化建立，網站 root 從網頁建立。

| 設定 | 填寫方式 |
|---|---|
| `COMPOSE_PROJECT_NAME` | 預設 `labor-union-nas-dsm-20261020`；既有安裝保留原值，Container Manager 填相同值；新測試才另取新名稱 |
| `NAS_IMAGE` | 已填 `chris23144638/cecec:nas-secure-20261020` |
| `NAS_DATA_ROOT` | 必填：既有安裝保留原路徑；新安裝才用空白路徑，例如 `/volume1/docker/labor-union-nas-dsm-20261020/storage` |
| `NAS_BIND_IP` | 必填：NAS 真正的固定內網 IPv4，例如 `192.168.1.100`；僅供初始化憑證，並非發布埠 |
| `NAS_MANAGEMENT_HOSTNAME` | 選填 `admin.你的DDNS名稱.synology.me`，不含協定或 port；只影響初次內部憑證，不會建立 DNS 或申請公信憑證 |
| `NAS_PROXY_SUBNET` | 預設 `172.31.250.0/29`；先在 Container Manager「網路」檢查與既有 Docker／LAN／VPN 網段沒有重疊 |
| `NAS_PROXY_API_IP` | 預設 `172.31.250.2`；必須位於上列網段，不能是網路、廣播或網關位址。這也是 DSM 代理的目的地主機 |
| `COMPOSE_PROFILES` | 初次留白；LINE 與 Tunnel 尚不啟動 |

管理入口預設選 **19443**，以獨立埠設定防火牆，不改動既有 DSM 或其他 443 網站。這是 DSM 介面設定，不是 Compose 的 `.env` 變數。本版已移除原本的 `NAS_HTTPS_PORT` 發布設定；NAS 的 `18443` 不再是本專案入口。

容量與 60 秒等待仍可從管理網頁調整；環境值只作初始值，保存後以 `/data/file-settings.json` 為準。資料根目錄仍由 Compose 掛載決定。

## 群暉介面操作順序（不使用 SSH）

以下 `union-example.synology.me`、`192.168.1.100`、`192.168.1.0/24` 都是範例，請改成自己的 DDNS、NAS IP 與允許使用管理介面的內網範圍。

1. **確認固定 IP 與空白資料夾。** 在 File Station 建立新的專案資料夾，上傳 `compose.yaml`、填好的 `.env`。在 `NAS_DATA_ROOT` 建立四個空白子目錄：`app-data`、`controlled-files`、`line-media`、`knowledge`。對新目錄設定所需 DSM ACL；日常程式身分為 UID/GID 1000:1000，不使用 777 或掛整個 volume。
2. **檢查 Docker 網段。** 既有安裝保留所有原網路；`${COMPOSE_PROJECT_NAME}_data` 必須已存在且 internal=true。新安裝需由管理者先準備此專案專用 internal bridge，再確認 `NAS_PROXY_SUBNET` 未與既有 Docker／LAN／VPN 網段重疊；不沿用其他專案的網路。既有安裝若需改管理固定 IP，須另行安排 DSM 代理及相關規則同步，不能當一般換版處理。
3. **登記 Synology DDNS。** 控制台 → 外部存取 → DDNS → 新增，服務供應商選 Synology，登記如 `union-example.synology.me`，依畫面登入 Synology 帳號並測試連線。這一步不新增路由器入站轉送或啟用自動路由器設定；保留既有 DSM 憑證的預設指派。
4. **申請包含萬用字元的憑證。** 控制台 → 安全性 → 憑證 → 新增 → 新增憑證 → 從 Let’s Encrypt 取得憑證。網域填 `union-example.synology.me`、填自己的電子郵件，主體別名（SAN）填 `*.union-example.synology.me`。含萬用字元的 Synology DDNS 憑證採 DNS-01 驗證，不開路由器 80 埠；若申請失敗，先查看 DSM 錯誤，不能以開放管理入口作替代。不要覆換原有 DSM 憑證或勾成全站預設。NAS 需可對外連網以申請／續期。
5. **準備內網 DNS。** 首選路由器已有的本機 DNS／網域覆寫功能：新增 `admin.union-example.synology.me → 192.168.1.100`。若路由器沒有，使用下一節群暉 DNS Server 做法。DDNS 的公開紀錄不等於內網解析，不能依賴外網 IP 繞回 NAS。
6. **先建立來源存取規則。** 控制台 → 登入入口 → 進階 → 存取控制設定檔，新增本專案專用設定檔。先新增「允許、來源 `192.168.1.0/24`」，再新增「拒絕、所有來源」（空白來源代表全部）。兩條規則依此順序；不要只新增允許而漏掉最後拒絕。只有被允許的子網／裝置可使用管理介面，不會因為是訪客 Wi-Fi 就自動取得權限。
7. **設定管理入口的防火牆。** 控制台 → 安全性 → 防火牆 → 編輯規則，在正確介面對 TCP 19443 先允許上述內網來源，再拒絕所有其他來源，放在可放行該埠的廣泛規則之前；IPv6 也不得留下外網允許。僅新增本埠規則，保留既有 DSM 與其他服務規則；勿重設整個設定檔。若選用其他未占用 port，以下所有 19443 一起改。
8. **下載既有映像。** Container Manager → 映像／倉庫，下載 `chris23144638/cecec:nas-secure-20261020`。應用服務使用 pull_policy: never，需先有映像；MySQL／Redis 仍依範本取得。上傳時倉庫為 Public，之後若改 Private 則使用自己的倉庫登入，帳密不寫進 Compose。
9. **建立新專案。** Container Manager → 專案 → 新增，名稱填 `.env` 的 `COMPOSE_PROJECT_NAME`，路徑選上述資料夾，使用現有 Compose 檔並啟動。不選 NAS Web Station 的自動公開入口。`initialize`、`configure-security` Exit 0 是正常的一次性完成；等待 db 及 management-api healthy。若初始化失敗，保留卷與紀錄，不勾刪除資料卷、不清空資料夾。
10. **確認實際容器位址。** 在 Container Manager 查看 management-api 詳細資料／網路，確認 management-egress 的位址與 `NAS_PROXY_API_IP` 相同；管理容器不應出現 NAS 主機埠映射。若不符，先檢查新專案 `.env` 與網段，不設定代理至其他專案或臨時變動的 IP。
11. **建立反向代理。** 控制台 → 登入入口 → 進階 → 反向代理 → 新增。來源：HTTPS、主機名稱 `admin.union-example.synology.me`、port `19443`。目的地：HTTPS、主機名稱 `.env` 的 `NAS_PROXY_API_IP`（預設 `172.31.250.2`）、port `8443`。套用第 6 步的存取控制設定檔；整個站台使用相同來源，不分開代理 /setup、/admin 與 /api。
12. **設定轉送標頭與上傳限制。** 反向代理的自訂標頭中，將送往後端的 `Host` 設為 `admin.union-example.synology.me:19443`，`X-Forwarded-Proto` 設為 `https`，避免 origin 不一致導致 root 建立／登入失敗。若已有相同標頭則編輯，不重複新增。保留 DSM 的真實來源 IP 轉送，不把代理信任設為所有來源。若畫面提供 HTTP body 大小與 proxy timeout，容量至少需容納管理頁目前設定的照片／履歷上限與 multipart 開銷，等待時間至少 60 秒，較大檔案可依需求提高；不要讓代理預設值比應用程式設定更小。DSM 沒有提供相關欄位時，先以實際上傳測試確認限制，不能宣稱所有容量已驗證。
13. **指派公信憑證。** 控制台 → 安全性 → 憑證 → 設定／設定服務憑證，將新的 `admin.union-example.synology.me:19443` 反向代理服務指派到第 4 步的 Let’s Encrypt 憑證；其他 DSM 服務的指派不動。
14. **開啟與驗證。** 內網電腦使用 `https://admin.union-example.synology.me:19443/setup` 建立 root，之後進 `/admin/` 並依原流程完成 MFA。瀏覽器顯示的憑證應涵蓋該網域，簽發者為 Let’s Encrypt，不應是 Labor Union private API CA。本方案不需在各電腦匯入 management-api-ca.crt。
15. **驗證只限內網。** 允許的內網裝置應能登入；不允許的網段／訪客網路應拒絕。手機關 Wi-Fi 後開管理網址，不得出現 setup、登入頁或業務資料。從內網直連 `NAS_IP:18443` 或 `NAS_IP:8443` 不應取得本專案頁面；既有其他服務若用相同埠，不能因此判為本專案成功。檢查 IPv6、路由器既有轉送與 DSM 存取規則，不能只憑沒有新開轉送就宣稱隔離通過。
16. **基本功能回歸。** 依序測 root／MFA 登入、管理查詢與修改、需求核准、照片／履歷預覽下載與上傳、PDF、匯入。再逐組啟動背景工作；LINE Worker 最後才 --check。代理 502 優先核對容器 healthy、固定 IP 與目的地 HTTPS:8443；Origin 錯誤核對 Host（含 19443）；TLS 警告核對憑證指派、DNS 與使用網址，不改成 HTTP 或放寬帳號權限。

## 需要使用群暉 DNS Server 時

本節只建立內網解析，不讓 NAS 成為對外公開 DNS。若路由器已能做上述單筆網域覆寫，不必另外安裝此套件。

1. 套件中心安裝 DNS Server，開啟「區域 → 建立 → 主要區域／正向區域」。區域名稱只填 `admin.union-example.synology.me`，主要 DNS 伺服器填 NAS 固定內網 IP。使用單一管理 hostname 區域，避免攔截 `union-example.synology.me` 的公網 DNS-01 憑證驗證查詢。
2. 在該區域「編輯 → 資源記錄」新增／設定 A 記錄，最終完整名稱必須為 `admin.union-example.synology.me`、IP 為 NAS 內網 IP；在會自動附加區域名稱的介面，使用區域根名稱，不重複輸入整段網域。SOA／NS 等自動記錄保留。檢查清單顯示的完整名稱，不能變成 `admin.union-example.synology.me.admin.union-example.synology.me`。
3. 「解析」啟用解析服務與轉寄站，將解析來源限制為需要使用的內網子網；轉寄到既有上游 DNS。DSM 防火牆只對允許的內網開 TCP／UDP 53，路由器不做 53 入站轉送。
4. 路由器 LAN／DHCP 設定將用戶端 DNS 指向 NAS IP，保留原閘道與 DHCP 位址範圍。不要同時派發不含管理網域覆寫的公共 DNS 當備援，否則可能繞過內網解析；需要備援時另一台 DNS 也必須有同樣紀錄。這是全網 DNS 變更，確認可管理路由器後才套用，並記下原值以便還原。
5. 測試電腦重新連接網路取得 DNS。若瀏覽器設定了固定外部安全 DNS，改用系統／組織指定的 DNS。使用 DSM GUI 設定仍需要用戶端實際查詢這台 DNS；只安裝 DNS Server 不會讓所有電腦自動採用它。

## profiles、儲存與測試限制

基本組為 initialize、db、configure-security、redis、management-api。initialize 與 configure-security 成功後 Exited (0) 正常，不需要保持執行。COMPOSE_PROFILES 留白不啟動 LINE 或 Tunnel。可依序填 durable、knowledge、incident、monitor、line、tunnel、line-check；多組以逗號分隔，依下方套用流程處理。LINE Worker 仍只有 --check，不代表持續處理訊息。

NAS_DATA_ROOT 的 app-data → /data；controlled-files → /data/controlled-files；line-media → /data/media；knowledge → /data/knowledge。日常管理服務讀寫，公開 LINE 只掛自己的媒體資料，不掛其餘業務目錄。各 Worker 僅掛自己的 token 與 CA。檔案備份目的地與還原演練仍需另外安排。

目前 LINE_PUBLIC_BASE_URL 仍只傳給 monitor；完整 LINE 對外連結與收送設定尚未在本次管理入口調整中補接，不能把四個憑證欄位或 --check 當成完整 LINE 上線驗證。

## 官方依據與已驗證範圍

- 群暉憑證與 Synology DDNS DNS-01／wildcard：https://kb.synology.com/en-us/DSM/tutorial/How_to_enable_HTTPS_and_create_a_certificate_signing_request_on_your_Synology_NAS
- DNS-01 可用於不對外公開的網站：https://letsencrypt.org/docs/challenge-types/#dns-01-challenge
- DSM 反向代理與來源 IP 存取控制：https://kb.synology.com/en-my/DSM/help/DSM/AdminCenter/system_login_portal_advanced
- Docker 不發布埠與舊版 localhost 限制：https://docs.docker.com/engine/network/port-publishing/
- Nginx 上游憑證驗證預設與 CA 設定：https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_ssl_verify
- 群暉 DNS Server 與用戶端 DNS 設定：https://kb.synology.com/en-eu/DSM/tutorial/How_to_set_up_your_domain_with_Synology_DNS_Server

既有映像完整前端 1931 passed／0 failed／2 原有 skipped，以及相關後端 67 項為先前有效結果，不等於本輪 DSM 實機驗收。此次新增的配置解析、映像／網頁與首次 root 邊界核對另記於驗證工作包；未申請實際憑證、部署 NAS、存取既有資料或重新建置／上傳映像。來源 IP、DNS、續期與實際檔案傳輸需完成上述實機步驟才可判定通過。

## Cloudflare Tunnel 與外部網址

目前採一條網頁管理 Tunnel、兩個獨立 hostname／Access 權限，完整步驟見 [CLOUDFLARE.md](CLOUDFLARE.md)。管理 hostname 先套 Access 指定信箱及 connector token 驗證，再進原網站帳號／MFA；LINE 依原簽章與本人授權，不套人員登入。

預設 compose.yaml 保持內網基本組。通過本機驗證後的整合 ZIP 另提供完整 compose.with-tunnel.yaml，準備 token／LINE 設定後複製成原專案 compose.yaml 即可，不改 COMPOSE_PROFILES。程式 nas_appliance.py 必須一併放原目錄，唯讀掛入現有映像；首次套用需重建相關 API 容器，但保留資料。

新的 cloudflared 使用 tunnel/token 檔案，不使用舊 config.yaml／credentials.json；舊 compose.tunnel.yaml／cloudflared.example.yaml 僅為歷史本機管理範例，不能疊加到新 remote-managed 配置。新版連接器只掛 token 與公開 CA，經兩個專用 internal origin 網路連 API，不連 MySQL／Redis，不掛業務檔案或 Docker socket。公開來源維持 TLS 與服務名稱／CA 驗證；原 DSM 內網入口保留。

參考：[網頁管理 Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)、[Access](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)。外網 PDF／匯入／LINE 正式連結仍需實機驗收，不能由 --check 或 YAML 解析冒充完成。

## 服務與帳號

| 執行位置／身分 | 允許操作 | 限制 |
|---|---|---|
| 工會人員／網站管理介面 | 查詢、建檔、修改、原有合法刪除與匯入；核准需求和異動申請 | 同等業務功能；只有網站 root 多出帳號中心 |
| management-api／management DB 帳號 | 業務表 SELECT、INSERT、適用的 UPDATE；逐一授權的固定刪除程序 | 沒有直接 DELETE、DDL、GRANT；不使用 MySQL root |
| 管理介面帳號安全／access DB 帳號 | 網站登入、MFA、帳號中心、內部管理員 LINE 綁定 | 與一般業務連線分開；憑證不掛入對外 LINE 容器 |
| line-api／line DB 帳號 | 經 LINE token 與綁定驗證後查詢；保存需求與異動申請、事件、回覆工作；本人服務日誌和照片 | 不建立正式客戶、不修改訂單或付款；沒有 P01–P10 或帳密／MFA 存取權 |
| 系統必要 LINE 綁定投影 | 更新 clients／staff 的 line_user_id、admin_users 的 linked_line_user_id | 僅連結識別欄位；不包含帳密、MFA、客戶業務內容 |
| 維護／maintenance DB 帳號 | 稽核歸檔、異常投影、核准範圍的技術資料清理 | 只執行各自授權程序；無直接 DELETE、DDL |
| 各 Worker | HTTPS 呼叫其被授權的私人操作 | 每個 Worker 只掛自己的 token 和 CA，不掛 DB 帳密 |
| 初始化及權限安裝 | 建立隔離新庫、帳號與程序 | MySQL root 僅掛入初始化／一次性設定服務，不給日常 API 或 Worker |

本人資料的列範圍由既有 LINE token 驗證、綁定與 owner Query／Apply 檢查。
MySQL 的表／欄位權限阻止核心寫入，**不提供資料列層級的讀取隔離**；不能宣稱 LINE 程式本身遭控制後仍絕對無法讀取其他人的資料。
所有 API 仍必須保留身分、版本、服務指派及日期檢查。

各 DB profile 與 locked definer 另有僅限本專案 database 的 `LOCK TABLES`，供既有 `FOR UPDATE` 鎖定讀取使用；核心資料寫入欄位不增加。
MySQL 要求鎖定讀取另持 DELETE、UPDATE 或 LOCK TABLES 之一，因此使用鎖定權來保留現有交易，而不是開放核心寫入；鎖定遭濫用仍可能造成阻塞。
依 [MySQL locking reads](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html) 與 [GRANT 的資料庫名稱規則](https://dev.mysql.com/doc/refman/8.0/en/grant.html)，installer 依 partial_revokes 處理底線，避免 database scope 變成跨庫 wildcard。

## 原有刪除如何保留

| 功能群組 | 固定程序 | 執行身分 |
|---|---|---|
| P01 假日刪除 | lu_nas_delete_holiday_v1；單一日期 | management |
| P02 證照／交通移除 | lu_nas_remove_staff_{certifications,transportation}_v1；固定人員和值 | management |
| P03 六種偏好關聯移除 | lu_nas_remove_staff_{regions,time_slots,cooking_skills,holiday_availability,weekly_rest,baby_types}_v1；固定值與 detail | management |
| P04 偏好縮減 | lu_nas_trim_preferences_v1；本人員、版本、保留清單 | management |
| P05 歷史匯入取代 | lu_nas_replace_staff_*_v1；固定關聯或銀行帳戶、核對舊集合 | management |
| P06 單案虛擬帳號替換 | lu_nas_replace_case_account_v1；案件與舊 mapping IDs | management |
| P07 排班重建舊佔用 | lu_nas_cancel_occupancy_v1；案件及舊有效世代 | management |
| P08 當前異常投影移除 | lu_nas_remove_current_issue_v1；key、owner、snapshot | management、maintenance |
| P09 稽核歸檔 | lu_nas_archive_audits_v1；逾兩年、核對歸檔內容後刪來源 | maintenance |
| P10 知識技術資料清理 | lu_nas_purge_knowledge_request/job/index_v1；固定終態、版本與關聯 | management、maintenance |

共 26 個實體程序。固定 definer 帳號鎖定登入，只具程序需要的表權限；不使用動態 SQL。
程序不自行 COMMIT，失敗由既有 outer transaction 回滾。索引檔案沿用鎖定交易內清理後才 commit 的順序，避免索引編號重用後誤刪新檔；檔案失敗回報待對帳且不 commit。檔案本身無法隨 DB 回滾，commit 失敗仍須對帳，不能宣稱 SQL／檔案整批原子性。
這些限制縮小合法刪除範圍，不代表可抵擋持有管理端完整業務憑證的所有惡意修改。

## 重啟、重建、更新與回復

### 操作範圍與前置檢查

以下只針對 `labor-union-nas-dsm-20261020`。在原專案目錄執行，保留原 `.env`、所有 named volumes、四個 bind roots 及 internal data 網路；不使用清理、刪除資料卷或 `down -v`。操作前記錄舊 image tag／digest、MySQL 版本與啟用 profiles。不要貼出完整 `docker inspect`、`compose config`、`.env` 或 security.json，這些可能包含秘密。

Container Manager 的「重新啟動」會啟動已停止的一次性服務，也不會套用新 .env／映像設定，因此本流程使用明確的停止／套用／檢查順序。若介面仍出現 `undefined`，不以其燈號判定成功，亦不重啟整個 Container Manager 套件來影響其他專案；使用以下限定專案的 SSH 命令。GUI 操作及 DSM 自身重新開機仍需 NAS 實測，不能由本機 Docker 驗證替代。

先確認 Compose 支援 `up --wait --wait-timeout`（`docker compose up --help`）；下列套用最多等 180 秒，不使用附加長時間 sleep。逾時後命令返回，但容器可能仍在執行，依狀態查原因，不反覆啟動同一作業。此值是操作等待上限，不是強制殺掉初始化工作的計時器。若初始化正在改帳號／GRANT，不可只憑超時假設已回滾。

```sh
sudo docker compose -p labor-union-nas-dsm-20261020 -f compose.yaml ps -a
sudo docker network inspect labor-union-nas-dsm-20261020_data --format 'internal={{.Internal}} {{range .IPAM.Config}}subnet={{.Subnet}} {{end}}'
```

data 必須 internal=true，現有 NAS subnet 應維持 172.24.0.0/16。防火牆保留已核准的 DB 規則。Redis 6379 與 Worker→私人 API 8443 仍需按實際來源網路逐項驗證；容器 Up 不代表可跨容器連線，不應為排錯停用整個防火牆。

### 1. 補啟動服務／一般重啟

只補 Redis，不停止 DB 或管理 API，也不重跑權限安裝：

```sh
sudo docker compose -p labor-union-nas-dsm-20261020 -f compose.yaml up -d --no-deps --no-build --pull never redis
```

需要整個專案重新啟動時，先停止，再由 Compose 依依賴條件套用原配置：

```sh
sudo docker compose -p labor-union-nas-dsm-20261020 -f compose.yaml stop --timeout 30
sudo docker compose -p labor-union-nas-dsm-20261020 -f compose.yaml up -d --no-build --pull never --wait --wait-timeout 180
```

initialize 遇到完整既有標記只驗證並沿用憑證。configure-security 若重跑會核對 schema、既有憑證及限定權限；這不是重新建庫，不會重設網站 root。失敗時保留現場，不以手動補標記或清空資料繞過。

### 2. 保留資料重建容器

本流程重建容器但不刪除網路／資料卷；不先執行 down。先完成下方冷備份，再停止及強制重建：

```sh
sudo docker compose -p labor-union-nas-dsm-20261020 -f compose.yaml stop --timeout 30
sudo docker compose -p labor-union-nas-dsm-20261020 -f compose.yaml up -d --force-recreate --no-build --pull never --wait --wait-timeout 180
```

完成後確認：db／management-api healthy、redis Up、一次性服務 Exited (0)、舊 root／工會帳號可完成 MFA 登入、setup 已關閉、檔案與原資料仍在。若資料夾突然空白或重新出現建立 root 畫面，先檢查 project／volume／NAS_DATA_ROOT 是否連到原位置，不建立第二組資料來掩蓋問題。

### 3. 一般映像更新（資料庫結構與權限未變更）

1. 完成備份，保存舊 compose.yaml／.env 與 image digest；保留舊映像。
2. 用 Container Manager 先下載指定新 tag 或 digest。下載映像不會更新執行中的容器。
3. 只修改原 `.env` 的 NAS_IMAGE；其他原值保留。新版本的 env 範本不能整份覆蓋原值。
4. 停止本專案，使用上面的 `up -d --no-build --pull never --wait --wait-timeout 180` 套用。Compose 會使用新映像建立需要更換的應用容器，仍掛原資料。
5. 依第 2 節的完成條件及該版本受影響功能驗證。未通過就停止該次更新，不能把容器 running 當整體通過。

如果 release 有 DB schema／seed／資料轉換／GRANT 變更，不能套用這段普通換版流程；先走既有保留資料 migration 的 plan、備份、隔離 apply／verify 及版本相容性驗證，再安排 NAS 維護。不對既有 DB 重跑 fresh schema。此任務沒有新增 migration 或授權 NAS DB apply。

### 4. 普通換版失敗的回復

僅適用上述「沒有 DB 變更」的更新：停止本專案、還原備份中的 compose.yaml／.env（NAS_IMAGE 回到舊 digest），並還原同版 host 唯讀程式，再執行一般套用命令；資料卷與檔案保持原位。確認 root／MFA、資料與檔案回讀正常後才恢復使用。

若有 schema 變更，舊映像未必相容，不能宣稱只換回 image 就能還原；應停止寫入，依該 migration 的備份／還原程序處理。備份缺失時停止操作，保留現場。

### 5. 一致的冷備份與災難還原範圍

備份必須在本專案所有 writer 停止、MySQL 正常停止後進行，保存：

- 原 compose.yaml、原 .env、同版 nas_appliance.py／憑證與備份程式、舊應用與 MySQL 的 image digest、profiles 與 data／新增代理網路的 internal／CIDR 資訊。映像 digest 不包含 host 唯讀掛載程式，必須一起保留對應版本。
- 本專案全部 named volumes，包含 mysql-data、settings、各 DB 憑證、私人 CA／伺服器憑證、MFA keyring、各 Worker token、line-config；不能只備份資料庫而漏掉加密金鑰。
- NAS_DATA_ROOT 下 app-data、controlled-files、line-media、knowledge 四個目錄，保留檔案權限與擁有者。
- 已啟用憑證維護時，另依 CERTIFICATES.md 備份管理者保護的 certificate-maintenance 狀態／issuer 私鑰；下方卷／檔案冷備份命令不包含這個可能自訂的目錄。完整災難備份須配套保存，不能把公開 private-ca 卷當成已含簽發私鑰。還原至新專案時也使用新的 NAS_CERT_MAINTENANCE_ROOT，不與原專案共用此狀態。

備份含帳密、MFA 金鑰與私人憑證，目的資料夾只允許管理者存取，不能放到會被應用掛載或公開下載的位置。容器／映像匯出不代表已包含資料卷。

**冷備份操作範例。** 先依第 1 節停止本專案；在 File Station 將原專案目錄下的 backups 資料夾 DSM ACL 限定為管理者可存取，再於原專案目錄整段執行下列命令。來源資料唯讀掛載，路徑由目前 management-api 的實際 `/data` 掛載推得，不靠猜測 NAS_DATA_ROOT；備份放在 backups 的新子目錄。有任何容器仍執行、DB 未正常停止或卷名不符就退出，不做清理或重設。命令中的 700／umask 僅處理 POSIX 模式，不代替 DSM ACL。

```sh
sudo sh <<'SH'
set -eu
umask 077
PROJECT=labor-union-nas-dsm-20261020
test -f compose.yaml && test -f .env
test -z "$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT")"
test "$(docker inspect --format '{{.State.Status}}' "$PROJECT-db-1")" = exited
test "$(docker inspect --format '{{.State.ExitCode}}' "$PROJECT-db-1")" = 0
APP_DATA=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$PROJECT-management-api-1")
DATA_ROOT=${APP_DATA%/app-data}
test "$APP_DATA" = "$DATA_ROOT/app-data" && test -d "$DATA_ROOT"
IMAGE=$(docker inspect --format '{{.Image}}' "$PROJECT-management-api-1")
BACKUP_DIR="$(pwd)/backups/$(date +%Y%m%d-%H%M%S)"
case "$BACKUP_DIR/" in "$DATA_ROOT/app-data/"*|"$DATA_ROOT/controlled-files/"*|"$DATA_ROOT/line-media/"*|"$DATA_ROOT/knowledge/"*) exit 1;; esac
mkdir -p "$(pwd)/backups"
mkdir -m 700 "$BACKUP_DIR"
cp compose.yaml .env nas_appliance.py nas_certificate_maintenance.py maintain-certificates.sh backup-database.sh "$BACKUP_DIR/"
printf '%s\n' "$PROJECT" > "$BACKUP_DIR/project-name.txt"
docker network inspect "$PROJECT"_data --format 'internal={{.Internal}} {{range .IPAM.Config}}subnet={{.Subnet}} {{end}}' > "$BACKUP_DIR/network.txt"
for SERVICE in db management-api; do
  ID=$(docker inspect --format '{{.Image}}' "$PROJECT-$SERVICE-1")
  docker image inspect --format '{{.Id}} {{json .RepoDigests}}' "$ID" >> "$BACKUP_DIR/images.txt"
done
docker volume ls --filter "label=com.docker.compose.project=$PROJECT" --format '{{.Name}}' > "$BACKUP_DIR/volume-names.txt"
grep -Fx "$PROJECT"_mysql-data "$BACKUP_DIR/volume-names.txt" >/dev/null
while IFS= read -r VOLUME; do
  SHORT=${VOLUME#"$PROJECT"_}
  test "$SHORT" != "$VOLUME"
  docker run --rm --pull never --network none --read-only --memory 256m --entrypoint python \
    --mount "type=volume,source=$VOLUME,target=/source,readonly" \
    --mount "type=bind,source=$BACKUP_DIR,target=/backup" \
    "$IMAGE" -c 'import sys,tarfile; a=tarfile.open("/backup/"+sys.argv[1]+".tar.gz","w:gz"); a.add("/source",arcname="."); a.close()' "$SHORT"
done < "$BACKUP_DIR/volume-names.txt"
tar -czf "$BACKUP_DIR/files.tar.gz" -C "$DATA_ROOT" app-data controlled-files line-media knowledge
(cd "$BACKUP_DIR" && sha256sum *.tar.gz compose.yaml .env nas_appliance.py nas_certificate_maintenance.py maintain-certificates.sh backup-database.sh > SHA256SUMS)
printf 'Backup complete: %s\n' "$BACKUP_DIR"
SH
```

只有完整執行到 Backup complete 且檢查碼驗證成功，才算完成備份；出錯保留該目錄，不把半份備份拿去還原。這種 tar 保存 UID/GID 與一般檔案模式，**不宣稱已備份群暉專用 DSM ACL**；還原 NAS 檔案目錄時仍須依原部署權限重新設定／驗證 ACL，或採已驗證支援該 ACL 的備份方式。

冷資料卷只能在 writer 已停止、同一 MySQL image／平台下還原。完整災難還原先還原至獨立的新測試專案及空白卷／檔案目錄，不覆寫仍保留的來源；原有 DB、憑證和檔案必須同一備份時間點配套還原，通過登入、MFA、資料及檔案回讀後，才另行安排 NAS 入口切換。原 NAS 沒有執行本機測試的任何還原操作。

獨立還原的操作順序：

1. 在備份目錄執行 `sha256sum -c SHA256SUMS`；每個檔案都必須 OK。將備份 compose.yaml／.env 複製到新的還原專案目錄，保留來源備份不動。
2. 只為這個還原專案另設新 COMPOSE_PROJECT_NAME、全新 NAS_DATA_ROOT、未重疊的 NAS_PROXY_SUBNET／NAS_PROXY_API_IP；NAS_IMAGE 與 MYSQL_IMAGE 必須使用備份對應的原 image digest／版本。COMPOSE_PROFILES 暫留空白，且之後必須明確只啟動內網五個服務；備份可能是 Tunnel 啟用版，不能以留空 profiles 就假設 LINE／Tunnel 不會啟動。還原的新副本另設定不重疊的 NAS_TUNNEL_MANAGEMENT_SUBNET／PROXY_IP／API_IP、NAS_TUNNEL_LINE_SUBNET／PROXY_IP／API_IP。不要複製正式 Tunnel token 或先啟動空白 DB。
3. 準備新名稱的 internal data 網路；還原的新網段需另驗最小防火牆規則，不擴大原專案規則。來源網路、卷與入口保留。
4. 依備份 `volume-names.txt` 的邏輯後綴（例如 mysql-data、settings、access-db）逐一建立 `新專案名稱_後綴` 空卷，帶上 `com.docker.compose.project=新專案名稱` 與 `com.docker.compose.volume=後綴` labels。只在這些新空卷中解開對應的 `後綴.tar.gz`，保留 UID/GID／檔案模式；不能解到舊卷。用同一舊映像的 `--entrypoint tar`，將備份唯讀掛到 `/backup`、新卷掛到 `/restore`，執行 `tar -xzpf /backup/後綴.tar.gz -C /restore`。任何新卷已存在或非空就停止確認。
5. 將 files.tar.gz 解到新的 NAS_DATA_ROOT，使四個子目錄回到原結構，並確認 DSM ACL。所有卷、憑證與檔案還原完整後，先把備份中的同版 nas_appliance.py／憑證／備份程式複製到新專案目錄（或讓 NAS_PROXY_RUNTIME_SCRIPT 指向此備份版本），再用新專案名執行 `up -d --no-build --pull never --wait --wait-timeout 180 initialize db configure-security redis management-api`，不要啟動 cloudflared／line-api／對外 Worker。
6. 驗證原 root／工會帳號、MFA、setup 關閉、資料與檔案回讀；來源與還原專案不共用卷／檔案目錄。通過後才安排 DSM 反向代理目的地切換，並確認只有單一正式 writer／對外 Worker 啟用。此入口切換不是本次隔離測試授權的一部分。

### 本機隔離演練與限制

以既有本機映像執行 opt-in 測試，不建置、不上傳，也不使用工作區或 NAS 的實際 .env：

```powershell
$env:NAS_LIFECYCLE_TEST = '1'
.venv\Scripts\python.exe -m pytest tests/domains/global/subsystems/local-runtime/modules/runtime-supervision/test_nas_compose_lifecycle.py -q -s
```

測試只建立隨機命名的 lu-nas-life-* 本機專案、internal 網路與全新資料卷；資料是自行建立的虛構帳號及檔案。失敗保留測試現場及去敏結果供查核。任何來源／還原資料卷都限定該次測試 namespace，不會 prune、讀取既有專案 DB 或呼叫外部 provider。兩個不同 tag 若指向同一 digest，只能證明換版操作與資料保留，不能宣稱不同程式版本的相容性已驗證。

2026-10-20 本機最終結果：34 項相關靜態／單元測試 PASS；1 項實際 Docker 生命週期測試 PASS（包含七個順序階段，約 4 分 15 秒）。正式 Compose 解析後與 NAS 現用修正版相同，全部 profiles 解析 PASS。演練使用既有映像 digest `sha256:33b4d0aa8c65526bc20e03eecb256dce83ed80e8f4934d932677789ea7cb1eda`、MySQL 8.0.46、Redis 7；未建置或上傳映像。

| 隔離情境 | 結果與直接證據 |
|---|---|
| 新環境啟動 | root／工會測試帳號建立及 MFA enrollment／登入成功，工會帳號中心 403 |
| 停止再啟動 | 一次性服務成功退出，DB／API healthy，舊 session 與資料仍可讀 |
| 保留資料強制重建 | 容器 ID 改變，root／帳密 hash／MFA ciphertext／金鑰／測試檔案不變，data network ID 不變 |
| 換版操作 | tag 改為同一映像的 digest，原帳號、設定及檔案保留；不代表不同程式版本相容 |
| 候選服務失敗與回復 | 測試 override 使 API 以 17 退出，套用返回失敗；還原原配置後 healthy、原資料可讀 |
| 冷備份 | 所有本專案 writer 停止且 MySQL 正常退出，保存全部 named volumes 與四個檔案根目錄 |
| 獨立還原 | 解到另一組新空卷／新目錄，原 root／工會帳號實際 TOTP 登入成功、原 session／金鑰與檔案回讀成功 |

API→Redis 的 PING 亦通過。最終去敏結果為 `scratch/nas-lifecycle-bf45b9c64f/result.json`；兩組演練容器已停止，測試卷／備份保留供查核。Docker Desktop Linux／8 GB VM 的結果不代替 DS220+／2 GB、DSM ACL、NAS 防火牆、憑證續期或 Container Manager 的 undefined 問題；這些保持 NOT_RUN，待 NAS 另行實測。不同程式版本、DB schema migration 與正式外部 LINE 收送亦未由本次測試涵蓋。

## 接續驗證順序

1. **已可離線執行：** Python 權限及 Worker 身分測試、申請／核准與回滾模型測試、管理頁面操作測試、前端建置、release manifest 靜態查核。
2. **本機隔離驗證 PASS：** MySQL 8.0.46 的 63 項 engine 情境，涵蓋四 profile、TLS／明文拒絕、26 程序成功／stale、直接 DELETE／DDL／越權程序拒絕、鎖、outer commit／rollback，以及 LINE 申請／工會核准／重送。canonical fresh／preserve-data 升級亦通過；帳號／GRANT DDL 本身不具整批回滾，partial 必須保留現場處理。
3. compact fresh schema 已經 canonical builder 重產為 `labor-union-validation-schema-2026-10-19-v46`：371 tables、377 triggers、1 view、758 statements。來源及 SQL hash gate、新空庫初始化、公開 installer 的零寫入 plan／apply、舊 scoped nas_app 撤權鎖定及 Windows launcher 的隔離庫唯讀 current 檢查均通過。這不代表 NAS 實機或完整應用 E2E 已驗證。
4. 權限安裝預設只做 plan；現有資料先備份、停 writer、跑 preserve-data ordered upgrade，再明確 apply。現有同名帳號若憑證、程序或其他庫權限不符就停止；不刪表、不重設業務資料、不任意變更其他帳號。
5. **本機已按紀錄完成受測情境：** 登入／root、管理／需求核准、本人與跨人拒絕、日誌照片、PDF、月嫂 Excel 匯入、背景工作及重啟持久化；完整監測保存與固定分類畫面通過。最後補驗 Python 42、前端 41 項。Windows 14 項、NAS 實機、真實 Cloudflare／LINE／外部 AI 依使用者指示保留 NOT_RUN；不宣稱所有匯入或 provider 路徑皆已 E2E。
6. **最後才執行 LINE Worker `--check`**：本機最終隔離環境已通過啟動、私人 CA 和獨立機器認證；前後佇列及發送紀錄數量一致。只驗證啟動和私人認證，不跑工作、不發訊息。此設定不代表 LINE 已自動回覆；真正收送與 Cloudflare 外網測試須另行啟用和確認。
7. 全部必要驗收通過後，才用 `scripts.package_nas_preview --secure` 準備經秘密過濾的 build context，建新映像及後續核准的上傳；不可直接拿 repository 根目錄當 Docker build context。

目前記憶體是初始上限，不是實測用量；正式 DS220+ Compose 不設定 NanoCPUS。基本 API 768 MiB、MySQL 512 MiB、Redis 64 MiB；每個 Worker 128 MiB、LINE API 384 MiB、Tunnel 128 MiB，尚不含 DSM。
全部一起啟動的上限已超過 2 GB；須照順序逐組測，PDF／Chromium 可能超限而被終止，接受高延遲並不能避免記憶體不足。
私人 API／DB 初始憑證仍為 90 天；首次執行另附的 DSM 憑證維護工作後才導入可續期 CA。程式準備與 DSM 排程啟用分開，實際維護依 CERTIFICATES.md 驗收，不因更新映像就宣稱已自動續期。

## 選用：逐位機車通勤查詢

1. 在 Google Cloud 建立專案、連結帳務並啟用 Routes API。建立伺服器 API key，API restrictions 僅開 Routes API；有固定對外 IP 時再設定相應 IP restriction。
2. NAS 專案既有 .env 加入 GOOGLE_MAPS_ROUTES_API_KEY，再依本文件保留資料換版流程讓 management-api 載入；本機開發則放在根目錄未納版的 .env 或 process environment。勿使用 VITE_ 前綴、貼入聊天、提交 Git 或列印金鑰。未設定時畫面會顯示尚未設定並停用查詢。
3. 由案件「尋找月嫂與詢問意願」逐位按「查詢機車通勤」；起點採月嫂名冊、終點採本案客戶的縣市與地址。查詢距離不永久保存，重新查詢會增加用量；連線結果未明先確認原操作，系統不自動重試。
4. 本月用量按美國太平洋時間每月重算，所有人員共用；畫面是本系統估算，並保守扣除計費待確認次數。Google 每月免費 1000 次是目前 Compute Routes Enterprise 價格，超額按官方分級費率估計美元未稅金額。
5. 「登錄 Google 帳務核對」可填同一帳務帳戶、全部專案、本月 Compute Routes Enterprise 的累計次數（含免費部分），及報表實際統計截止時間（畫面輸入台灣時間）。核對後只加計截止之後的本系統用量，避免重複計算；其他系統後續用量仍須再次核對。本功能不自動讀取 Google 帳單，不需要帳務服務帳戶金鑰。
6. 在 Google Cloud 設定用量配額與預算通知；預算通知本身不是硬性停止計費開關。Google Maps 內容使用須納入服務條款與隱私告知；Google 金鑰／正式地址測試及實際帳單核對由操作者設定後驗收，本次程式驗證不代表已啟用 Google。

官方設定：[Routes API key](https://developers.google.com/maps/documentation/routes/get-api-key)、[帳務與用量](https://developers.google.com/maps/documentation/routes/usage-and-billing)。
