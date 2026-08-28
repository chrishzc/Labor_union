# SCHEDULE-002 generic resolve suppression guard

- `doc_type`: `specification`
- `declared_status`: `SPEC_READY`
- Authority：使用者要求根因消失後才解除異常；`06_Anomalies_Domain.md`；
  `02_Assignments_Scheduling_Domain.md` replacement lineage。
- Scope：移除 `workflow_status='resolved'` 對 `SCHEDULE-002` root predicate 的抑制。

## Contract

只要 detector 仍讀到 `case_staff_assignments.status='replaced'` 的來源 root，而 canonical replacement／service
outcome／finance split completion 尚未有 owner predicate 證明，`SCHEDULE-002` desired state 必須保持 active。
claim、tracking 或 generic resolve 不得改變 desired root predicate；rescan 必須重新開啟被 generic resolve 的
current alert。

本切片不定義真正 completion，也不改 assignment、schedule 或 finance root；在 owner contract 收斂前固定
fail closed。不得用移除 warning、略過 source row 或查 workflow status 冒充修復。

## Acceptance

- `SCHEDULE-RESOLVE-GUARD-A1`: 每個 replaced source row 都產生 `active=True` desired state。
- `SCHEDULE-RESOLVE-GUARD-A2`: builder 不接受 resolved-alert suppression input。
- `SCHEDULE-RESOLVE-GUARD-A3`: MySQL scan 不查 `workflow_status='resolved'` 來計算 root predicate。
- `SCHEDULE-RESOLVE-GUARD-A4`: source row 消失時由 canonical projector既有 bounded reconciliation處理；
  本切片不製造假的 inactive row。
- `SCHEDULE-RESOLVE-GUARD-A5`: focused regression、compile、diff與 strict UTF-8通過。

```yaml
convergence:
  status: READY
  blockers: []
```

結果：`SPEC_READY`。
