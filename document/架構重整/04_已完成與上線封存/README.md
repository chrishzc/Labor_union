# 已完成與上線封存

## 目的

本目錄保存已完成、已驗收、已上線或已被取代，且不再參與日常實作決策的文件。用途是歷史
追溯、incident／rollback、migration lineage 與稽核，不是日常開工必讀、現行 SSOT、代辦清單
或新實作授權。

Agent 平常不得遞迴讀取本目錄，也不得把本目錄加入一般任務的預設上下文。只有任務明確涉及
歷史追溯、事故調查、rollback、migration/cutover、舊 release 重現、法律／稽核查證，或現行
文件明確引用特定 archive identity 時，才可用 `rg` 精準搜尋 `archive_manifest.json`，再只讀取
命中的個別文件。

## 什麼可以封存

只有符合下列其中一類，且通過封存 gate 的文件可以移入：

1. `completed` Work Package／gap package，已連結完整驗收 evidence，沒有 active blocker、待辦、
   recovery action 或未執行 release gate。
2. 已由新正式規格完整取代並標記 `superseded` 的舊規格／提案，且 successor 已進入現行索引。
3. 已完成 release/cutover 的 execution record、receipt 與只供歷史追溯的 supporting evidence。
4. 已退役 entry point／migration／writer 的結案記錄，且 caller inventory、replacement 與 regression
   receipt 已完成。

## 什麼不能封存

- 仍約束目前 production 行為的 `approved` Global／Domain／Subsystem 正式規格；即使已上線，
  仍留在 `01_規格基線/`。只有被新的 current SSOT 取代後，舊版本才可封存。
- `draft`、`proposed`、`approved`、`in-progress`、`blocked` 的功能計畫或 Work Package。
- awaiting execution／release／migration／rollback 的 readiness 文件。
- 尚未建立 receipt、仍含未結 blocker、仍是人工操作入口或 current runbook 的文件。
- `validation/scenarios`、canonical fixtures、目前 release manifest、正式 schema 或 production code。

## 封存 gate

封存是一次可追溯的文件 relocation，不是刪除。每次執行前必須：

1. 確認 final status、owner、完成日期、上線日期（如適用）、release identity 與 evidence。
2. 確認仍有效的業務不變量已存在於精簡的 current SSOT，不依賴即將封存的文件才能理解。
3. 搜尋全部 inbound links，更新為 current successor 或 archive path；不得留下 broken link。
4. 在 `archive_manifest.json` 登記 source／archive path、digest、successor、evidence 與 restore triggers。
5. 從 active `02`／`03`／功能計畫索引移除長篇項目，只保留一行 archive pointer 或分類摘要。
6. 驗證 strict UTF-8、連結、manifest schema 與 `git diff --check`。
7. 不得在同一動作刪除原始 Git history、validation asset、production data 或 release artifact。

## 目錄分類

實際有文件時才建立子目錄，避免空資料夾與無效索引：

- `work_packages/`：已完成且不再 active 的執行包。
- `superseded_specs/`：已有 current successor 的舊版規格／提案。
- `release_records/`：已執行的 release／cutover／rollback 記錄。
- `receipts/`：已結案且不再被 active gate 直接讀取的收據與 evidence 摘要。

大型 binary、raw log、完整 DB dump、secret 與個資不得因「封存」而加入 Git；仍依 archive／backup
retention 與敏感資料規則保存。

## Manifest 使用方式

`archive_manifest.json` 是低頻 routing index，不是權威內容。日常任務不全文讀取；需要追溯時以
source path、archive id、release identity 或 Domain 精準搜尋。每筆 entry 至少包含：

- `archive_id`
- `source_path`、`archive_path`
- `doc_type`、`final_status`
- `completed_at`、`deployed_at`（不適用時為 `null`）
- `release_identity`（不適用時為 `null`）
- `successor_path`（不適用時為 `null`）
- `evidence_paths`
- `content_sha256`
- `archived_at`、`archived_by`、`reason`
- `restore_triggers`

2026-08-11 已完成兩輪保守封存：共 29 份 completed／proven／superseded／retired 文件通過
逐份 inventory、successor、evidence 與 inbound-link gate 後移入本目錄。完整清單與 digest 只查
`archive_manifest.json`；本 README 不重複列出每份歷史文件，避免再次形成高頻長索引。
