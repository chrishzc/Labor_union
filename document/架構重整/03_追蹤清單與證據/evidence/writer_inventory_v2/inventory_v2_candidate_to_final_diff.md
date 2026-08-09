# Inventory v2 Candidate → Full Scan 差異報告

## 結論

- Candidate scope：historical 201-row reconciliation／43 source paths。
- Full scan scope：`api, infrastructure, services, line, scripts` 下全部 Python sources。
- Full scan finding：670。
- Candidate exact carried forward：199。
- Candidate stale／已不在 live finding set：2。
- Candidate scope 外新增 live finding：471。
- 所有 live finding 均為 `effective_disposition=blocked`；
  `approved_to_remove=false`。

## v1 Baseline Drift

- finding count：666 → 670
- baseline fingerprint：`d7ab5eb7f257037fd26407a78e4c82347b01c945120bd33df77a6c942e50f3d5`
- current fingerprint：`2fb57b10fbfba9ab35299aaafff4c55750467f346e1ff8349c1f073e3abe2069`
- 結果：finding count 與 identity multiset 均已漂移。

## Blocker Repair

- `services/anomaly_alert_detection.py` 已能由 strict UTF-8 AST 完整解析。
- Candidate 時的 source SHA-256：
  `0af1763573115663fb0c06ac41c2d16e72f1a7a96968b827a8f922324960268c`
- Full scan 時的 source SHA-256：
  `76f7cf0d33f88f3fae9f765623e131d3f16e3ae6bd64124056a9f17b1b11b52c`
- `source_parse_error`、`fresh_root_scan_incomplete`、
  `new_findings_outside_snapshot_paths_not_scanned_as_complete` 已解除。

## 尚未完成

- semantic disposition
- unique owner coverage for every live finding
- caller manifest
- replacement receipt
- removal approval

因此本 artifact 狀態為 `scan_complete_disposition_pending`。它是完整 fresh
Inventory v2 scan，但不是移除授權，也不是 semantic disposition 已完成的 inventory。
