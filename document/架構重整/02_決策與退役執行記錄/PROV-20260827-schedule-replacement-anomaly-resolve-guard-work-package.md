# SCHEDULE-002 generic resolve suppression guard Work Package

- Package ID：`PROV-20260827-schedule-replacement-anomaly-resolve-guard`
- Status：`completed`
- Specification：同名 spec (`SPEC_READY`)
- Effect ceiling：source/tests/docs；零 schema、零 DB mutation、零排班／帳務 mutation。

## Steps

1. 移除 builder 的 `already_resolved_assignment_ids` 與 workflow-based inactive 分支。
2. 移除 adapter 對 resolved current alerts 的 Query／composition。
3. 新增 focused regression，證明 replaced row固定 active且 source scan不依賴 workflow status。
4. 執行 focused/related tests、compile、diff、UTF-8與獨立 verifier。

## Exclusions／safe stop

不建立 replacement completion command、不更動 assignment/finance root、不宣稱人工 remediation完成。若發現
current owner rule已提供更精確 completion predicate，停止並回 spec-workshop，不以本 guard覆蓋。

| Acceptance | Step | Oracle |
|---|---|---|
| A1/A2 | 1,3 | replaced rows一律 active，舊 suppression parameter不存在 |
| A3 | 2,3 | adapter不再讀 resolved alerts |
| A4 | 1–2 | 不製造 synthetic inactive desired state |
| A5 | 3–4 | tests/checks/verifier passed |

結果：`PACKAGE_READY`。

## Completion

Source implementation與 focused regression完成；獨立 `gpt-5.6-luna`／`high` E3 verifier `PASS`，P0/P1=0。
另依 verifier建議補上 legacy resolved → fresh replaced root rescan → workflow reopened的直接 reducer回歸。
詳見 `03_追蹤清單與證據/evidence/2026-08-27_schedule_replacement_anomaly_resolve_guard_receipt.md`。
