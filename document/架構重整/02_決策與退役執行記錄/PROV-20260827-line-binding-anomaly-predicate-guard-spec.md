# LINE-001／LINE-005 canonical binding predicate guard

- `doc_type`: `specification`
- `declared_status`: `SPEC_READY`
- Authority：使用者要求異常自動解除必須符合真實業務流程；`23_LINE身分管理與解除正式規格.md` §2–5；
  `06_Anomalies_Domain.md` 全異常 remediation 閉環。
- Scope：只修正 `LINE-001`／`LINE-005` current-state detector 的 inactive 判定；不建立 profile writer、
  binding mutation、人工修正 UI、schema 或 provider side effect。

## Root predicate

### `LINE-001`

每個具有 Client 的訂單案件均保留一筆 case-scoped desired state。只有同時符合下列全部條件才可
`predicate_active=false`：

1. Client projection 的 `line_user_id` 非空；
2. 同一 `line_user_id` 的 canonical `line_identity_bindings` root 存在；
3. `binding_status='bound'`；
4. `subject_type='customer'`；
5. `subject_reference` 精確等於 Client technical identity 的十進位字串。

任一條件不成立、binding 缺失、`pending_review`／`revocation_pending`／`revoked`、subject mismatch 或 projection
與 root 不一致時都保持 active。

### `LINE-005`

未指派 Staff 的案件不啟動此碼。已指派 Staff 時，只有同時符合下列全部條件才可
`predicate_active=false`：

1. Staff projection 的 `line_user_id` 非空；
2. 同一 `line_user_id` 的 canonical binding root 存在；
3. `binding_status='bound'`；
4. `subject_type='staff'`；
5. `subject_reference` 精確等於 Staff technical identity 的十進位字串。

其餘情況保持 active。Detector 必須由同一 bounded Query 同時讀 projection 與 canonical binding evidence，
不得在 Python 以姓名、電話或相似度猜 subject。

## Invariants 與 exclusions

- 這是 fail-closed safety guard，不宣稱完成兩碼的人工 remediation。
- 不改 Anomalies workflow status，不呼叫 generic resolve，不寫 Client／Staff／LINE Identity root。
- 不改 registry code、fingerprint identity、display allowlist 或 source identity。
- 不新增 schema／migration；若 live schema 缺 canonical binding table，scan 應整批失敗並 rollback，不得退回
  legacy projection-only 判定。
- `LINE-004`、`LINE-002`、`LINE-006` 不在此切片。

## Acceptance IDs

- `LINE-BIND-GUARD-A1`: projection 空值時 `LINE-001`／已指派 Staff 的 `LINE-005` 保持 active。
- `LINE-BIND-GUARD-A2`: projection 非空但 canonical binding 缺失時保持 active。
- `LINE-BIND-GUARD-A3`: status 非 `bound`、subject type 錯誤、subject reference 錯誤時保持 active。
- `LINE-BIND-GUARD-A4`: 只有 bound＋正確 subject/reference＋projection 一致時 inactive。
- `LINE-BIND-GUARD-A5`: 未指派 Staff 的案件不啟動 `LINE-005`。
- `LINE-BIND-GUARD-A6`: focused detector與 MySQL adapter tests 證明 Query 帶回 canonical binding evidence，
  `git diff --check` 與 strict UTF-8 通過。

## Source map

- Formal rule：`23_LINE身分管理與解除正式規格.md` §2–5。
- Anomaly invariant：`06_Anomalies_Domain.md` 全異常人工 remediation 閉環。
- Live drift：`subsystems/anomalies/process_reminder_anomaly_source.py` 的 projection-only predicate，
  `infrastructure/mysql/process_reminder_anomaly_source.py` 的 Client／Staff line queries。
- Coverage evidence：`2026-08-27_anomaly_rulebook_oracle_matrix.md`。

```yaml
convergence:
  status: READY
  blockers: []
```

結果：`SPEC_READY`。
