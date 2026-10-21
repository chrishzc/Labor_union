# 每日凌晨 3 點：不停機 SQL 備份

這份操作單供稍後設定 DSM。只新增 `backup-database.sh` 與一個獨立排程，**不改 Compose／.env、不更新映像、不停止服務、不執行還原**。憑證更新另排時段，例如凌晨 2 點。

## 備份範圍

每日 03:00（DSM 時區）匯出本專案 MySQL 的結構、資料、view、預存程序／函式、trigger、event 定義。採 `mysqldump --single-transaction --quick` 的 InnoDB 一致性快照，串流壓成 SQL gzip；不停止 API／Worker，不執行全域讀鎖。快照開始後提交的資料留待下一份。執行時增加 CPU／磁碟負載，不能保證回應時間完全不受影響。

所有基礎資料表都須為 InnoDB，且資料庫非空，否則工作失敗，不改用鎖表。**備份期間不要改表結構、部署 migration 或執行 TRUNCATE**；快照不保護這些管理操作。參考 [MySQL 官方說明](https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html)。

本次只備份 SQL，**不含照片、履歷等實體檔案、.env、MFA 加密金鑰、Worker token、CA 私鑰或 MySQL 帳號與 GRANT**。SQL 的檔案紀錄不等於實體檔案。完整災難還原仍須保留原 named volumes／金鑰／檔案，見 README 原有冷備份流程。

不新增 DB 帳號、GRANT 或資料表。DSM root 維護工作核對 DB 容器／卷的專案歸屬後，才在 DB 內使用既有 root 密碼與 Unix socket 執行唯讀匯出；密碼不進 NAS 命令列或輸出，一般應用仍使用原受限帳號。

## 1. 準備程式與獨立資料夾

1. File Station 將 `backup-database.sh` 放到既有專案 `/volume1/docker/labor-union-nas-dsm-20261020`，保留 LF 換行。不要覆蓋原 Compose／.env／憑證程式。
2. 在 DSM 建立專用備份資料夾，不能位於專案資料夾或任何容器掛載路徑裡。以下示範 **`/volume1/backup/labor-union-sql`，需改成你的實際路徑**；`backup` 是「控制台 → 共用資料夾」建立或既有的備份分享。
3. DSM ACL 限定管理者使用，移除一般使用者／工會帳號／容器身分及不適當繼承授權，不提供網站下載。SQL 含完整個資；gzip 只壓縮，沒有加密。這個位置不用掛入 Compose。

## 2. 一次性權限準備，不用 SSH

DSM「控制台 → 工作排程器 → 新增 → 排程的工作 → 使用者定義的指令碼」，使用者選 **root**，名稱「工會 SQL 備份權限準備」，先取消啟用排程。貼上後手動執行一次：

```sh
set -eu
cd /volume1/docker/labor-union-nas-dsm-20261020
test -f backup-database.sh
test -f .env
test -d /volume1/backup/labor-union-sql
test ! -L /volume1/backup/labor-union-sql
chown 0:0 backup-database.sh /volume1/backup/labor-union-sql
chmod 600 backup-database.sh
chmod 700 /volume1/backup/labor-union-sql
command -v docker
command -v timeout
command -v flock
command -v gzip
command -v sha256sum
echo 'SQL backup permissions prepared; database unchanged.'
```

確認成功後，該準備工作保持停用。POSIX 700 不代替 DSM ACL，兩者都需檢查；不要為一般帳號下載 SQL 而放寬權限。

## 3. 建立每日工作，先手動驗證

新增另一個 root 使用者定義工作「工會每日 SQL 備份」，選 **每日 03:00**，先保持停用。在 DSM「控制台 → 通知」設定並測試管理者 email，再於工作設定勾選傳送執行詳細資料、僅異常結束時寄送。不在映像／.env 增加 SMTP 密碼。

先貼上檢查指令，手動執行：

```sh
/bin/bash /volume1/docker/labor-union-nas-dsm-20261020/backup-database.sh --check --backup-dir /volume1/backup/labor-union-sql
```

應回傳 JSON `status=ready`；只查狀態／引擎／路徑，不匯出或停止服務。然後改成正式指令，手動執行一次：

```sh
/bin/bash /volume1/docker/labor-union-nas-dsm-20261020/backup-database.sh --backup --backup-dir /volume1/backup/labor-union-sql
```

應回傳 `status=completed`，目的地出現 UTC 日期目錄，例如 `20261020T190000Z`，相當於台灣 10/21 凌晨 3 點。裡面有 `database.sql.gz`、`metadata.txt`（DB／版本／表和程序數量）、`SHA256SUMS`、`COMPLETE`。確認管理介面仍可查詢及合法寫入後，再啟用排程。

要測異常郵件，可另建一個保持停用的測試工作，指令只寫 `echo SQL_BACKUP_NOTIFICATION_TEST; exit 2`，手動執行並確認收信，不接觸 DB。

預設整份備份上限 3600 秒，避免故障工作永久卡住；資料量增加時可在指令末尾加 `--timeout-seconds 7200` 改成兩小時。這不是網頁上傳等待時間。單次 metadata／Docker 檢查最多 30 秒。同一目的地已有備份執行時，第二份立即失敗，不重複匯出。

## 4. 失敗、保存與容量

- 歷史備份**永久保留，不自動刪除、輪替或覆蓋**。目的地不可寫、匯出失敗、磁碟滿、逾時、檢查碼錯誤都以非零結束，讓 DSM 通知。
- 匯出中使用 `.partial-日期` 目錄，全部成功才改為正常日期目錄。**partial 即使有 COMPLETE 也不能還原**；中斷可能留下它，供管理者確認後自行處理，程式不清理。
- 成功代表 gzip 可完整讀取、SQL 有完成尾註、SHA-256 驗證通過；不代表每天已執行還原測試。
- 永久保存會累積容量。請確認 DSM 儲存空間管理員的容量不足告警，並在「控制台 → 通知」啟用對應通知；收到告警後擴充／移轉備份。滿碟可能影響同儲存空間的其他服務。同 NAS 備份不能防整台 NAS 故障，另存設備可後續用 Hyper Backup 設定。
- NAS 關機／通知網路故障時，本機排程不能保證寄信；首次啟用後隔日確認新目錄確實產生。

## 5. 還原與待辦

腳本沒有還原操作，不寫回正式 DB。復原前先驗 SHA256SUMS，將 SQL 匯入同版本的**全新隔離 MySQL**，保留舊 DB，再確認中文、資料、view、預存程序、trigger、event。預存程序含 DEFINER，完整應用還原還需要原受限 DB 帳號／GRANT、settings／MFA 金鑰和實體檔案；不把 SQL 單獨匯入當成完整災難復原。

- [ ] 程式已放原專案；Compose／.env／映像未改。
- [ ] 目的地 root 700、DSM ACL、容器不可存取已確認。
- [ ] check／backup 成功，服務仍可使用，舊備份保留。
- [ ] 異常郵件實際收到，容量告警啟用。
- [ ] DSM 時區正確；每日 03:00 與憑證維護／migration 避開。
- [ ] 啟用後隔日確認新備份產生。

本機驗證結果見交付包 validation.json。DSM 排程、ACL、實際寄信及 2 GB NAS 負載仍待實機驗收；尚未登入 NAS 或建立每日工作。
