# 2026-08-27 HCM Multi-occurrence Umbrella Resolution Receipt

- `status`: `source_pass_runtime_not_run`
- `source_work_package_status`: `removed_after_source_completion`
- `authority`: 同一匯入三個問題逐筆解除；最後一個修正後整筆匯入警示消失。

## Final candidate

- `IMPORT-004` 新增唯一 exact owner auto-resolution contract：
  `hcm_review_all_occurrences_owner_terminal_after_locked_readback`。
- HCM field correction 仍先檢查 event、prior occurrence、case、client、review binding 與 fresh root
  fingerprint；只解除該 occurrence。
- 同 review sibling 以 `source_receipt_identity` 聚合。只有 `auto_resolved` 為 terminal；人工 `closed`、
  缺少 current-task row 或未知 issue 均保持 active／固定 fail closed。
- aggregate 為 0 時才重投影 umbrella inactive。current umbrella 缺失或 projector 回傳 `None` 會回滾
  occurrence transition，不會把 outbox 標記 published。
- 同 review 較早未 published outbox 會阻擋較晚 claim；不同 review 不受影響，因此 correction
  event source version 不倒退。

## Verification

| Gate | Status | Evidence |
|---|---|---|
| Focused Python | `passed` | 84 passed in 0.67s：Anomaly rulebook、HCM aggregate／resubmission／workbook／IMPORT-004／WP95 schema |
| Compile | `passed` | `python -m compileall` on final Python candidate |
| Diff hygiene | `passed` | `git diff --check` on owned paths |
| Independent E3 | `passed` | `gpt-5.6-luna` / `high`；final pass 無 P0／P1，前輸發現的四個 P1 均已關閉 |
| MySQL lock scheduling | `not_run` | Docker Compose／MySQL 未啟動，不以 fake 代替 |
| FastAPI／React active-list | `not_run` | API／React service 未啟動 |

## DDH dynamic adjustment record

1. E3 Luna High 唯讀定位原始 P1 與合法 write set。
2. 工作包 `PACKAGE_READY` 後，因 cohesive shared transaction 轉 E2 主代理單一 writer。
3. 每次 E3 發現 material P1，只重投影剩餘修復：owner contract／missing alert／left join／
   same-review claim ordering。
4. final E3 PASS 後停止 source 擴張；runtime 因服務未啟動保留 `not_run`。

本 receipt 不宣稱 Task96 全42碼完成，也不宣稱真 MySQL lock／Browser runtime 已驗收。
