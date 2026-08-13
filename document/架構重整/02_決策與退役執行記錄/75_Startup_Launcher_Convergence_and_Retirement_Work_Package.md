---
doc_type: work-package
declared_status: in-progress
date: 2026-08-13
owner: Global Deployment / Developer Experience
priority: P1
---

# 75 啟動與本機維運 Launcher 收斂及退役 Work Package

## 1. 人工裁決與 business scenario

2026-08-13 人工要求將分散的啟動腳本集中到單一資料夾、建立腳本 README，並判斷過期入口是否
退役。操作者是本機開發者與 recovery operator；目標是讓入口名稱直接說明實際副作用，避免從
根目錄、`scripts/` 與重複 wrapper 選到不同流程。

同日人工再次確認：開發者必須保有「恢復成模板測試資料庫」能力，因此 `reset_DB.bat` 不能退役；
它與保留資料的 update workflow 是兩條不同入口。

## 2. 核准架構與裁決

- Global：`scripts/launchers/` 是 operator-facing launcher 唯一目錄，README 擁有用途、安全邊界、
  replacement 與 retirement 對照。
- Domain／Subsystem：本案不改業務規則、根事實、transaction 或 worker 行為。
- Module：實際 `scripts/run_*.py`、file watcher 與 migration module 留在 `scripts/`；只搬移外層入口。
- `online.bat`／`.sh` 搬移並改名為 `start_local_development.*`；重複 alias `start.bat` 退役。
- `dev_API.bat` 因名稱與實際「停用認證並啟動全部服務」不符，改名為
  `start_local_development_no_auth.bat`。
- `start_fastapi_ngrok.py` 搬移但維持 development-only；production 禁止 ngrok。
- Durable Job Worker supervision 依既有人工裁決暫緩，因此 installer 退役；status／uninstall 只作
  已安裝排程任務的 recovery 入口。
- `update_local_database.bat` 保留現有資料；`reset_DB.bat` 捨棄現有資料並載入版本化模板 fixture。

## 3. Write set

- 根目錄及 `scripts/` 既有 launcher 的搬移／退役。
- `scripts/launchers/README.md`、launcher path regression tests。
- 本 Work Package、正式 deployment 路徑說明、開發者導覽與 evidence receipt。
- 不啟動服務、不安裝／移除排程任務、不修改任何資料庫或 production configuration。

## 4. Acceptance

1. 所有現行 operator launcher 位於 `scripts/launchers/`，實際 process modules 不被誤搬。
2. README 能清楚區分 active、development-only、recovery-only、moved 與 retired。
3. 模板 reset 先 preflight、再要求 `RESET`，fixture 缺失時不刪 DB。
4. 舊重複／誤導入口有唯一 replacement，且 regression test 防止舊路徑回歸。
5. focused pytest、strict UTF-8 與 `git diff --check` 通過；真實 launcher／DB smoke 未執行前維持
   `in-progress`。
6. 每支 active／recovery launcher 提供零副作用 dry run；不得啟動 process、修改 `.env`、連線 DB、
   查詢／修改排程任務或將缺少依賴誤報為 ready。

模板 fixture 已於既有歷史裁決退役且目前不在 HEAD；2026-08-13 人工明確裁決其重建不屬本次
任務。`reset_DB.bat` 保留 canonical entrypoint 與 fail-closed preflight，但在新 fixture 核准並建立前
不得宣稱模板 reset 可用，也不得直接復活舊 v3 snapshot。

## 5. Evidence

- [`2026-08-13_startup_launcher_convergence_receipt.md`](../03_追蹤清單與證據/evidence/2026-08-13_startup_launcher_convergence_receipt.md)
