# NAS 內部憑證維護：先保存，稍後在 DSM 設定

本教學適用目前專案 `labor-union-nas-dsm-20261020`。採 DSM 每日排程，不新增常駐 CA 伺服器、公開入口、業務資料表或前端頁面。排程完成前不會自動續期；既有憑證繼續使用至其實際到期日。

本機驗證與 NAS 實機驗收分開；本文件不代表已在你的 NAS 設定成功。Container Manager 的 undefined 問題不由此功能修復，也不需要先停止整個套件。此維護程式不執行 LINE 工作週期。

## 要保存的檔案

| 檔案 | 用途 |
|---|---|
| compose.yaml | 原專案配置，另含 certificates 手動維護服務 |
| nas_certificate_maintenance.py | 憑證維護程式，對應 repository 的 scripts/nas_certificate_maintenance.py |
| maintain-certificates.sh | DSM 排程呼叫的主機腳本 |
| CERTIFICATES.md | 本教學 |
| env-additions.example | 交付包中的選用憑證設定參考；**不能覆蓋 NAS 原本的 .env** |

Python 檔以唯讀方式掛入維護容器，並經標準輸入交給原 API 容器做連線檢查，因此可搭配已下載的 `nas-secure-20261020` 映像，不需先建置／上傳新版映像。未來映像也會由 Dockerfile 的 `COPY scripts/` 納入程式；這次不建置映像。

不需要重建 DB／API 容器才能執行手動 profile。不要把 certificates 加入 COMPOSE_PROFILES，也不要為換證清除／刪除專案或資料卷。

## 一次性 DSM 設定待辦

- [ ] 保存目前 compose.yaml／.env，完成一致性資料備份；備份保留在 NAS 以外。
- [ ] 將上述程式、腳本與新版 compose.yaml 放入原專案目錄；原 .env、專案名稱、NAS_DATA_ROOT、網路及其餘檔案保留。
- [ ] 以 File Station 建立原專案目錄下的 `certificate-maintenance` 資料夾。
- [ ] 設定該資料夾 DSM ACL：停止繼承會開放一般使用者／應用程式存取的權限，只保留必要管理者及系統。不要放進 app-data、controlled-files、line-media 或 knowledge。
- [ ] 設定以下一次性權限工作，再執行不變更憑證的檢查。
- [ ] 設定 DSM 電子郵件通知，實際確認 NAS 管理者能收到測試信。
- [ ] 執行一次正式維護，確認成功後啟用每日排程。

### 1. 選用的 .env 欄位（接受預設值可省略）

以下全部不含密碼，程式／Compose 已內建相同預設值。**採預設政策不必改原 .env**；只有自訂路徑／天數時才加入相應欄位，不重填原專案設定：

```dotenv
NAS_CERT_MAINTENANCE_ROOT=./certificate-maintenance
NAS_CERT_LEAF_DAYS=90
NAS_CERT_RENEW_BEFORE_DAYS=30
NAS_CERT_CA_DAYS=1825
NAS_CERT_ROTATE_BEFORE_DAYS=180
NAS_CERT_OVERLAP_DAYS=30
```

`NAS_DATA_ROOT` 須保留原本絕對路徑；主機腳本不把 .env 當 shell 程式執行，也不展開其中的 `$變數`。維護腳本讀取專案名稱、映像及所需路徑，沒有資料庫密碼。

### 2. 設定一次性權限工作（不用 SSH）

到 DSM「控制台 → 工作排程器 → 新增 → 排程的工作 → 使用者定義的指令碼」。

1. 名稱填 `Labor Union Certificate Setup`，執行身分選 root，暫不啟用自動排程。
2. 在「工作設定 → 使用者定義的指令碼」貼上下列內容。路徑若不同，修改固定的專案目錄那一行；不要使用其他專案目錄。
3. 儲存後手動選「執行」，在「動作 → 檢視結果」確認成功。這段只準備新維護目錄與程式權限，不簽發／套用憑證。

```sh
set -eu
cd /volume1/docker/labor-union-nas-dsm-20261020
test -f compose.yaml
test -f .env
test -f nas_certificate_maintenance.py
test -f maintain-certificates.sh
test -d certificate-maintenance
test ! -L certificate-maintenance
chown 0:0 certificate-maintenance maintain-certificates.sh nas_certificate_maintenance.py
chmod 700 certificate-maintenance
chmod 600 maintain-certificates.sh nas_certificate_maintenance.py
command -v docker
command -v timeout
command -v flock
echo 'Certificate maintenance permissions prepared; certificates unchanged.'
```

root 是 DSM 維護工作的執行身分，不是網站 root，也不會把應用程式改用 root 操作資料庫。Docker 管理權限本身很高，必須限制誰能修改這些程式、compose.yaml、.env 與排程內容；指定本專案目標不是 Docker 的權限隔離機制。程式不將 Docker socket 掛入任何容器。

若缺少 docker／timeout／flock 或權限檢查失敗，保留結果並停止，不自行安裝陌生工具或停用權限限制。具體 DSM 版本仍需實機確認這些主機工具與 ACL。

### 3. 建立每日維護工作，先只做檢查

新增同類工作，名稱填 `Labor Union Certificate Maintenance`，身分 root。設定每日一次、低使用量時段，先取消「啟用」。

先填入：

```sh
/bin/bash /volume1/docker/labor-union-nas-dsm-20261020/maintain-certificates.sh --check
```

儲存、手動執行；結果應包含兩組 CA／三張服務憑證的到期時間。`managed:false` 代表尚未導入可續期 CA，不代表資料庫損壞。此檢查只讀憑證，但會建立排程鎖定檔；不更新憑證、不重啟服務。

### 4. 設定通知並測試

到「控制台 → 通知設定 → 電子郵件」完成寄送設定並寄測試信，收件人使用 NAS 管理者維運信箱。登入／授權資訊只放 DSM，不放 .env、Image 或教學。

在每日工作的「工作設定」勾選「透過電子郵件傳送執行詳細資料」與「僅在指令碼異常結束時傳送」。有需要可啟用「儲存輸出結果」，目的資料夾限制管理者存取。不要將含私鑰的 maintenance 整個目錄當一般郵件附件。

可暫建一個**停用排程**的通知測試工作，身分 root，使用以下固定內容後手動執行。它不呼叫 Docker、不更動專案：

```sh
echo 'TEST ONLY: certificate maintenance notification delivery check; no project changes.'
exit 2
```

必須實際收信才算通知通過；這是通知測試，不是模擬服務故障。測完維持停用，不能讓它每日寄信。

### 5. 首次正式執行與啟用自動排程

確認備份及通知完成後，安排短暫維護時間。將每日工作的指令改為：

```sh
/bin/bash /volume1/docker/labor-union-nas-dsm-20261020/maintain-certificates.sh --apply
```

手動執行一次，看到 `status:completed` 後確認原 root／工會帳號可登入、資料與檔案仍在，最後才啟用每日排程。首次會把原本未保存簽發私鑰的兩組 CA，更新成可續期的管理狀態；不重新初始化業務資料。

若只啟動 DB、沒有任何執行中的 API，維護工作不能完成新 DB 連線驗證，不會把它冒充全數通過。維護過程只重新啟動原本 running／restarting 的對應服務，不啟動原本停用的 LINE、Worker、Tunnel。若本專案全部停止，僅能離線驗證檔案，仍須在之後啟動時實測連線。

## 執行結果怎麼看

| 結果 | 意義與處理 |
|---|---|
| unchanged，結束碼 0 | 尚未接近到期，沒有重啟服務 |
| completed，結束碼 0 | 本次憑證套用完成；執行中的 API／DB 已做新連線驗證 |
| failed，recovery=verified_previous_certificates，結束碼 2 | 本次換證失敗，已回復並驗證前一組；仍寄信讓管理者知道 |
| blocked／requires_administrator／journal_preserved，結束碼非 0 | 維持／保留可用現場與階段紀錄，管理者查看原因；不能刪資料卷或重新初始化 |
| 主機 timeout 結束碼 | 本次工作超出時間，保留階段紀錄，下一次可嘗試完成；若持續失敗交維運處理 |

排程同時執行會被 flock 阻止；單次 Docker 操作最多等待 45 秒，整次協調工作最多 600 秒，之後給 30 秒結束處理。這不是長時間保活，也不會停止整個 Container Manager。中斷後可由 DSM 手動執行同一工作重試，不能只因上一回傳非 0 就假設所有檔案已回復。

## 自動續期、CA 輪替與回復範圍

- 服務憑證剩餘 30 天時，以同一 CA 簽發新憑證；CA 剩餘 180 天時建立新 CA。
- CA 先發布新舊共同信任，再更換服務憑證；重疊 30 天後另次工作才移除舊 CA 信任。
- 簽發容器無網路、無 DB 密碼、無業務資料卷、無 Docker socket。DB reload 使用主機端在 DB 容器內的既有本機維運途徑，密碼不進命令參數或輸出。
- MySQL 使用 `ALTER INSTANCE RELOAD TLS` 的預設失敗回滾；API 重啟載入新憑證；有啟用 Tunnel 時更新其 origin CA 信任。不使用 `NO ROLLBACK ON ERROR`、HTTP fallback 或略過憑證驗證。
- 憑證備份及階段紀錄位於 certificate-maintenance/transactions；目前保留歷次小型憑證備份，不清理任何業務資料。這些備份含私鑰，必須按私鑰管理。
- 原 root／工會帳號、MFA 金鑰、DB 密碼及 GRANT、Worker token、照片／履歷／合約、資料卷與 internal 網路保持原位。
- 原有 app-data 下兩個公開 CA 檔案會同步更新；使用獨立 UID 1000 的無網路複製容器，沒有簽發私鑰，避免主機 root 跟隨應用資料中的惡意符號連結。
- 舊憑證已過期時不能退回過期備份冒充成功；候選流程與簽發私鑰仍可由維護工作處理，不依賴 API 健康。但私鑰遺失／檔案損壞仍需管理者處理，不能直接清空目錄讓它重建。

## 備份與交接

既有一致性備份之外，新增備份原專案中的 Python 程式、shell 腳本及 certificate-maintenance 整個目錄。內含 CA 私鑰，限制存取、保護離機副本。DSM 專用 ACL 需另保存／驗證，普通 tar 不等於保存全部 ACL。

交接時保存：排程名稱、每日執行時間、維運收件人、備份位置及本教學。兩天後再設定也要回來完成上方核取清單；更新 Image／放好檔案本身不會建立 DSM 工作。

本機可驗證程式、Linux 權限、真實 TLS、MySQL reload、原登入／MFA／業務檔案與回復；DSM 真正排程與收信、ACL、2 GB 負載仍須 NAS 實機驗收。NAS 整台停機或通知寄送本身故障時，同機排程不能保證通知送達。

官方依據：[DSM 工作排程器](https://kb.synology.com/index.php/en-ro/DSM/help/DSM/AdminCenter/system_taskscheduler?version=7)、[MySQL TLS 動態重新載入](https://dev.mysql.com/doc/refman/8.0/en/using-encrypted-connections.html)。
