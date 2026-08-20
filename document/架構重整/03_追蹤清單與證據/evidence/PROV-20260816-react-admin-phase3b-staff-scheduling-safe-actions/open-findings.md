# Phase 3B Open Findings

## Blocking findings

1. `P3B-01 STAFF_SELECTOR_WRITE_SET_GAP`：四flow需要canonical staff ID，但React沒有Staff summaries client，
   核准write set也未包含該bounded client。不得沿用／改名`MOCK_STAFF`。
2. `P3B-02 PREFERENCES_TYPED_ERROR_GAP`：route errors仍是raw `HTTPException.detail`，且缺route-level契約tests。
3. `P3B-03 AVAILABILITY_G2_EVIDENCE_GAP`：成功契約可接，但occupancy mutex、overlap/waiting-lock/buffer、
   replay/stale/append-only cancel的route evidence未閉合。
4. `P3B-04 LIFECYCLE_PUBLIC_CONTRACT_GAP`：error raw、view未strict、fingerprint未限制64-hex、缺route tests。
5. `P3B-05 LEAVE_RAW_IMPACT_GAP`：三個cross-domain impact仍是`dict[str,Any]`。
6. `P3B-06 LEAVE_OUTER_UOW_GAP`：正式Apply提交後另開UoW處理leave request與LINE outbox，不符合核准的
   單一outer-UoW原子性要求。

## Status

Phase 3B remains `blocked-contract-amendment-required`. No production client/page writer may start under the current
exact write set. A revised backend-hardening plus Staff selector amendment requires new human approval.

