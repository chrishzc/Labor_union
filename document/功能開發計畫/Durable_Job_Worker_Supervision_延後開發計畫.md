---
status: proposed
priority: deferred
owner: Global / Operations
domain: Global Durable Jobs
updated_date: 2026-08-12
---

# Durable Job Worker Supervision 延後開發計畫

## 狀態與目標

此項目依 2026-08-12 人工指示暫緩，不屬於目前架構執行範圍，也不構成部署或主機變更授權。
未來若指定 managed app host 需要 24/7 執行 durable commands，再重新確認部署範圍並核准。

目標是在正式 Windows 主機使用 Task Scheduler 監督 durable job worker，避免 API 已接受的
銀行匯入、LINE 發布、通知或其他 durable command 因程序退出、主機重啟或無人登入而長期停留
在佇列中。

## Business scenario

1. API 驗證命令並將 durable job 寫入資料庫後即可回覆 accepted。
2. 背景 worker 從 durable queue claim 命令並呼叫 owning application workflow。
3. Worker 意外退出或主機重啟後，supervisor 恢復處理，不得建立重複 Domain writes。

## 預定範圍

- Windows Task Scheduler task name：`LaborUnionDurableJobWorker`。
- 使用專案虛擬環境執行 `scripts/run_durable_job_worker.py`。
- 開機啟動、單一 instance、異常退出後有限次重啟。
- 提供唯讀狀態查詢及受控安裝、解除安裝入口。

## Out of scope

- 本計畫不授權在任何主機註冊、啟動或移除排程。
- 不變更 durable queue、lease、idempotency、receipt 或 Domain workflow。
- `online.bat` 仍只作本機開發入口，不因此升格為正式 supervisor。

## Dependencies

- 人工指定 managed app host 與部署窗口。
- 確認主機服務帳號、專案路徑及受保護 `.env` 可用。
- 重新確認正式部署及 rollback 權限。

## Write set（重新核准後）

- `scripts/install_durable_job_worker_task.ps1`
- `scripts/get_durable_job_worker_task_status.ps1`
- `scripts/uninstall_durable_job_worker_task.ps1`
- 對應 deployment receipt 與操作文件

## Acceptance

- 排程於指定主機開機後啟動且同時只允許一個 worker。
- Worker 異常退出後依核准策略重啟。
- 唯讀狀態查詢不 claim 或執行任何 business command。
- 重啟與 lease recovery 不產生重複 Domain writes。
- 完成指定主機的去敏 deployment receipt。
