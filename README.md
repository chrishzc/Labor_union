# 新竹市月子照顧服務人員職業工會－行政流程系統

本專案提供案件與月嫂排班、訂單生命週期、客戶帳務、服務人員應付、銀行流水匯入、政府補助、LINE 整合與內部管理功能。

目前管理端唯一 current UI 是 `ui_react/`；正式業務操作由 React 經 FastAPI 呼叫 Application workflow，再由 owning Domain 與 MySQL 完成。舊 `ui/` Streamlit tree 已退役並從工作樹移除，不再是入口、rollback 或驗證來源。

## 本機啟動

以下命令從 repository root 執行。先以 Python 3.11 以上建立 `.venv`；已有環境時沿用，不重建。尚未建立時，Windows 執行 `python -m venv .venv`，macOS／Linux 執行 `python3 -m venv .venv`。

開發／測試環境需安裝 `requirements.txt` 的 runtime pins，以及 `pyproject.toml` 既有的 `dev` 群組（含 `pytest`）。`--group` 需要 pip 25.1 以上；下列命令先滿足此前提，再一併安裝 runtime 與開發依賴。

Windows 依賴安裝：

```powershell
.\.venv\Scripts\python.exe -m pip install "pip>=25.1"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt --group dev
cd ui_react
npm ci
cd ..
```

macOS／Linux 依賴安裝：

```bash
./.venv/bin/python -m pip install "pip>=25.1"
./.venv/bin/python -m pip install -r requirements.txt --group dev
cd ui_react
npm ci
cd ..
```

只需執行應用而不跑 Python 測試時，可省略 `--group dev`；僅安裝 runtime pins 不包含測試依賴。Dependency group 的命令語意見 [pip 官方說明](https://pip.pypa.io/en/stable/user_guide/#dependency-groups)。

Windows 啟動：

```powershell
.\scripts\launchers\start_local_development.bat --dry-run
.\scripts\launchers\start_local_development.bat --smoke-test
.\scripts\launchers\start_local_development.bat
```

macOS／Linux：

```bash
./scripts/launchers/start_local_development.sh --dry-run
./scripts/launchers/start_local_development.sh
```

標準開發入口為 FastAPI `127.0.0.1:8000` 與 React/Vite `127.0.0.1:5173/admin/`。啟動器不會啟動 Streamlit。

## 本機資料庫

更新程式後先執行唯讀檢查，再套用已存在的 additive migration：

```powershell
.\scripts\launchers\update_local_database.bat --dry-run
.\scripts\launchers\update_local_database.bat
```

需要捨棄本機資料並建立空白 current schema 時才使用：

```powershell
.\scripts\launchers\reset_DB.bat --dry-run
.\scripts\launchers\reset_DB.bat
```

`reset_DB.bat` 是破壞性操作；不得用於需要保留的資料庫。

## 程式定位

```text
api/                 FastAPI routes、dependencies、Pydantic schemas
domains/             Domain 根事實、狀態機與業務規則
subsystems/          Query／Preview／Apply workflow、跨 Domain 協調與 workers
infrastructure/      MySQL、HTTP、LINE 與其他 typed-port adapters
shared_kernel/       共用 command、typed error、receipt 與 durable-job primitives
ui_react/            React 管理端、ViewModel adapters 與 typed API clients
line/                 LINE webhook 與 runtime adapter
db/                   schema parts、migration releases 與模板
scripts/              匯入、migration、維運與 worker entry points
tests/                Python Module／Subsystem／Domain／Global 驗證
validation/           版本化 scenario、manifest 與 readback artifacts
.arch-map/            current architecture 與 focused-test 導航索引
document/架構重整/   正式規格、仍有效決策與必要證據
```

## Agent 與開發者閱讀順序

1. 先讀 `AGENTS.md`。
2. 已知精確 path／symbol 時直接開檔；只有功能描述時，先在 `.arch-map/` 做 filename-only bounded search，命中唯一 leaf 就直接讀取，候選不明時才讀 `.arch-map/index.md` 並沿單一最短路徑定位。
3. leaf 已指出 owner、source、adapter 與 focused test 後停止擴大搜尋。
4. 只有修改 owner、SSOT、public contract、Unit of Work、schema／migration 或跨 Domain invariant 時，才讀對應正式規格。
5. 正式規格索引為 `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`。

歷史計畫、封存 evidence、舊測試名稱與 Git 歷史不是 current implementation authority。

## 核心執行規則

- Query 唯讀；Preview 零正式寫入；Apply 以 fresh read 與明確 outer Unit of Work 提交。
- 一個業務命令只有一個 transaction owner；repository 與 adapter 不自行 commit。
- UI、route、webhook 與外部來源不得直接決定 Domain 根事實。
- 外部副作用由已提交的 outbox、inbox 或 durable job 執行。
- production、資料庫 migration、credential 與 provider 操作都需要各自的明確授權。

## 驗證

先執行直接相關的 focused tests：

```powershell
.\.venv\Scripts\python.exe -m pytest <直接相關測試>
cd ui_react
npm test -- <直接相關測試>
```

只有 failure signal 或 release acceptance 明確要求時才擴大到完整測試：

```powershell
.\.venv\Scripts\python.exe -m pytest
cd ui_react
npm test
```
