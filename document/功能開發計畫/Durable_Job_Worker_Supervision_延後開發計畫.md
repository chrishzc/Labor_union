---
status: proposed
priority: deferred
owner: Global / Cloud Operations
domain: Global Durable Jobs
subsystem: Cloud Run Worker Pool
updated_date: 2026-08-16
---

# Cloud Run Durable Job Worker Supervision 延後開發計畫

## 狀態與目標

此計畫依 2026-08-12 人工指示維持暫緩，並依單一 Cloud VPN 雲端部署基線，將原先的
Windows Task Scheduler 主機監督方向改為 Cloud Run Worker Pool runtime supervision。它不構成
cloud project、Cloud Run、IAM、VPN、secret、NAS DB 或 production deployment 的建立／修改授權。

目標是在日後經核准的隔離 cloud test project 中，讓 `union-runtime-workers` Worker Pool 長期監督
durable、LINE 與 incident worker；在程序、revision 或網路故障後，恢復可安全處理的工作，而不將
已接受的 durable command 偽裝成成功或造成重複 Domain write。

## Business scenario 與不變量

1. Business API 在其 outer Unit of Work 內驗證命令、寫入 durable job 後，才回覆 accepted。
2. Worker Pool 的 worker 以短效 OIDC 呼叫受保護的 private operation API；API 擁有 claim、lease、
   idempotency 與 Domain workflow，不由 worker 直接寫 NAS DB。
3. child process 意外退出、Cloud Run revision restart 或正常 shutdown 後，未完成 lease 必須依既有
   recovery 語意重試；不得產生重複 Domain write。
4. 單一 VPN tunnel 或 NAS DB 不可用時，worker 必須 fail closed：停止取得可執行工作、保留可追溯
   typed failure／retry evidence，待 API 與資料庫健康恢復後才續行。

## 預定範圍（重新核准後）

- 一個無公開 HTTP URL 的 Cloud Run Worker Pool：`union-runtime-workers`；v1 固定一個 instance。
- 容器 PID 1 supervisor 管理 durable、LINE、incident 三個 child worker，記錄 child exit、restart
  counter、health／heartbeat 與無法恢復的 permanent failure；後者必須使 instance failure 可由平台
  重新啟動及告警看見。
- Worker 僅持有呼叫 private API 所需的短效 OIDC identity；Direct VPC egress 不得賦予 NAS MySQL
  `3306` 連線路徑、DB credential 或 client mTLS secret。
- 與獨立的 `union-runtime-monitor` Cloud Run Job 建立可觀測性介面；monitor 負責週期健康彙整，
  不擁有 durable queue 的 claim 或業務寫入。
- 單 tunnel 故障測試只驗證明確停止、去敏告警與恢復後安全續行；不宣稱 HA、second-tunnel failover
  或 SLA。雙 tunnel 高可用性另由後續計畫處理。

## Out of scope

- 不再以 Windows Task Scheduler、Windows managed host 或本機登入 session 作為正式 runtime
  supervision 設計；既有 scheduler recovery-only scripts 不變更，也不是此計畫的部署入口。
- 不建立或修改 Cloud Run、Artifact Registry、VPC、VPN、Firewall、IAP、IAM、OIDC service account、
  secret、Cloud Logging／Monitoring 或任何 NAS／production database。
- 不變更 durable queue、lease、idempotency、receipt、Domain workflow、資料庫 schema 或外部 provider。
- `scripts/launchers/start_local_development.bat` 仍只是開發入口；不得因本計畫升格為雲端 supervisor。

## Dependencies 與啟動門檻

- [Cloud Run＋單一 Cloud VPN 雲端部署測試計畫](Cloud_Run_單一Cloud_VPN_部署測試計畫.md) 已被人工
  轉成 exact-scope Work Package，並明定隔離 test project、NAS test DB、operator、預算、資源上限、
  cleanup owner 與故障注入窗口。
- [18 Global Deployment 與治理正式規格](../架構重整/01_規格基線/18_Global_Deployment與治理正式規格.md)
  的 API-only database boundary、OIDC workload identity、artifact digest、rollback 與 receipt 要求。
- 已確認 worker image digest、private API audience、test service account、最小 IAM role 與
  Cloud Run runtime／monitor observability contract；這些值不得記入 Git 或文件。
- 已取得 Cloud test project 與 NAS test DB 的明確操作授權。production target 必須另立部署／cutover
  Work Package，不能由本計畫推定。

## 預定 write set（取得新 Work Package 後再定案）

實際路徑、雲端資源名稱與 IaC owner 必須在最新 integration target 上由新的 exact-scope Work Package
late-bind；本計畫不預留或建立檔案。預期需涵蓋：worker container command／PID 1 supervision、受控
deployment configuration、OIDC／network policy、runtime monitoring、isolated test automation、去敏
receipt 與 rollback／cleanup runbook。

原先設想的 `install_durable_job_worker_task.ps1` 不在本計畫 write set；
`get_durable_job_worker_task_status.ps1` 與 `uninstall_durable_job_worker_task.ps1` 如仍存在，只維持
既有 recovery-only 語意，不得變成 Cloud Run 或 Windows 安裝／啟動入口。

## Acceptance（僅限隔離 cloud test project）

1. Worker Pool 無公開 URL、v1 僅一個 instance，並能以部署 revision／image digest 追溯。
2. worker 可用短效 OIDC 呼叫 private API；未授權 identity 被拒絕，且 worker 不具 DB secret 或 NAS
   `3306` 網路連線能力。
3. 個別 child crash 與不可恢復 fault 會留下去敏 health／restart evidence，並能由平台 restart／告警
   偵測，而非靜默停擺。
4. revision shutdown、restart 與 lease recovery 不造成重複 Domain write；所有結果可由既有
   idempotency／receipt 追溯。
5. VPN／NAS DB outage 時，worker 明確 fail closed；恢復時先證明 API 與資料庫 ready，才恢復 claim。
6. `union-runtime-monitor` 可辨識 worker health／lag 或故障訊號；它不得執行 worker 業務命令。
7. 測試完成後保留最小去敏 deployment、outage、recovery、rollback／cleanup receipt；不含 secret、
   token、帳密或完整內網位址。

## 相關設計

- [單一 Cloud VPN 計畫書](<../雲端部署/計劃書/單一Cloud VPN計畫書.md>)
- 單一 Cloud VPN 雲端部署簡報（current workspace 未保存，不作 activation gate）
- Cloud Run Direct VPC HA VPN 雙 Tunnel 部署計畫（current workspace 未保存，不作 activation gate）

本計畫為 deferred proposal；所有 acceptance 均為 `NOT_RUN`，直到人工建立並核准新的實作
Work Package 為止。
