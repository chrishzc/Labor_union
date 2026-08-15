---
doc_type: receipt
declared_status: completed
date: 2026-08-15
owner: Case Import / Global Entry Governance
scope: HCM historical whole-row direct-SQL writer retirement
---

# HCM Historical Whole-row Writer 退役驗收收據

Historical HCM HTTP routes 早已固定 `410`；本次移除其未使用 composition factory、row intake 與
`clients`／`orders` whole-row `UPDATE` helper。current typed HCM Web workflow 和 WP95 resubmission 保持。

| 驗收項目 | 結果 |
|---|---|
| retired composition／writer source | PASS：沒有 `HcmHistoricalRowIntake` 或 historical whole-row SQL。 |
| replacement | PASS：HCM Web current intake 和 resubmission shared adapter 保留。 |
| focused regression | PASS：36 passed、7 skipped。 |
| DB／external effect | NOT_APPLICABLE：未執行 DB 寫入、schema 變更或外部呼叫。 |

Restore trigger：HCM Web intake incident 或 legacy-entry audit；不得恢復 historical whole-row overwrite，應使用
HCM owner resubmission Preview／Apply。
