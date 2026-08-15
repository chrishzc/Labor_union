---
doc_type: receipt
declared_status: completed
date: 2026-08-15
owner: Case Import / Global Entry Governance
scope: HCM legacy CLI apply retirement
---

# HCM Legacy CLI Apply 退役驗收收據

## 結果

`scripts/imports/import_client_hcm.py` 不再有 `__main__` CLI entrypoint，也不再列入 current entrypoint
queue。它只保留供 authenticated HCM Web Preview／Apply 使用的 shared normalization／row-intake adapter；
historical whole-row overwrite HTTP routes 維持 `410`。

| 驗收項目 | 結果 |
|---|---|
| CLI entrypoint | PASS：module 無 `__main__` guard，不能再直接執行匯入。 |
| Entry governance | PASS：current queue 不再列出 retired CLI。 |
| Replacement | PASS：HCM typed Web Preview／Apply adapter import 與 route regression 通過。 |
| Focused regression | PASS：37 passed（queue、entry split、HCM safety、router、API client、workbook）。 |
| DB／external effect | NOT_APPLICABLE：本工作包未連線、未寫入 DB、未變更 schema。 |

Restore trigger：HCM Web intake 事故或 legacy entrypoint audit；不得恢復 CLI writer，應完成 shared adapter
extraction 後再移除殘留 legacy direct SQL helper。
