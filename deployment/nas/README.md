# NAS MySQL 資料庫正式部署與維運說明

本目錄僅負責 **NAS 端 MySQL 8.0 資料庫容器、每日不停機 SQL 備份與資料庫保留資料升級**。

正式架構已定案為：

- **工會電腦（Windows）**：執行 FastAPI 後端、React 管理端、背景 Workers、LINE Webhook 與 Cloudflare Tunnel（由專案根目錄 `Windows管理.bat` 與 `docker-compose.yml` 的本機 Redis 驅動，操作詳見 [`scripts/launchers/WINDOWS-REMOTE.md`](../../scripts/launchers/WINDOWS-REMOTE.md)）。
- **NAS（Synology Container Manager）**：僅運行本目錄 `compose.yaml` 的 `db`（MySQL 8.0）服務，透過內網固定 IP 提供工會電腦連線，**不對外網公開 Port 3306，也不在 NAS 運行網站、Workers 或 Tunnel**。

---

## 一、目錄檔案清單

| 檔案 | 用途 |
|---|---|
| `compose.yaml` | NAS Container Manager 專用的純 MySQL 8.0 部署設定 |
| `.env.example` | 環境變數範本（複製為 `.env` 填入 `NAS_DB_BIND_IP`，不含密碼） |
| `mysql-client.cnf` | MySQL client 預設 `utf8mb4` 字元集設定 |
| `backup-database.sh`／`SQL-BACKUPS.md` | DSM 每日凌晨 03:00 不停機匯出 InnoDB SQL 快照備份 |
| `upgrade-database.sh`／`DATABASE-UPGRADE.md` | 獨立資料卷副本的保留資料 schema 升級維護工具 |

---

## 二、首次部署步驟（NAS 端＋工會電腦初始化）

1. **準備 NAS 專案目錄與密碼檔**：
   - 在 NAS 建立專用資料夾（例如 `/volume1/docker/labor-union-nas-db`），上傳本目錄檔案並將 `.env.example` 複製為 `.env`，填入 NAS 內網固定 IP `NAS_DB_BIND_IP`。
   - 建立受管理者權限保護的 `mysql-secrets/` 子目錄（`chmod 700`），分別建立單行無換行密碼檔 `root-password` 與 `app-password`（`chmod 600`，勿放入 `.env` 或 Git）。
2. **限制區網防火牆**：
   - 於 DSM「控制台 → 安全性 → 防火牆」設定 TCP `3306` **僅允許工會電腦內網 IP**，其餘來源一律拒絕；路由器嚴禁轉發 3306 至外網。
3. **啟動 MySQL 容器**：
   - 於 Synology Container Manager 新增專案，選擇上述目錄與 `compose.yaml` 啟動，等待 `db` 狀態變為 `healthy`。
4. **從工會電腦初始化正式 Schema**：
   - 在工會電腦 `.env` 填好 NAS 的 `DB_HOST`、`DB_PORT=3306`、`DB_USER`、`DB_PASSWORD`、`DB_DATABASE=union_db`（並授予初始化所需的 DDL／trigger／view／routine 權限）。
   - 於工會電腦雙擊執行 `scripts\launchers\initialize_nas_schema.bat`，通過預檢後輸入 `Y` 完成 371 張表與必要系統資料初始化。
5. **設定每日自動備份**：
   - 依 [`SQL-BACKUPS.md`](SQL-BACKUPS.md) 在 DSM 工作排程器設定每日 03:00 執行 `backup-database.sh`。
