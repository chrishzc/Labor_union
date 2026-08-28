# LINE-001／LINE-005 canonical binding predicate guard Work Package

- Package ID：`PROV-20260827-line-binding-anomaly-predicate-guard`
- Status：`completed`
- Specification：`PROV-20260827-line-binding-anomaly-predicate-guard-spec.md` (`SPEC_READY`)
- Requirements：`LINE-BIND-GUARD-A1`～`A6`
- Effect ceiling：本機 source/tests/docs；零 schema、零 DB mutation、零外部 provider effect。

## Required now

1. 擴充 Client／Staff reminder Query，一次讀出 projection identity、subject technical id 與匹配的 canonical
   binding status/type/reference/version。
2. 將兩個 request builder 的 inactive 判定改為 spec 的五項 conjunction；未知／缺失 evidence 固定 active。
3. 更新 focused source與 adapter contract tests，覆蓋 missing binding、wrong status/type/reference、projection
   mismatch、valid bound 與 unassigned Staff。
4. 執行 focused tests、相關 anomaly regression、`git diff --check` 與 strict UTF-8。

## Exclusions／safe stop

- 不修改 `LINE-004/002/006`、registry action、UI、identity mutation、schema 或 provider。
- 若現有 canonical schema無法以 bounded join提供所需 facts，停止並回 `SPEC_GAP`，不得 fallback 到 legacy
  column。
- 若與既有 dirty source修改重疊，先保留雙方意圖；無法安全整合則停止。

## Coverage

| Acceptance | Package step | Verification oracle |
|---|---|---|
| A1/A2 | 1–3 | empty projection與 missing binding request皆 `active=True` |
| A3 | 1–3 | pending/revocation/revoked、wrong type/reference皆 `active=True` |
| A4 | 1–3 | exact bound root與 projection一致才 `active=False` |
| A5 | 2–3 | `staff_id is None` 時 `active=False` |
| A6 | 3–4 | adapter SQL包含 canonical binding join；focused regression、diff、UTF-8皆 passed |

結果：`PACKAGE_READY`。

## Completion

2026-08-27 source implementation完成；focused＋相關 anomaly regression `51 passed`，compile、
`git diff --check`、strict UTF-8 passed。第一輪 Luna High／high E3 verifier 發現 Client relation drift 與
whitespace 兩項 P1；序列修正並補 regression 後，第二輪 verifier `PASS`，P0/P1=0。詳見
`03_追蹤清單與證據/evidence/2026-08-27_line_binding_anomaly_predicate_guard_receipt.md`。
