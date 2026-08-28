# Task 96 Windows runtime supervision source receipt

- 日期：2026-08-28
- Package：`LDU-WINDOWS-RUNTIME-SUPERVISION-SOURCE`
- 結果：`PASS`（source／focused）；另一台實體 Windows developer acceptance 為 `NOT_RUN`。
- DB 總結：`DB_CHANGE_NOT_READY`。

## 1. 已完成契約

- `start_local_development.bat` 在 current-schema gate 後委派正式 supervisor；API、React 與 required
  workers 必須存活並通過 readiness，optional worker 不會被誤列為 required success。
- supervisor 以同一份 `Win32_Process` snapshot 的 PID、ParentPid、CreationDate 建立 process lineage；
  traversal、存活判斷與 cleanup 都重新核對 immutable process identity，PID reuse 或 orphan 不會被誤殺。
- process state 明確區分 `alive`、`exited`、`unknown`；unknown 固定 non-zero 並輸出
  `cleanup_unknown`，不得冒充 `cleanup_complete`。
- `Stop-Process` 後以新的 process readback 驗證停止結果；React `/admin/` root marker、環境旗標、
  schema gate 與 worker survival 都有 machine-readable evidence。
- no-auth temporary environment 以 atomic `.NET UTF8Encoding(false)` 寫入，維持 UTF-8 無 BOM。

## 2. 驗證

- 主代理 launcher focused regression：`41 passed`。
- fresh Luna/high final2 verifier：P0=0、P1=0、P2=0，`changed_files=[]`。
- verifier focused：`29 passed`。
- tree-sitter PowerShell parser：`PASS`。
- Unix launcher `bash -n`、strict UTF-8／BOM、Windows CRLF、quoted path 與 `git diff --check`：`PASS`。
- 原生 PowerShell／Windows parser與實體 Windows runtime：`NOT_RUN`。

## 3. Remaining acceptance

另一台實體電腦仍須對自己的 allowlisted development exact-1003 DB，依正式 runbook 完成 backup、
read-only plan、explicit preserve-data Apply、`--require-current`、no-auth startup、required workers、
Browser 與 receipt readback。此 source receipt 不取代實體機 Developer acceptance，也不授權
`union_db`、reset、replacement、`--switch`、production 或全庫清理。

本輪未操作 DB／port／Browser，未使用 Graphify，也未 stage／commit。
