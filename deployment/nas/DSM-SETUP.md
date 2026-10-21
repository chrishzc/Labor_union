# NAS 整合維護包：先保存，之後照這份設定

本包供既有 `labor-union-nas-dsm-20261020` 安裝使用，沿用 `chris23144638/cecec:nas-secure-20261020` 映像。包含完整 Compose、內部憑證維護及不停機 SQL 備份；不是 Docker 映像，也不是現有資料的備份。

**保留 NAS 原本的 `.env`、專案名稱、資料卷、檔案路徑、網路、root／工會帳號和既有資料。** 包內沒有實際 `.env`、密碼、私鑰、SQL 資料或照片。放置程式／更新映像都不會自動建立 DSM 排程；以下工作要日後在 NAS 設定。此次交付沒有操作 NAS。

## 一、先看清楚本次會做什麼

| 項目 | 安排與效果 |
|---|---|
| 憑證維護 | 每日 02:00 執行檢查；需要續期／CA 輪替才套用。真正換證時會短暫重啟原本執行中的相關 API／Tunnel，DB 只 reload TLS；不重建資料庫、不重設帳號。 |
| SQL 備份 | 每日 **03:00**，不停止／重啟服務；使用 InnoDB 快照匯出本專案結構、資料、view、程序／函式、trigger 和 event，壓縮後永久保存。 |
| 通知 | 兩個獨立 DSM 工作共用 DSM 電子郵件設定；異常結束才通知，回復成功的換證失敗也通知。 |
| 管理入口 | 沿用目前的內網 DNS、DSM DDNS／Let’s Encrypt 及反向代理。這份內部憑證腳本不替 DSM 公開憑證續期，也不調整管理入口。 |

SQL 備份期間可以查詢／寫入，但會增加 CPU／磁碟負載，不保證速度完全不受影響；不要同時部署 migration 或修改資料表結構。它**不包含照片／履歷實體檔案、MFA 金鑰、CA 私鑰、Worker token 或 MySQL 系統帳號與 GRANT**，不能取代完整災難備份。

永久保存指不自動刪除歷史 SQL；需要設定容量不足通知。同 NAS 副本不能防整台 NAS 故障。

## 二、包內檔案及需要填的地方

| 檔案 | 用途 |
|---|---|
| `README.md` | 本份統一設定步驟，先讀這份即可。 |
| `compose.yaml` | 完整既有服務配置，已包含手動 `certificates` 維護服務；SQL 備份不需要額外容器。 |
| `maintain-certificates.sh`、`nas_certificate_maintenance.py` | DSM 憑證維護程式。 |
| `backup-database.sh` | DSM 不停機 SQL 備份程式。 |
| `env-additions.example` | 可選憑證政策，**接受預設值就不用加入原 `.env`，不要另存取代 `.env`**。 |
| `CERTIFICATES.md`、`SQL-BACKUPS.md` | 個別功能、錯誤與回復的詳細說明。 |
| `OPERATIONS.md` | 原部署／重啟／更新／完整冷備份與獨立還原參考；這次安裝維護程式不需要執行重建或冷備份命令。 |
| `cloudflared.example.yaml` | 原有選用 Tunnel 的設定範例，不含實際憑證；本次保留原 Tunnel 設定，不啟動新 LINE 工作。 |
| `validation.json`、`SHA256SUMS` | 驗證來源、限制及交付檔案檢查碼。 |

後續指令採以下路徑，請先確認：

| 設定 | 此份教學的值／需自行填寫 |
|---|---|
| 原專案路徑 | `/volume1/docker/labor-union-nas-dsm-20261020`；若你已搬到其他位置，所有指令的專案路徑一起替換。 |
| 憑證維護目錄 | 原專案下的 `certificate-maintenance`；預設不用填 `.env`。若原 `.env` 已自訂 `NAS_CERT_MAINTENANCE_ROOT`，沿用該位置並修改權限準備步驟，不能換成空白目錄。 |
| **SQL 備份目的地〔需填〕** | 範例 `/volume1/backup/labor-union-sql`；請替換成你建立的 NAS 獨立資料夾。不能在專案內或任何容器掛載路徑內。 |
| **通知收件人〔需填〕** | DSM 設定 NAS 維運管理者信箱；不寫進 `.env` 或程式。 |

**沒有新增必填網域。** 原 `.env` 的 `COMPOSE_PROJECT_NAME`、`NAS_IMAGE`、`NAS_DATA_ROOT`、`NAS_BIND_IP`、`NAS_PROXY_SUBNET`、`NAS_PROXY_API_IP`、LINE／Tunnel 設定與 `COMPOSE_PROFILES` 沿用；不要新增 `certificates` 到一般啟動 profiles。每日時間使用 DSM 時區，確認為 Asia/Taipei。

## 三、File Station 放置檔案，保留原部署

1. 先保存目前 NAS 的 `compose.yaml`／`.env` 至管理者保護的位置，作為設定回復參考；不要寄出／公開 `.env`。原有資料備份保留不動。
2. 將本包解壓到電腦，或先用 File Station 解壓到獨立暫存資料夾。**只把以下四個檔案放到原專案目錄**：`compose.yaml`、`maintain-certificates.sh`、`nas_certificate_maintenance.py`、`backup-database.sh`。教學可留在電腦保存。不要更動原 `.env`／`tunnel`／資料目錄。
3. Compose 已包含現有服務及新的 certificate-maintenance profile，沒有 NanoCPUS、沒有公開 MySQL／Redis 埠。它沿用原 `.env` 及原 `${COMPOSE_PROJECT_NAME}_data` 網路。若你之後曾另外客製 NAS 的 Compose，先比較那些變更，不能把客製設定當成可以直接覆蓋；目前包依本專案已驗證的正式版本產生。
4. 在原專案下建立 `certificate-maintenance` 資料夾；若已存在維護狀態就保留，**不要清空或用別份 CA 狀態覆蓋**。
5. 建立 SQL 獨立備份資料夾。範例的 `backup` 是 DSM「控制台 → 共用資料夾」建立或既有的備份分享，再於 File Station 建立 `labor-union-sql`。
6. 兩個新增資料夾設定 DSM ACL，移除一般使用者／工會帳號／容器執行身分及不適當繼承授權；僅必要管理者／系統可存取。程式、Compose、`.env` 及排程內容也只能由可信管理者修改。POSIX 700 不代替 DSM ACL。

這次不用在 Container Manager 建立新專案、重建或重新啟動現有容器。憑證腳本會直接讀取原目錄這份 Compose 執行一次性 profile；現有 DB／Redis／API 繼續使用，尚未啟用的 LINE／Worker／Tunnel 保持停用。不要使用「清除／刪除資料卷」來套用檔案，也不要為這次維護更改原專案名稱。

## 四、一次性 DSM 權限準備

到「控制台 → 工作排程器 → 新增 → 排程的工作 → 使用者定義的指令碼」，執行身分選 **root**，名稱「工會維護權限準備」，排程先保持停用。貼上以下內容，**先把備份路徑改成實際值**，儲存後手動執行一次：

```sh
set -eu
cd /volume1/docker/labor-union-nas-dsm-20261020
test -f compose.yaml
test -f .env
test -f maintain-certificates.sh
test -f nas_certificate_maintenance.py
test -f backup-database.sh
test -d certificate-maintenance
test ! -L certificate-maintenance
test -d /volume1/backup/labor-union-sql
test ! -L /volume1/backup/labor-union-sql
chown 0:0 certificate-maintenance maintain-certificates.sh nas_certificate_maintenance.py backup-database.sh /volume1/backup/labor-union-sql
chmod 700 certificate-maintenance /volume1/backup/labor-union-sql
chmod 600 maintain-certificates.sh nas_certificate_maintenance.py backup-database.sh
command -v docker
command -v timeout
command -v flock
command -v gzip
command -v sha256sum
docker --host unix:///var/run/docker.sock compose --env-file .env -f compose.yaml config --quiet
echo 'Maintenance permissions and Compose syntax checked; no certificates or database data changed.'
```

在工作排程器查看結果，確認成功。這段不讀出密碼、不換證、不備份 SQL、不停止服務；不修改 `.env`。完成後此準備工作保持停用。root 是 DSM 的維護執行身分，不是把網站／應用改用 MySQL root。若工具或權限檢查失敗，保存錯誤代碼處理，不停用安全限制或重設 DB。

## 五、DSM 通知只設一次

1. 在「控制台 → 通知 → 電子郵件」設定維運信箱並寄測試信；實際收到才算通過。寄件憑證只存在 DSM。
2. 後續兩個每日工作都勾選「透過電子郵件傳送執行詳細資料」及「僅在指令碼異常結束時傳送」。若要儲存工作輸出，使用管理者保護的位置，不要把含私鑰的維護目錄當附件。
3. 可另建一個**停用排程**的通知測試工作，指令為 `echo MAINTENANCE_NOTIFICATION_TEST; exit 2`，手動執行並確認異常信。它不呼叫 Docker 或修改資料，測完維持停用。
4. 同時確認儲存空間管理員的容量不足告警及 DSM 對應通知。永久備份不會自行釋放空間；收到告警要安排擴充／移轉，不等磁碟滿才處理。

## 六、SQL 工作：每日 03:00，不停機

建立另一個 root 使用者定義工作「工會每日 SQL 備份」，每日 **03:00**，先保持停用。將以下目的地改成實際路徑後，先手動執行檢查：

```sh
/bin/bash /volume1/docker/labor-union-nas-dsm-20261020/backup-database.sh --check --backup-dir /volume1/backup/labor-union-sql
```

應回傳 `status=ready`；查核 DB 歸屬、非空 InnoDB 資料庫及目的地，不匯出／停止服務。再改為正式內容，手動執行一次：

```sh
/bin/bash /volume1/docker/labor-union-nas-dsm-20261020/backup-database.sh --backup --backup-dir /volume1/backup/labor-union-sql
```

應回傳 `status=completed`，新日期目錄內有 `database.sql.gz`、`metadata.txt`、`SHA256SUMS`、`COMPLETE`。檔名時間採 UTC；例如 `20261021T190000Z` 是台灣 10/22 凌晨 3 點。確認管理介面仍能查詢／合法修改資料後，才啟用每日排程；次日確認另一份備份有產生。首次先完成這份 SQL 備份，再往下設定憑證套用；SQL 仍不能代替原有完整資料／金鑰備份。

預設備份作業上限 3600 秒，不是等待一小時才開始；大量資料可在指令末尾加 `--timeout-seconds 7200`。備份不刪舊檔、不自動還原，失敗保留 `.partial-日期` 並非零通知；partial 不能用作還原。gzip／完成尾註／檢查碼驗證通過才發布正常日期目錄，不等於每天都做還原演練。

## 七、憑證工作：每日 02:00，先檢查再啟用

建立另一個 root 使用者定義工作「工會內部憑證維護」，每日 **02:00**，先保持停用。工作設定先貼：

```sh
/bin/bash /volume1/docker/labor-union-nas-dsm-20261020/maintain-certificates.sh --check
```

手動執行，應顯示兩組 CA／三張服務憑證的到期狀態。`managed:false` 代表尚未導入管理狀態；這次檢查不換證、不重啟服務，但會建立鎖定檔。

確認備份／通知及原服務正常後，在可接受短暫 API 重啟的時段，將工作改為以下內容並手動執行一次：

```sh
/bin/bash /volume1/docker/labor-union-nas-dsm-20261020/maintain-certificates.sh --apply
```

首次導入或真正換證成功會回傳 `status=completed`；沒有到期需求則為 `unchanged`。確認原 root／工會帳號可登入，資料和檔案仍可讀後，才啟用每日排程。DB 與至少一個原本使用的 API 應正常執行，才有實際新連線驗證；不能只憑離線檔案檢查宣稱服務健康。

服務憑證預設 90 天、剩 30 天續期；CA 預設 1825 天、剩 180 天輪替，新舊 CA 重疊 30 天。這些預設已寫在程式／Compose，不必更改 `.env`。詳見 CERTIFICATES.md。維護最多 600 秒加結束處理時間，不用長時間等待保活。

## 八、失敗時怎麼處理

| 情況 | 做法 |
|---|---|
| 權限／工具／Compose 檢查失敗 | 每日工作保持停用，確認具體錯誤、目錄與 DSM 工具，保留原服務；不為排錯停止整個 Container Manager。 |
| 換證失敗但已回復 | 仍會收到非零通知；確認服務可用，依 CERTIFICATES.md 看 recovery 狀態。 |
| 換證要求人工處理／逾時 | 保留 certificate-maintenance 中的私鑰、journal 和 transactions；不要清空、重跑初始化或降級 TLS。不是所有中斷都已完成回復。 |
| SQL 備份失敗 | 原 DB 與舊備份保留，檢查容量／權限／引擎與工作結果；排除後手動執行同一工作，不拿 partial 還原。 |
| 只想停用維護功能 | 在 DSM 停用兩個每日工作，現有應用與資料保持原位；憑證未續期仍會到期，需交接處理。 |

備份需要的帳密／金鑰與業務檔案保留在原資料卷。憑證維護目錄也須納入管理者保護的完整備份，SQL 日備份不會包含它。完整冷備份及新環境還原參考 OPERATIONS.md；這次不要執行正式還原／切換。所有排程都在 NAS 上，NAS 關機或通知本身故障時，不能保證寄信。

## 九、之後回來設定時的核取清單

- [ ] 已保存原 Compose／.env，原專案名稱、資料卷與路徑沒有改。
- [ ] 四個程式／Compose 已放原目錄，未覆蓋 `.env`、未重建容器或下載新映像。
- [ ] 維護目錄、SQL 獨立目的地、POSIX 權限與 DSM ACL 已確認。
- [ ] 一次性準備工作成功；完成後保持停用。
- [ ] DSM 時區、通知測試與容量告警已確認。
- [ ] 憑證 check／apply 成功，原登入／MFA／資料／檔案正常。
- [ ] SQL check／backup 成功，備份四個檔案完整，服務持續可用。
- [ ] 每日 02:00 憑證工作、03:00 SQL 工作已分別啟用；次日確認結果。

## 驗證範圍

整合包沿用先前通過的憑證功能 63 個情境、SQL 備份 9 個情境；這次以檔案雜湊確認完整 Compose 與三個程式逐位元一致，再驗合成環境的全 profiles Compose、教學命令與 ZIP 清單／檢查碼。沒有重新宣稱已驗證實際 DSM。

工作區仍有兩個非本任務的既有測試歸屬問題，見 validation.json；不將整個工作區標成全部通過。DSM 排程、實際寄信、ACL、2 GB NAS 負載、GUI undefined 與 NAS 實際套用仍未驗收。本包無實際 `.env`／秘密、未操作 NAS、未建置／上傳映像。
