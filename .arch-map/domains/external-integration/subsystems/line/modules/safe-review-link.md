# Module: safe-review-link

## Parent

- domain: `external-integration`
- subsystem: `line`

## Responsibility

2026-10-22 人工裁決取消群組告警及其專用一次性審核連結。Issue／Redeem 僅回 retired error，零 UoW／token／outbox；保留歷史 masked Query、Revoke、receipt 與 audit，不恢復群組通知。

## Implementation

- `subsystems/line/safe_review_link_contracts.py`
- `subsystems/line/safe_review_link_application.py`
- `db/schema_parts/1023_task96_line_safe_review_link_matching_outbox_v1.sql`
- `infrastructure/mysql/line_safe_review_link_repository.py`
- `subsystems/line/runtime_alert_target_application.py::_target_view` — existing runtime owner version interpretation.
- `api/routes/runtime_health.py`
- `api/schemas/runtime_health.py`
- `ui_react/src/api/line_safe_review_link/`
- `ui_react/src/components/SafeReviewLinkWorkbench.tsx`

## Persistence

- `db/schema_parts/1023_task96_line_safe_review_link_matching_outbox_v1.sql`
- additive release manifest and descriptor under `db/migration_releases/`
- The PR #299 correction uses the existing immutable `issued` event payload:
  `runtime_alert_target.target_id` and `runtime_alert_target.current_version`.
  It adds no table or public request field. `get_issued_runtime_target()` reads
  that evidence back from `line_safe_review_link_events`.

## Safety boundary

群組連結不得重新簽發、兌換或因 replay 回復功能；API 對退役操作回 HTTP 410。歷史 Query／撤銷沿原 root version 與 receipt。既有 schema 與 immutable issued events 保留，不回填或刪除。

普通 `/line-mobile-admin?target=customer_service` 為仍有效的身分驗證導航，不是群組一次性審核連結。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/external-integration/subsystems/line/modules/safe-review-link/`
- test_root: `ui_react/src/tests/safe_review_link_workbench.test.tsx`
- evidence: PR #299 code baseline `4eb58e07e94660308ba8afd05d39931f0301fdf1`; shared regression run `34733277249` / job `103659935152`. The 29 M4 regressions are part of the recorded 53-test run, not 53 tests of this module. Owner/UoW substitutes and SQLite adapter checks do not establish MySQL locking, mobile, provider, or full one-time-link flow acceptance; those remain `NOT_RUN` for this correction.
