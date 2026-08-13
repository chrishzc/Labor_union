# 2026-08-13 啟動腳本收斂 focused receipt

- Work Package：`75_Startup_Launcher_Convergence_and_Retirement_Work_Package.md`
- 變更環境：Windows 專案工作區；未啟動服務、未連線或修改 MySQL、未安裝或移除排程任務。
- 靜態契約：本專案應用程式的 operator-facing launcher 已集中至 `scripts/launchers/`；worker、
  monitor、migration 等 process module 仍位於 `scripts/`。個人工具及其 wrapper 明確不在本案範圍。
- 退役裁決：`start.bat` 為重複 alias；`dev_API.bat` 名稱誤導；Durable Job Worker installer 因主機
  supervision 已暫緩而退役。舊入口 replacement 已列於 launcher README。
- DB 契約：`update_local_database.bat` 保留資料；`reset_DB.bat` 捨棄資料並載入版本化模板，預檢失敗
  不進入 destructive apply。
- focused command：`.venv\Scripts\python.exe -m pytest tests/test_online_script.py tests/test_development_launcher_commands.py tests/test_durable_worker_task_scheduler_scripts.py tests/test_reset_fake_database_entrypoint.py tests/test_update_local_database_entrypoint.py tests/test_launcher_inventory.py tests/line/infrastructure/test_line_schema_stage6.py tests/test_local_database_maintenance.py -q -W error --basetemp .pytest_tmp/launcher-convergence-final`。
- 結果：`27 passed in 1.01s`；`git diff --check` 無 whitespace error。
- read-only reset preview 因目前 `.env` 未指向 `union_db` 而 fail closed，沒有修改 DB。HEAD 未追蹤
  `fixtures/db_snapshot_v2/v3`，且人工裁決 fixture 重建不屬本次任務，因此 reset 入口目前只保留
  canonical path 與安全門禁，真實模板 reset／服務 smoke 未執行。

## Launcher dry run

- 每支 active／recovery launcher 已加入唯讀 dry run；共用 preflight 為
  `scripts/launcher_preflight.py`。
- ready（exit `0`）：Admin no-auth BAT／PowerShell、Windows local startup、Windows no-auth startup、
  preserve-data DB update、排程狀態查詢及排程解除安裝，共 7 個入口。
- blocked（exit `1`）：模板 reset 缺 `fixtures/db_snapshot_v2/v3/manifest.json`；ngrok supervisor 缺
  `ngrok`；Unix launcher 在本 Windows 驗證環境缺 `lsof`。三者均成功進入 preflight 並準確回報
  dependency，不代表腳本解析或 wiring failure。
- `.env` dry run 前後 SHA-256 相同；沒有啟動 Docker／API／UI／worker／ngrok，沒有連線 DB，沒有
  查詢或修改 Windows 排程任務。
- dry-run contract focused regression：`22 passed in 0.90s`；另針對 batch blocked exit propagation
  驗證 `reset_DB.bat --dry-run` 回傳 `1`、Windows local startup 回傳 `0`。
- launcher、DB maintenance 與 LINE supervisor 合併 regression：`33 passed in 1.07s`；strict UTF-8 與
  `git diff --check` 通過。
