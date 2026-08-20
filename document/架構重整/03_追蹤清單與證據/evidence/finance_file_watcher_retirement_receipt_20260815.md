---
doc_type: receipt
declared_status: completed
date: 2026-08-15
owner: Finance Import / Global Entry Governance
scope: Finance File Watcher retirement
---

# Finance File Watcher 退役驗收收據

## 結果

`scripts/file_watcher.py` 與所有 local launcher、smoke、candidate rehearsal runtime caller 已移除。
銀行日常入口維持 authenticated Finance Web ingestion；受控 Finance CLI 的 dry-run／explicit apply
邊界未改動。

| 驗收項目 | 結果 |
|---|---|
| Runtime source scan | PASS：沒有 `scripts/file_watcher.py`、`watchdog` import 或 watcher launcher target。 |
| Dependency lock | PASS：`watchdog` 已從 direct dependency 移除；`uv lock --check` 成功。 |
| Entry governance | PASS：current queue 不再列不存在的 File Watcher CLI。 |
| Focused regression | PASS：49 passed（entrypoint queue、import isolation、Finance CLI、local launcher／smoke、preserve-data plan）。 |
| DB / external effects | NOT_APPLICABLE：未寫入 DB、未啟動服務、未呼叫外部 provider。 |

Restore trigger：若 Finance Web ingestion 無法服務日常銀行匯入，先修復其 typed API／runtime；不得復活
watched-folder import。任何新的維運入口都須另立 Work Package 與 entrypoint review。
