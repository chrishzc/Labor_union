# Writer Inventory v2 Candidate

## 狀態

- `artifact_status = blocked_candidate`
- `architecture_status = approved-architecture-baseline`
- `active_work_authorization = writer-inventory-v2-only`
- `execution_authority = none`
- `approved_to_remove_count = 0`

本 artifact 只做歷史 201-row snapshot 與目前 source identity 的部分 reconciliation。
它不是完整 fresh inventory，不授權 caller 改接、`410`、刪除、production code、
pytest、schema、資料或外部副作用。

## 結果

- historical snapshot rows：201
- exact identity matches：199
- verified stale identity：1
- parse-blocked probable stale identity：1
- source paths：43
- fresh root scan：未完成

`services/anomaly_alert_detection.py` 的共享 dirty source 目前不能通過 AST parse，
所以 scanner 無法驗證完整 root、count 或 fingerprint。修復該 source、重新執行完整
fresh scan、完成逐 finding semantic disposition／caller manifest／replacement receipt
以前，每一列的 `effective_disposition` 固定為 `blocked`。

## Artifacts

- `inventory_v2_candidate.manifest.json`：範圍、授權、repository identity、counts 與 blockers。
- `inventory_v2_candidate.rows.jsonl`：201 筆 exact snapshot identity 與逐列 reconciliation。
- `inventory_v2_candidate.sources.json`：43 個 live source digest 與 parse status。
- `inventory_v2_candidate.reconciliation_receipt.json`：input／output digest 與 partial receipt。

所有 JSON 使用 canonical compact form、strict UTF-8、LF、無 BOM。Digest 以各 manifest
或 receipt 內記錄為準，不以本 README 作 evidence SSOT。

## 可重現識別與 digest

- 每筆 identity 除 path、symbol、method、operation、table、call fingerprint 外，
  還包含 AST source span 與同 identity 的一基底 duplicate ordinal。
- parse-blocked 或已 stale finding 若可由目前 `HEAD` 還原，provenance 明列為
  `historical_head_ast`，不得誤稱為 live AST 證據。
- canonical JSON 使用 UTF-8 無 BOM、key 排序、compact separators、
  `ensure_ascii=false`，並保留單一結尾 LF。
- identity 集合 digest 以排序後的 digest 陣列計算，重複值不去重，因此是 multiset。
- 完整算法版本與各 digest 輸入定義記錄在 reconciliation receipt 的
  `digest_specification`。

## 未解除 Blockers

- `source_parse_error`
- `fresh_root_scan_incomplete`
- `new_findings_outside_snapshot_paths_not_scanned_as_complete`
- `semantic_disposition_incomplete`
- `caller_manifest_missing`
- `replacement_receipt_missing`
- `removal_approval_missing`

架構基線雖已核准，任何 production mutation 仍須另立 Work Package 並取得人工明確核准。

## Blocker Repair 與完整 Fresh Scan

2026-08-03 核准的 `Inventory v2 blocker repair` 只允許修復
`services/anomaly_alert_detection.py` 的既有 SyntaxError、執行語法檢查與 read-only
writer inventory scan。核准原文保存在
`blocker_repair_approval_2026-08-03.json`。

完整五個 roots 的 fresh scan artifacts：

- `inventory_v2_final.manifest.json`
- `inventory_v2_final.findings.jsonl`
- `inventory_v2_final.sources.jsonl`
- `inventory_v2_final.delta.jsonl`
- `inventory_v2_final.schema.json`
- `inventory_v2_final.scan_receipt.json`
- `inventory_v2_candidate_to_final_diff.md`

`final` 表示 full-root scan artifact；目前狀態仍是
`scan_complete_disposition_pending`。所有 finding 繼續 fail closed，不構成移除授權。
