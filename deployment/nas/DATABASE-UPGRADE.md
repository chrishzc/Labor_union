# NAS MySQL 保留資料升級（DSM 維護工具）

本工具用於對 NAS MySQL（`deployment/nas/compose.yaml`）執行不覆寫原資料卷的冷備份副本升級與設定切換。
日常應用系統運行於工會 Windows 主機，升級前請先透過 `Windows管理.bat` 停止工會電腦服務，再停止 NAS 的 `db` 容器。

1. 確認已完成本專案的完整冷備份（目錄內含 `COMPLETE`、`SHA256SUMS`、SQL 與資料卷壓縮檔），且本專案 `db` 容器已停止。
2. 將 `upgrade-database.sh` 與 `scripts/update_nas_database.py` 放入 NAS 專案目錄（保留原 `.env`、`compose.yaml` 與資料卷）。
3. DSM 工作排程器：建立執行身分 `root`、排程停用的單次任務，替換最後的備份資料夾名稱後手動執行**一次**：

```sh
/bin/bash /volume1/docker/你的專案目錄/upgrade-database.sh --update --backup-dir /volume1/docker/backups/full-實際備份目錄
```

成功為結束碼 `0`、`status=updated`。腳本會自動完成「冷備份副本升級 → 驗證成功才切換邏輯 `mysql-data` 資料卷 → 啟動 NAS `db` 服務」。
失敗即停止後續動作；原資料卷、候選副本與紀錄均保留，不自動清空或覆蓋。

<details>
<summary>進階：分階段操作、原理與失敗回復（一般更新可略過）</summary>

這是手動維護工具，不是每日排程。`upgrade-database.sh` 呼叫 `update_nas_database.py`，在**冷備份的獨立無網路 MySQL 資料卷副本**內重用 `scripts.update_local_database` 的 canonical migration、backfill、journal 與資料驗證。原 MySQL 資料卷保持停止且不掛入升級容器。

## 第一階段：準備並驗證副本

```sh
/bin/bash /volume1/docker/你的專案目錄/upgrade-database.sh --prepare --backup-dir /volume1/docker/backups/full-實際備份目錄
```

成功必須是結束碼 `0`、最後 `status=prepared`；記下輸出的 `run_id`。
若已知 NAS 處理較慢，可在第一次準備前加上 `--timeout-seconds 2400` 調高總上限；不把逾時當成功，也不在未完成副本上盲目重跑。

## 第二階段：切換資料卷設定

只有準備成功才將命令改為以下內容（替換 `RUN_ID`）：

```sh
/bin/bash /volume1/docker/你的專案目錄/upgrade-database.sh --switch --run-id RUN_ID
```

成功必須是結束碼 `0`、`status=configuration_switched`。
此步驟僅將原 `compose.yaml` 的邏輯 `mysql-data` 指向已驗證的新資料卷，原設定備份與驗證紀錄保存在 `database-upgrades/RUN_ID/`。

## 第三階段：啟動與驗收

1. 於 Container Manager（或 `docker compose --env-file .env up -d --wait`）啟動 NAS `db` 服務並確認 `healthy`。**不要用 `.env.example` 覆蓋原 `.env`，也不要用未切換的模板覆蓋剛完成切換的 `compose.yaml`。**
2. 回到工會 Windows 主機以 `Windows管理.bat` 啟動系統（會自動執行唯讀 canonical schema gate），使用原帳號與 MFA 登入確認既有資料與各項查詢／異動正常。
3. 手動確認 `backup-database.sh` 日備份在新資料卷上仍正常運作。

## 失敗與回復

- **準備失敗**：原專案／原設定／原資料卷未切換；保留 `database-upgrades/RUN_ID/` 依錯誤碼排查，勿直接重跑。
- **切換中斷**：先保持服務停止，依 `switch-plan.json` 比對 before／after hash，可從同目錄的 `.env.before`／`compose.yaml.before` 成對回復原設定，不可混搭。
- **新版尚未產生業務寫入時**：先停止工會電腦與 NAS `db`，成對還原 `.env.before`／`compose.yaml.before` 後啟動原資料卷；新資料卷先保留不刪除。
- **新版已接受業務寫入時**：先停止工會電腦與 NAS `db` 並保存新資料卷，完成資料對帳後再決定處置，不可直接切回舊卷而忽略新資料。

</details>
