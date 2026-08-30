"""
File: generate_entrypoint_review_queue.py
Description: 產生 API、CLI、Streamlit 與 React entry review queue，不記錄 runtime 使用量。
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "document" / "架構重整" / "03_追蹤清單與證據" / "evidence" / "entrypoint_review_queue_v1.jsonl"
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
REACT_NAV_PATH = ROOT / "ui_react" / "src" / "components" / "MasterLayout.tsx"
REACT_APP_PATH = ROOT / "ui_react" / "src" / "App.tsx"
REACT_ROLLBACKS = {
    "order-tracker": ("ui:05_form_management.py", "/?entry=form-management&view=order-tracker", "order-workbench"),
    "orders": ("ui:02_orders.py", "/?entry=orders", "orders"),
    "scheduling": ("ui:03_calendar.py", "/?entry=scheduling&view=calendar", "staff-scheduling"),
    "staff": ("ui:03_calendar.py", "/?entry=scheduling&view=staff-directory", "staff-scheduling"),
    "data-import": ("ui:09_data_import.py", "/?entry=data-import", "data-import"),
    "line-management": ("ui:07_line_management.py", "/?entry=line-management", "line"),
    "reports": ("ui:08_system_status.py", "/?entry=system-status&view=reports", "reports-system"),
    "finance": ("ui:04_finance.py", "/?entry=finance", "finance"),
    "anomalies": ("ui:06_finance_alerts.py", "/?entry=anomalies", "anomalies"),
    "data-browser": ("ui:01_data_browser.py", "/?entry=data-browser", "data-browser"),
    "account-management": ("ui:09_access_management.py", "/?entry=access-management", "access"),
    "system-status": ("ui:08_system_status.py", "/?entry=system-status", "reports-system"),
}
TERMINAL_DISPOSITION_BY_STATUS = {
    "active": "active_canonical",
    "operator_only": "operator_only_guarded",
    "retired_410": "retired_410",
    "removed": "delete",
}
SOURCE_RETIRED_HTTP_ENTRIES = {
    "api:GET /api/v1/anomalies/{fingerprint}": "api:GET /api/v1/anomaly-recovery/{issue_key}",
    "api:POST /api/v1/anomalies/{fingerprint}/claim": "Owning Domain typed Query/Preview/Apply action",
    "api:POST /api/v1/anomalies/{fingerprint}/resolve": "Owning Domain typed Query/Preview/Apply action followed by bounded recheck",
    "api:POST /api/v1/anomaly-recovery/definitions/{definition_code}/scan": "Global durable anomaly.recheck job with an owner-composed bounded detector",
    "api:POST /api/v1/anomaly-recovery/projector/retry": "Global durable-job retry/supersede mechanism",
    "api:GET /api/v1/admin/anomaly-necessity-migration/alerts": "api:GET /api/v1/anomalies",
    "api:POST /api/v1/admin/anomaly-necessity-migration/alerts/{alert_fingerprint}/apply": "owner_action_from:GET /api/v1/anomalies/{issue_key}/actions/{action_key}",
    "api:POST /api/v1/admin/anomaly-necessity-migration/alerts/{alert_fingerprint}/preview": "owner_action_from:GET /api/v1/anomalies/{issue_key}/actions/{action_key}",
    "api:POST /api/v1/admin/data-browser/{table}/{row_id}/source-correction/apply": "Owning Domain typed Query/Preview/Apply command selected by exact source owner.",
    "api:POST /api/v1/admin/data-browser/{table}/{row_id}/source-correction/preview": "Owning Domain typed Query/Preview/Apply command selected by exact source owner.",
    "api:GET /api/v1/admin/capability-grants/{admin_user_id}": "Authenticated principal effective-capability projection; no per-user capability list.",
    "api:GET /api/v1/finance-reports/accounts-payable-summary": "api:GET /api/v1/finance-reports/accounts-payable",
    "api:GET /api/v1/finance-import/jobs/{job_id}": "api:GET /api/v1/jobs/{job_id}/observation",
    "api:GET /api/v1/storage/files": "subsystems.controlled_files.reference_finalize.ControlledFileReferenceService",
    "api:GET /api/v1/storage/files/{file_id}": "subsystems.controlled_files.reference_finalize.ControlledFileReferenceService",
    "api:GET /api/v1/storage/files/{file_id}/download": "subsystems.controlled_files.reference_finalize.ControlledFileReferenceService",
    "api:GET /api/v1/storage/receipts/{receipt_id}": "subsystems.controlled_files.reference_finalize.ControlledFileReferenceService",
    "api:POST /api/v1/storage/files/apply": "subsystems.controlled_files.reference_finalize.ControlledFileReferenceService",
    "api:POST /api/v1/storage/files/preview": "subsystems.controlled_files.reference_finalize.ControlledFileReferenceService",
    "api:POST /api/v1/storage/staging": "subsystems.controlled_files.reference_finalize.ControlledFileReferenceService",
    "api:GET /api/v1/anomaly-recovery/projector/dead-letters": "Global durable-job retry/supersede mechanism",
    "api:POST /api/v1/anomaly-recovery/projector/dead-letters/{projector_identity}/{event_id}/retry/apply": "Global durable-job retry/supersede mechanism",
    "api:POST /api/v1/anomaly-recovery/projector/dead-letters/{projector_identity}/{event_id}/retry/preview": "Global durable-job retry/supersede mechanism",
    "api:POST /api/v1/anomaly-recovery/projector/dead-letters/{projector_identity}/{event_id}/supersede/apply": "Global durable-job retry/supersede mechanism",
    "api:POST /api/v1/anomaly-recovery/projector/dead-letters/{projector_identity}/{event_id}/supersede/preview": "Global durable-job retry/supersede mechanism",
    "api:POST /api/v1/matches/{match_id}/send-info-1": "Matching Plan segment information endpoint",
    "api:POST /api/v1/matches/{match_id}/send-info-2": "Matching Plan segment information endpoint",
    "api:POST /api/v1/orders/{case_no}/actual-start/reconfirm": "api:POST /api/v1/orders/{case_no}/actual-start/preview and /apply",
    "api:POST /api/v1/orders/{case_no}/assignment-synchronization/apply": "api:POST /api/v1/orders/{case_no}/assignment-plan/apply",
    "api:POST /api/v1/orders/{case_no}/assignment-synchronization/preview": "api:POST /api/v1/orders/{case_no}/assignment-plan/preview",
    "api:POST /api/v1/orders/{case_no}/availability-locks/{lock_id}/convert": "api:POST /api/v1/orders/{case_no}/assignment-plan/preview and /apply",
    "api:POST /api/v1/orders/{case_no}/cancel": "api:POST /api/v1/orders/{case_no}/cancellation/preview and /apply",
    "api:POST /api/v1/orders/{case_no}/holds": "Anomalies typed root-fact recovery actions",
    "api:POST /api/v1/orders/{case_no}/holds/{hold_key}/release": "Anomalies typed root-fact recovery actions",
    "api:POST /api/v1/orders/{case_no}/lifecycle-corrections": "Owning Domain root-fact Preview/Apply",
    "api:POST /api/v1/orders/{case_no}/matches": "Matching Plan create/contact-state endpoints",
    "api:POST /api/v1/orders/{case_no}/matching-plans/{plan_id}/availability-lock/acquire": "waiting-deposit-lock acquisition Preview/Apply",
    "api:POST /api/v1/orders/{case_no}/matching-plans/{plan_id}/availability-locks/{lock_id}/release": "waiting-deposit-lock release Preview/Apply",
    "api:POST /api/v1/line/staff-self-service/service-day-logs": "api:POST /api/v1/line/staff-self-service/service-day-logs/preview and /apply",
    "api:POST /api/v1/orders/{case_no}/send-resume": "Matching Plan resumes endpoint",
    "api:GET /api/v1/orders": "api:GET /api/v1/orders/summaries",
    "api:GET /api/v1/orders/{case_no}/historical-baseline-projector": "api:GET /api/v1/orders/{case_no}/historical-operational-baseline",
    "api:GET /api/v1/staff": "api:GET /api/v1/staff/summaries",
    "api:PATCH /api/v1/admin/data-browser/{table}/{row_id_str}": "Owning Domain typed Preview/Apply command",
    "api:PATCH /api/v1/customer-service/tickets/{ticket_id}": "api:POST /api/v1/customer-service/tickets/{ticket_id}/update/preview and /apply",
    "api:POST /api/config/line-menus/{menu_id}/publish": "api:POST /api/v1/line/rich-menus/{menu_id}/publish-preview and /publish",
    "api:POST /api/v1/assignment-schedules/{assignment_id}/generate": "Assignment Plan Query/Preview/Apply",
    "api:POST /api/v1/assignment-schedules/{assignment_id}/rest-dates/leave-resolution/apply": "api:POST /api/v1/orders/{case_no}/leave-substitution/preview and /apply",
    "api:POST /api/v1/assignment-schedules/{assignment_id}/rest-dates/leave-resolution/batch-apply": "api:POST /api/v1/orders/{case_no}/leave-substitution/preview and /apply",
    "api:POST /api/v1/assignment-schedules/{assignment_id}/rest-dates/leave-resolution/batch-preview": "api:POST /api/v1/orders/{case_no}/leave-substitution/preview and /apply",
    "api:POST /api/v1/assignment-schedules/{assignment_id}/rest-dates/leave-resolution/preview": "api:POST /api/v1/orders/{case_no}/leave-substitution/preview and /apply",
    "api:POST /api/v1/client-payments/due-dates/backfill": "Client Finance typed Query/Preview/Apply",
    "api:POST /api/v1/client-payments/transaction": "Client Finance typed Query/Preview/Apply",
    "api:POST /api/v1/customer-service/tickets/{ticket_id}/reply": "api:POST /api/v1/customer-service/tickets/{ticket_id}/reply/preview and /apply",
    "api:POST /api/v1/line/identity/reviews/{request_id}/{decision}": "api:POST /api/v1/line/identity/reviews/{request_id}/{decision}/preview and /apply",
    "api:POST /api/v1/line/mobile-admin/customer-service/tickets/{ticket_id}/reply": "api:POST /api/v1/line/mobile-admin/customer-service/tickets/{ticket_id}/reply/preview and /apply",
    "api:POST /api/v1/line/mobile-admin/identity-reviews/{request_id}/decision": "api:POST /api/v1/line/mobile-admin/identity-reviews/{request_id}/decision/preview and /apply",
    "api:POST /api/v1/matches/{match_id}/send-resume": "Matching Plan communication endpoints",
    "api:POST /api/v1/orders/{case_no}/assign-staff": "Assignment Plan Query/Preview/Apply",
    "api:POST /api/v1/schedule/save": "Assignment Plan or Leave/Substitution Preview/Apply",
    "api:POST /api/v1/staff-payments/transaction": "Staff Payables typed Query/Preview/Apply",
    "api:PUT /api/line/users/{user_id}/role/{role}": "api:POST /api/v1/line/identity",
    "api:PUT /api/v1/assignment-schedules/{assignment_id}/days/{work_date}": "Assignment Plan Query/Preview/Apply",
    "api:PUT /api/v1/assignment-schedules/{assignment_id}/rest-dates": "api:POST /api/v1/orders/{case_no}/leave-substitution/preview and /apply",
    "api:PUT /api/v1/matches/{match_id}/reply": "Matching Plan communication endpoints",
    "api:PUT /api/v1/orders/{case_no}/status": "Orders typed lifecycle Preview/Apply commands",
}
SOURCE_REPOSITORY_LOCAL_TYPED_410_ENTRIES = frozenset(
    {
        "api:GET /api/v1/orders",
        "api:GET /api/v1/orders/{case_no}/historical-baseline-projector",
        "api:GET /api/v1/staff",
        "api:PATCH /api/v1/admin/data-browser/{table}/{row_id_str}",
        "api:PATCH /api/v1/customer-service/tickets/{ticket_id}",
        "api:POST /api/config/line-menus/{menu_id}/publish",
        "api:POST /api/v1/assignment-schedules/{assignment_id}/generate",
        "api:POST /api/v1/assignment-schedules/{assignment_id}/rest-dates/leave-resolution/apply",
        "api:POST /api/v1/assignment-schedules/{assignment_id}/rest-dates/leave-resolution/batch-apply",
        "api:POST /api/v1/assignment-schedules/{assignment_id}/rest-dates/leave-resolution/batch-preview",
        "api:POST /api/v1/assignment-schedules/{assignment_id}/rest-dates/leave-resolution/preview",
        "api:POST /api/v1/client-payments/due-dates/backfill",
        "api:POST /api/v1/client-payments/transaction",
        "api:POST /api/v1/customer-service/tickets/{ticket_id}/reply",
        "api:POST /api/v1/line/identity/reviews/{request_id}/{decision}",
        "api:POST /api/v1/line/mobile-admin/customer-service/tickets/{ticket_id}/reply",
        "api:POST /api/v1/line/mobile-admin/identity-reviews/{request_id}/decision",
        "api:POST /api/v1/matches/{match_id}/send-resume",
        "api:POST /api/v1/orders/{case_no}/assign-staff",
        "api:POST /api/v1/schedule/save",
        "api:POST /api/v1/staff-payments/transaction",
        "api:PUT /api/line/users/{user_id}/role/{role}",
        "api:PUT /api/v1/assignment-schedules/{assignment_id}/days/{work_date}",
        "api:PUT /api/v1/assignment-schedules/{assignment_id}/rest-dates",
        "api:PUT /api/v1/matches/{match_id}/reply",
        "api:PUT /api/v1/orders/{case_no}/status",
    }
)
SOURCE_MEDIA_RETIRED_HTTP_ENTRIES = frozenset(
    {
        "api:GET /api/v1/storage/files",
        "api:GET /api/v1/storage/files/{file_id}",
        "api:GET /api/v1/storage/files/{file_id}/download",
        "api:GET /api/v1/storage/receipts/{receipt_id}",
        "api:POST /api/v1/storage/files/apply",
        "api:POST /api/v1/storage/files/preview",
        "api:POST /api/v1/storage/staging",
    }
)
SOURCE_LOCAL_CANONICAL_HTTP_ENTRIES = frozenset(
    {
        "api:GET /api/v1/anomaly-recovery/{issue_key}",
        "api:GET /api/v1/anomaly-recovery/{issue_key}/actions/{action_key}",
        "api:GET /api/v1/admin/data-browser/sources/{source_id}",
        "api:GET /api/v1/case-import/hcm/workbooks/results",
        "api:GET /api/v1/customer-service/escalations/{escalation_id}",
        "api:GET /api/v1/finance-import/jobs/{job_id}/batch-outcome",
        "api:GET /api/v1/finance-import/jobs/{job_id}/correction-outcome",
        "api:GET /api/v1/government-subsidy/overpayments/{overpayment_identity}",
        "api:GET /api/v1/import-warning-tracking/receipts/{receipt_identity}",
        "api:GET /api/v1/jobs/{job_id}/observation",
        "api:GET /api/v1/line/configurations/{kind}/safe",
        "api:GET /api/v1/line/identity/reviews/numbered",
        "api:GET /api/v1/line/media-assets/rich-menu",
        "api:GET /api/v1/line/order-groups/numbered",
        "api:GET /api/v1/line/order-groups/{case_no}/events/numbered",
        "api:GET /api/v1/line/rich-menus/draft",
        "api:GET /api/v1/operations-reports/weekly",
        "api:GET /api/v1/operations-reports/weekly/export",
        "api:GET /api/v1/orders/historical-review-remediations/{review_identity}",
        "api:GET /api/v1/orders/{case_no}/cancellation/receipt",
        "api:GET /api/v1/orders/{case_no}/client-finance/refund-overage-recovery/{recovery_identity}",
        "api:GET /api/v1/orders/{case_no}/client-finance/settlement-remediation",
        "api:GET /api/v1/orders/{case_no}/contract-external-signing",
        "api:GET /api/v1/orders/{case_no}/contract-external-signing/final-document/readback",
        "api:GET /api/v1/orders/{case_no}/contract-external-signing/legacy-recovery",
        "api:GET /api/v1/orders/{case_no}/contract-external-signing/receipts/{receipt_id}",
        "api:GET /api/v1/orders/{case_no}/contract-external-signing/unsigned-pdf",
        "api:GET /api/v1/orders/{case_no}/historical-baseline-projector",
        "api:GET /api/v1/orders/{case_no}/historical-completion",
        "api:GET /api/v1/orders/{case_no}/service-before-replacement",
        "api:GET /api/v1/staff-payables/overpayment-recoveries/{staff_id}/{recovery_identity}",
        "api:GET /internal/v1/runtime/react-admin/artifact-health",
        "api:POST /api/v1/admin/auth/login/challenges",
        "api:POST /api/v1/admin/auth/login/challenges/{challenge_id}/verify",
        "api:POST /api/v1/customer-service/escalations",
        "api:POST /api/v1/customer-service/escalations/preview",
        "api:POST /api/v1/customer-service/escalations/{escalation_id}/claim",
        "api:POST /api/v1/customer-service/escalations/{escalation_id}/claim/preview",
        "api:POST /api/v1/customer-service/escalations/{escalation_id}/handling",
        "api:POST /api/v1/customer-service/escalations/{escalation_id}/handling/preview",
        "api:POST /api/v1/customer-service/escalations/{escalation_id}/resolve",
        "api:POST /api/v1/customer-service/escalations/{escalation_id}/resolve/preview",
        "api:POST /api/v1/customer-service/tickets/{ticket_id}/reply/apply",
        "api:POST /api/v1/customer-service/tickets/{ticket_id}/reply/preview",
        "api:POST /api/v1/customer-service/tickets/{ticket_id}/update/apply",
        "api:POST /api/v1/customer-service/tickets/{ticket_id}/update/preview",
        "api:POST /api/v1/line/identity/reviews/{request_id}/{decision}/apply",
        "api:POST /api/v1/line/identity/reviews/{request_id}/{decision}/preview",
        "api:POST /api/v1/line/rich-menus/draft/preview",
        "api:POST /api/v1/matching-coordination/{case_no}/apply/caregiver-selection",
        "api:POST /api/v1/matching-coordination/{case_no}/apply/confirm-zero-candidate",
        "api:POST /api/v1/matching-coordination/{case_no}/apply/criteria-diff",
        "api:POST /api/v1/matching-coordination/{case_no}/apply/customer-decision",
        "api:POST /api/v1/matching-coordination/{case_no}/apply/initial-criteria",
        "api:POST /api/v1/matching-coordination/{case_no}/apply/leave-impact",
        "api:POST /api/v1/matching-coordination/{case_no}/apply/rematch",
        "api:POST /api/v1/matching-coordination/{case_no}/apply/service-date-rematch",
        "api:POST /api/v1/matching-coordination/{case_no}/apply/zero-candidate",
        "api:POST /api/v1/matching-coordination/{case_no}/preview/confirm-zero-candidate",
        "api:POST /api/v1/matching-coordination/{case_no}/preview/criteria-diff",
        "api:POST /api/v1/matching-coordination/{case_no}/preview/initial-criteria",
        "api:POST /api/v1/matching-coordination/{case_no}/preview/leave-impact",
        "api:POST /api/v1/matching-coordination/{case_no}/preview/package",
        "api:POST /api/v1/matching-coordination/{case_no}/preview/rematch",
        "api:POST /api/v1/matching-coordination/{case_no}/preview/service-date-rematch",
        "api:POST /api/v1/matching-coordination/{case_no}/preview/zero-candidate",
        "api:POST /api/v1/matching-coordination/{case_no}/query",
        "api:POST /api/v1/orders/historical-review-remediations/apply",
        "api:POST /api/v1/orders/historical-review-remediations/preview",
        "api:POST /api/v1/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/information/manual-confirmation",
        "api:POST /api/v1/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/information/manual-confirmation/preview",
        "api:POST /api/v1/orders/{case_no}/contract-external-signing/client/completion-reports",
        "api:POST /api/v1/orders/{case_no}/contract-external-signing/final-document/apply",
        "api:POST /api/v1/orders/{case_no}/contract-external-signing/final-document/preview",
        "api:POST /api/v1/orders/{case_no}/contract-external-signing/final-document/staging",
        "api:POST /api/v1/orders/{case_no}/contract-external-signing/legacy-recovery/apply",
        "api:POST /api/v1/orders/{case_no}/contract-external-signing/legacy-recovery/preview",
        "api:POST /api/v1/orders/{case_no}/contract-external-signing/staff-segments/{segment_id}/completion-reports",
        "api:POST /api/v1/orders/{case_no}/contract-signing/client/manual-attestation",
        "api:POST /api/v1/orders/{case_no}/contract-signing/client/manual-attestation/preview",
        "api:POST /api/v1/orders/{case_no}/contract-signing/staff-segments/{segment_id}/manual-attestation",
        "api:POST /api/v1/orders/{case_no}/contract-signing/staff-segments/{segment_id}/manual-attestation/preview",
        "api:POST /api/v1/orders/{case_no}/matching-plans/{plan_id}/resumes/manual-confirmation",
        "api:POST /api/v1/orders/{case_no}/matching-plans/{plan_id}/resumes/manual-confirmation/preview",
        "api:POST /api/v1/orders/{case_no}/service-before-replacement/apply",
        "api:POST /api/v1/orders/{case_no}/service-before-replacement/preview",
        "api:POST /api/v1/orders/{case_no}/service-completion/preview",
        "api:POST /api/v1/runtime/line-alert-targets/admin/preview",
        "api:POST /api/v1/runtime/line-alert-targets/group/reset",
        "api:POST /api/v1/runtime/line-alert-targets/group/reset/preview",
        "api:POST /api/v1/runtime/line-alert-targets/{target_id}/preview",
        "api:PUT /api/v1/line/rich-menus/draft",
    }
)
# These identities remain grouped for review metadata even though the source
# retirement override above now makes each terminal disposition `retired_410`.
SOURCE_MEDIA_REWRITE_HTTP_ENTRIES = frozenset(
    {
        "api:GET /api/v1/storage/files",
        "api:GET /api/v1/storage/files/{file_id}",
        "api:GET /api/v1/storage/files/{file_id}/download",
        "api:GET /api/v1/storage/receipts/{receipt_id}",
        "api:POST /api/v1/storage/files/apply",
        "api:POST /api/v1/storage/files/preview",
        "api:POST /api/v1/storage/staging",
    }
)
SOURCE_ANOMALY_REWRITE_HTTP_ENTRIES = frozenset(
    {
        "api:GET /api/v1/anomaly-recovery/projector/dead-letters",
        "api:POST /api/v1/anomaly-recovery/projector/dead-letters/{projector_identity}/{event_id}/retry/apply",
        "api:POST /api/v1/anomaly-recovery/projector/dead-letters/{projector_identity}/{event_id}/retry/preview",
        "api:POST /api/v1/anomaly-recovery/projector/dead-letters/{projector_identity}/{event_id}/supersede/apply",
        "api:POST /api/v1/anomaly-recovery/projector/dead-letters/{projector_identity}/{event_id}/supersede/preview",
    }
)
SOURCE_OWNER_COMMAND_REWRITE_HTTP_ENTRIES = frozenset(
    {"api:POST /api/v1/beclass-import-reviews/apply"}
)
SOURCE_LOCAL_REWRITE_HTTP_ENTRIES = (
    SOURCE_MEDIA_REWRITE_HTTP_ENTRIES
    | SOURCE_ANOMALY_REWRITE_HTTP_ENTRIES
    | SOURCE_OWNER_COMMAND_REWRITE_HTTP_ENTRIES
)
SOURCE_EXTERNAL_EVIDENCE_HTTP_ENTRIES = frozenset(
    {
        "api:GET /api/v1/admin/entry-targets",
        "api:GET /api/v1/admin/entry-targets/{entry_id}",
        "api:GET /api/v1/line/media-assets/rich-menu/{asset_id}",
        "api:GET /api/v1/orders/historical-baseline-projector/deliveries/{delivery_identity}",
        "api:GET /api/v1/orders/{case_no}/historical-operational-baseline",
        "api:GET /static/bind.html",
        "api:POST /api/v1/admin/entry-targets/apply",
        "api:POST /api/v1/admin/entry-targets/preview",
        "api:POST /api/v1/line/identity/admin/preview",
        "api:POST /api/v1/line/identity/registration/preview",
        "api:POST /api/v1/line/mobile-admin/customer-service/tickets/{ticket_id}/reply/apply",
        "api:POST /api/v1/line/mobile-admin/customer-service/tickets/{ticket_id}/reply/preview",
        "api:POST /api/v1/line/mobile-admin/identity-reviews/{request_id}/decision/apply",
        "api:POST /api/v1/line/mobile-admin/identity-reviews/{request_id}/decision/preview",
        "api:POST /api/v1/line/staff-self-service/leave-requests/apply",
        "api:POST /api/v1/line/staff-self-service/leave-requests/preview",
        "api:POST /api/v1/line/staff-self-service/leave-requests/{request_id}/query",
        "api:POST /api/v1/line/staff-self-service/service-day-logs/apply",
        "api:POST /api/v1/line/staff-self-service/service-day-logs/preview",
        "api:POST /api/v1/line/staff-self-service/service-day-logs/{log_id}/query",
        "api:POST /api/v1/orders/{case_no}/historical-operational-baseline/apply",
        "api:POST /api/v1/orders/{case_no}/historical-operational-baseline/preview",
        "api:POST /api/v1/orders/{case_no}/matching-plans/{plan_id}/schedule-confirmation/manual-apply",
        "api:POST /api/v1/orders/{case_no}/matching-plans/{plan_id}/schedule-confirmation/manual-preview",
    }
)
SOURCE_CANONICAL_OPERATOR_ENTRIES = {
    "cli:scripts/generate_task97_commit_dispositions.py": (
        "Architecture Governance",
        "Regenerate the tracked Task 97 repository-commit disposition evidence from current source.",
        "authorized architecture-governance operator",
    ),
    "cli:scripts/generate_task97_entry_governance.py": (
        "Architecture Governance",
        "Regenerate the tracked Task 97 entry-governance evidence from the reviewed queue.",
        "authorized architecture-governance operator",
    ),
    "cli:scripts/generate_task97_production_script_inventory.py": (
        "Architecture Governance",
        "Regenerate the tracked Task 97 production-script inventory from current executable sources.",
        "authorized architecture-governance operator",
    ),
    "cli:scripts/launchers/local_mysql_tcp_forward.py": (
        "Local Infrastructure",
        "Provide the container-internal TCP hop used by the governed local Cloud Run database bridge launcher.",
        "authorized local infrastructure operator through manage_gcp_cloud_run_db_bridge.ps1",
    ),
    "cli:scripts/validate_agent_governance.py": (
        "Global Agent Governance",
        "Validate the canonical Agent task-grade, document-routing, and DB-gate links for the current repository.",
        "authorized repository governance operator",
    ),
    "cli:scripts/validate_streamlit_retirement_readiness.py": (
        "Frontend Retirement Governance",
        "Run the approved read-only Phase 6A installation or retirement-readiness gate without changing entry state.",
        "authorized frontend retirement gate operator",
    ),
}
SOURCE_CANONICAL_OPERATOR_CALLER_EVIDENCE = {
    "cli:scripts/launchers/local_mysql_tcp_forward.py": (
        "scripts/launchers/manage_gcp_cloud_run_db_bridge.ps1 mounts the file "
        "read-only and invokes it inside the dedicated forward container; the "
        "published host port is explicitly bound to 127.0.0.1"
    ),
    "cli:scripts/validate_agent_governance.py": (
        "document/架構重整/00_Agent任務分級與交付規範.md explicitly "
        "declares this validator as its minimal static consistency check"
    ),
    "cli:scripts/validate_streamlit_retirement_readiness.py": (
        "the approved Phase 6A retirement release-gate work package lists this "
        "validator in its exact write set and required commands"
    ),
}
REVIEW_REQUIRED_PATH_GOVERNANCE = {
    "api/main.py": ("LINE Identity", "browser user accessing the identity binding entry"),
    "api/routes/admin_auth.py": ("Access Control", "unauthenticated administrator completing the bounded login challenge"),
    "api/routes/admin_entry_targets.py": ("Global Entry Target Governance", "authenticated release or cutover operator"),
    "api/routes/anomaly_recovery.py": ("Anomalies / Global Durable Jobs", "authenticated anomaly recovery operator"),
    "api/routes/candidate_contact_pool.py": ("Scheduling Candidate Contact", "authenticated scheduling operator"),
    "api/routes/client_refund_reversal.py": ("Client Finance", "authenticated client-finance operator"),
    "api/routes/contract_external_signing.py": ("Contract Signing", "authenticated contract-signing operator or verified external signing integration"),
    "api/routes/contract_signing.py": ("Contract Signing", "authenticated contract-signing operator"),
    "api/routes/controlled_files.py": ("Global Controlled Files", "authenticated controlled-file operator"),
    "api/routes/customer_service.py": ("Customer Service", "authenticated customer-service operator"),
    "api/routes/data_browser_admin.py": ("Data Browser Admin Projection", "authenticated administrator"),
    "api/routes/finance_import.py": ("Finance Import", "authenticated finance-import operator"),
    "api/routes/government_subsidy.py": ("Government Subsidy", "authenticated government-subsidy operator"),
    "api/routes/hcm_import.py": ("Case Import", "authenticated case-import operator"),
    "api/routes/historical_baseline_projector.py": ("Orders Historical Baseline", "authenticated historical-baseline operator or projector worker"),
    "api/routes/historical_completion.py": ("Orders", "authenticated historical-completion operator"),
    "api/routes/historical_operational_baseline.py": ("Orders Historical Operational Baseline", "authenticated historical-baseline operator"),
    "api/routes/historical_order_review_remediation.py": ("Orders Historical Review", "authenticated historical-review operator"),
    "api/routes/import_warning_tracking.py": ("Import Warning Tracking", "authenticated import operator"),
    "api/routes/jobs.py": ("Global Durable Jobs", "authenticated job observer"),
    "api/routes/line_configurations.py": ("LINE Configuration", "authenticated LINE configuration operator"),
    "api/routes/line_identity.py": ("LINE Identity", "authenticated LINE identity operator or verified LINE principal"),
    "api/routes/line_media_assets.py": ("LINE Integration Media", "authenticated LINE media operator"),
    "api/routes/line_order_groups.py": ("LINE Order Group Integration", "authenticated LINE order-group operator"),
    "api/routes/line_rich_menus.py": ("LINE Rich Menu Publication", "authenticated LINE rich-menu operator"),
    "api/routes/matches.py": ("Scheduling Matching Communication", "authenticated scheduling operator"),
    "api/routes/matching_coordination.py": ("Scheduling Matching Coordination", "authenticated scheduling operator"),
    "api/routes/matching_schedule_confirmation.py": ("Scheduling", "authenticated scheduling operator"),
    "api/routes/operations_reports.py": ("Operations Reporting Projection", "authenticated operations-report operator"),
    "api/routes/order_auto_completion.py": ("Orders", "authenticated order-completion operator or scheduler"),
    "api/routes/order_cancellation.py": ("Orders", "authenticated orders operator"),
    "api/routes/private_operations.py": ("Global Runtime Supervision", "authenticated internal runtime service"),
    "api/routes/runtime_health.py": ("Global Runtime Supervision", "authenticated runtime operator"),
    "api/routes/service_before_replacement.py": ("Scheduling Service Before Replacement", "authenticated scheduling recovery operator"),
    "api/routes/staff_leave_intake.py": ("Scheduling", "verified staff member through LINE self-service"),
    "api/routes/staff_payout.py": ("Staff Payables", "authenticated staff-payables operator"),
    "api/routes/staff_service_day_logs.py": ("Scheduling Service Day Log", "verified staff member through LINE self-service"),
    "scripts/build_local_additive_qualification.py": ("Global Migration Qualification", "authorized local migration qualification operator; caller not evidenced"),
    "scripts/build_react_admin_artifact.py": ("Frontend Release", "authorized frontend build operator; caller not evidenced"),
    "scripts/collect_local_additive_engine_evidence.py": ("Global Migration Qualification", "authorized local evidence operator; caller not evidenced"),
    "scripts/launchers/local_mysql_tcp_forward.py": ("Local Infrastructure", "authorized local infrastructure operator; caller not evidenced"),
    "scripts/migrate_admin_capability_grants_schema.py": ("Access Control Migration", "authorized migration operator; caller not evidenced"),
    "scripts/run_task96_hob_route_a.py": ("Task 96 HOB Scenario Evidence", "authorized Task 96 evidence operator; caller not evidenced"),
    "scripts/run_task96_payout001_scenario.py": ("Task 96 Staff Payables Scenario Evidence", "authorized Task 96 evidence operator; caller not evidenced"),
    "scripts/run_task96_rpre_browser_scenario.py": ("Task 96 Replacement Scenario Evidence", "authorized Task 96 evidence operator; caller not evidenced"),
    "scripts/validate_agent_governance.py": ("Global Agent Governance", "authorized governance validator operator; caller not evidenced"),
    "scripts/validate_streamlit_retirement_readiness.py": ("Frontend Retirement Governance", "authorized frontend retirement operator; caller not evidenced"),
    "ui/pages/09_data_import.py": ("Import UI Composition", "authenticated import operator"),
}
REVIEW_REQUIRED_REACT_OWNERS = {
    "ui-react:#account-management": "Access Control",
    "ui-react:#anomalies": "Anomalies",
    "ui-react:#data-import": "Import UI Composition",
    "ui-react:#finance": "Finance UI Composition",
    "ui-react:#line-ai-events": "LINE AI Event Observation",
    "ui-react:#line-liff-studio": "LINE LIFF Configuration",
    "ui-react:#line-management": "LINE Integration",
    "ui-react:#line-security": "LINE Security",
    "ui-react:#order-tracker": "Orders Tracking Projection",
    "ui-react:#orders": "Orders",
    "ui-react:#reports": "Reporting Projection",
    "ui-react:#scheduling": "Scheduling",
    "ui-react:#staff": "Staff Operations / Scheduling",
    "ui-react:#system-status": "Global Runtime Supervision",
}
LOCAL_CANONICAL_EVIDENCE_BY_SOURCE = {
    "api/routes/anomaly_recovery.py": (
        "ui_react/src/api/anomalies/anomaly_detail_client.ts",
        "tests/domains/anomalies/subsystems/anomalies/integration/test_anomaly_public_detail_recovery_contract.py; ui_react/src/tests/anomaly_detail_client.test.ts",
    ),
    "api/routes/admin_auth.py": ("ui_react/src/api/auth/session_client.ts", "tests/test_admin_auth_runtime.py; tests/test_admin_auth_security.py"),
    "api/routes/candidate_contact_pool.py": ("ui_react/src/api/scheduling/candidate_contact_pool_client.ts", "tests/test_candidate_contact_pool_workflow.py; ui_react/src/tests/candidate_contact_pool_client.test.ts"),
    "api/routes/client_refund_reversal.py": ("ui_react/src/api/client_finance/client_over_refund_recovery_client.ts", "tests/test_client_refund_reversal_route.py; tests/domains/client-finance/subsystems/client-finance/integration/test_client_refund_overage.py"),
    "api/routes/contract_external_signing.py": ("ui_react/src/api/orders/contract_external_signing_client.ts", "tests/domains/contract-signing/subsystems/contract-signing/integration/test_contract_external_signing_api.py; ui_react/src/tests/contract_external_signing_client.test.ts"),
    "api/routes/contract_signing.py": ("ui_react/src/api/orders/contract_signing_mutation_client.ts", "tests/test_client_contract_signing_application.py; tests/test_staff_contract_signing_application.py; ui_react/src/tests/contract_signing_mutation_client.test.ts"),
    "api/routes/customer_service.py": ("ui_react/src/api/customer_service_escalations/customer_service_escalation_client.ts and customer_service_client.ts", "tests/test_customer_service_escalation_api_contract.py; tests/test_customer_service_reply_preview_apply.py; tests/test_customer_service_preview_contract.py"),
    "api/routes/data_browser_admin.py": ("ui_react/src/api/data_browser/data_browser_query_client.ts", "tests/test_data_browser_query_contract.py; ui_react/src/tests/data_browser_query_client.test.ts"),
    "api/routes/finance_import.py": ("ui_react/src finance-import typed mutation/outcome clients", "tests/test_finance_import_batch_job_outcome_route.py; ui_react/src/tests/finance_import_mutation_client.test.ts; ui_react/src/tests/finance_import_correction_client.test.ts"),
    "api/routes/government_subsidy.py": ("ui_react/src government-overpayment typed recovery client", "tests/domains/government-subsidy/subsystems/government-subsidy/integration/test_government_subsidy_overpayment_query.py; ui_react/src/tests/government_overpayment_recovery_client.test.ts"),
    "api/routes/hcm_import.py": ("ui_react/src/api/case_import/hcm_import_result_client.ts", "tests/test_hcm_import_router.py; ui_react/src/tests/hcm_import_result_client.test.ts"),
    "api/routes/historical_baseline_projector.py": ("ui_react/src/api/anomalies/historical_baseline_projector_client.ts", "tests/domains/anomalies/subsystems/anomalies/integration/test_historical_baseline_projector_api.py; ui_react/src/tests/historical_baseline_projector_readback.test.tsx"),
    "api/routes/historical_completion.py": ("ui_react/src/api/orders/historical_completion_client.ts", "tests/domains/orders/subsystems/orders/integration/test_historical_completion_api.py; ui_react/src/tests/historical_completion.test.tsx"),
    "api/routes/historical_order_review_remediation.py": ("ui_react/src/api/orders/historical_review_remediation/client.ts", "tests/domains/orders/subsystems/orders/integration/test_historical_order_review_remediation_api.py; ui_react/src/tests/historical_order_review_remediation.test.tsx"),
    "api/routes/import_warning_tracking.py": ("ui_react import-warning typed transition client", "tests/test_import_warning_tracking_api.py; tests/test_import_warning_transition_receipt_contract.py; ui_react/src/tests/import_warning_transition_client.test.ts"),
    "api/routes/jobs.py": ("ui_react typed job observation client", "tests/test_jobs_public_observation_route.py; ui_react/src/tests/account_query_client.test.ts"),
    "api/routes/line_configurations.py": ("ui_react/src/api/line_safe_config/line_safe_config_client.ts", "tests/domains/external-integration/subsystems/line/integration/test_line_configuration_public_query_route.py; ui_react/src/tests/line_configuration_query_client.test.ts"),
    "api/routes/line_identity.py": ("ui_react/src/api/line_identity/line_identity_client.ts", "tests/domains/external-integration/subsystems/line/infrastructure/test_line_identity_api_routes.py; ui_react/src/tests/line_identity_client.test.ts"),
    "api/routes/line_media_assets.py": ("ui_react/src/api/line_rich_menu_media/line_rich_menu_media_client.ts", "tests/test_line_management_stage9.py; ui_react/src/tests/line_rich_menu_media_client.test.ts"),
    "api/routes/line_order_groups.py": ("ui_react/src/api/line_order_groups/line_order_group_query_client.ts", "tests/domains/external-integration/subsystems/line/subsystems/test_line_order_group_numbered_api.py; ui_react/src/tests/line_order_group_query_client.test.ts"),
    "api/routes/line_rich_menus.py": ("ui_react/src/api/line_rich_menu_draft/line_rich_menu_draft_client.ts", "tests/domains/external-integration/subsystems/line/subsystems/test_line_rich_menu_draft_api.py; ui_react/src/tests/line_rich_menu_draft_client.test.ts"),
    "api/routes/matches.py": ("ui_react/src/api/scheduling/matching_plan_communication_client.ts", "tests/test_task97_typed_matching_receipts.py; ui_react/src/tests/matching_plan_communication_client.test.ts"),
    "api/routes/matching_coordination.py": ("ui_react/src/api/matching_coordination/matching_coordination_client.ts", "tests/test_matching_coordination_application.py; tests/test_matching_coordination_public_contract.py; ui_react/src/tests/matching_coordination_client.test.ts"),
    "api/routes/operations_reports.py": ("ui_react weekly operations report typed query/export client", "tests/test_weekly_operations_report_contract.py; ui_react/src/tests/weekly_operations_report_client.test.ts"),
    "api/routes/order_auto_completion.py": ("ui_react/src/api/orders/order_service_completion_client.ts", "tests/domains/orders/subsystems/orders/integration/test_order_auto_completion_routes.py; tests/domains/orders/subsystems/orders/integration/test_order_auto_completion_workflow.py"),
    "api/routes/order_cancellation.py": ("ui_react/src/api/orders/order_cancellation_client.ts", "tests/domains/orders/subsystems/orders/integration/test_order_cancellation_receipt_route.py; ui_react/src/tests/order_cancellation_client.test.ts"),
    "api/routes/private_operations.py": ("internal runtime startup and artifact-health observer", "tests/test_react_admin_artifact_health.py; tests/test_private_runtime_operations.py"),
    "api/routes/runtime_health.py": ("ui_react runtime alert target typed client", "tests/test_runtime_alert_target_admin_contract.py; tests/domains/external-integration/subsystems/line/subsystems/test_runtime_alert_target_application.py"),
    "api/routes/service_before_replacement.py": ("ui_react/src/api/orders/service_before_replacement_client.ts", "tests/domains/scheduling/subsystems/scheduling/modules/service-before-replacement/contract/test_service_before_replacement_api.py; ui_react/src/tests/service_before_replacement_actions.test.tsx"),
    "api/routes/staff_payout.py": ("ui_react/src/api/staff_payables/staff_overpayment_recovery_client.ts", "tests/domains/staff-payables/subsystems/staff-payables/integration/test_staff_overpayment_recovery.py; ui_react/src/tests/staff_overpayment_recovery_client.test.ts"),
}


def discover_entrypoints() -> list[dict[str, object]]:
    entries = [*_discover_api_entries(), *_discover_ui_entries(), *_discover_react_entries(), *_discover_cli_entries()]
    return sorted(entries, key=lambda entry: str(entry["entry_id"]))


def build_review_queue() -> list[dict[str, object]]:
    existing = _existing_entries()
    return [
        _govern_entry(_apply_source_retirement(_merge_reviewed_entry(entry, existing)))
        for entry in discover_entrypoints()
    ]


def _apply_source_retirement(entry: dict[str, object]) -> dict[str, object]:
    identity = str(entry["entry_id"])
    if identity in SOURCE_OWNER_COMMAND_REWRITE_HTTP_ENTRIES:
        return {
            **entry,
            "status": "review_required",
            "canonical_owner": "Case Import / Client or Staff owning domain",
            "business_scenario": (
                "Apply one accepted BeClass review only through the exact owning "
                "Client or Staff typed command inside the Case Import outer Unit of Work."
            ),
            "operator": "authenticated Case Import reviewer",
            "caller_evidence": (
                "runtime registration is present; the current composition fails closed "
                "because no approved owning typed command exists"
            ),
            "external_operator_evidence": (
                "repository-local route evidence only; production caller authority is not claimed"
            ),
            "replacement": (
                "Client or Staff owning typed BeClass command inside the Case Import outer Unit of Work"
            ),
            "replacement_readback": "blocked until the owning typed command provides fresh authoritative readback",
            "deletion_gate": "blocked_owner_command_contract",
            "focused_regression": "tests/test_beclass_import_review_owner_command_gate.py",
            "final_zero_reference_oracle": (
                "zero runtime references to the fail-closed writer after the owning typed command is composed"
            ),
            "terminal_receipt": f"entrypoint-review-v1:{identity}:rewrite_to_canonical",
        }
    if (
        identity in SOURCE_LOCAL_CANONICAL_HTTP_ENTRIES
        and identity not in SOURCE_RETIRED_HTTP_ENTRIES
    ):
        source_path = str(entry["source_path"])
        governance = REVIEW_REQUIRED_PATH_GOVERNANCE.get(source_path)
        evidence = LOCAL_CANONICAL_EVIDENCE_BY_SOURCE.get(source_path)
        if governance is None or evidence is None:
            raise ValueError(f"canonical local entry lacks exact governance evidence: {identity}")
        owner, operator = governance
        typed_caller, focused_regression = evidence
        caller_evidence = (
            f"runtime registration plus repository-local typed caller {typed_caller}; "
            f"focused canonical contract: {focused_regression}"
        )
        return {
            **entry,
            "status": "active",
            "canonical_owner": owner,
            "business_scenario": f"Execute or read the bounded {owner} scenario identified by {identity}.",
            "operator": operator,
            "caller_evidence": caller_evidence,
            "external_operator_evidence": (
                "not required for the evidenced repository-local canonical caller; "
                "production deployment or external usage is not claimed"
            ),
            "replacement": identity,
            "replacement_readback": (
                f"typed receipt, projection, or bounded response readback through {typed_caller}"
            ),
            "deletion_gate": "not_applicable_active_canonical",
            "focused_regression": focused_regression,
            "final_zero_reference_oracle": "not_applicable_active_canonical",
            "terminal_receipt": f"entrypoint-review-v1:{identity}:active_canonical",
        }
    operator_contract = SOURCE_CANONICAL_OPERATOR_ENTRIES.get(identity)
    if operator_contract is not None:
        owner, scenario, operator = operator_contract
        caller_evidence = SOURCE_CANONICAL_OPERATOR_CALLER_EVIDENCE.get(
            identity,
            "tracked Task 97 governance generation and focused reproducibility test",
        )
        return {
            **entry,
            "status": "operator_only",
            "canonical_owner": owner,
            "business_scenario": scenario,
            "operator": operator,
            "caller_evidence": caller_evidence,
            "external_operator_evidence": caller_evidence,
            "replacement": identity,
            "replacement_readback": "task97_entry_governance_v1.json source hash and record counts",
            "deletion_gate": "not_applicable_operator_only_guarded",
            "focused_regression": "tests/test_task97_entry_governance_artifact.py",
            "final_zero_reference_oracle": "not_applicable_operator_only_guarded",
        }
    replacement = SOURCE_RETIRED_HTTP_ENTRIES.get(identity)
    if replacement is None:
        return entry
    governance = REVIEW_REQUIRED_PATH_GOVERNANCE.get(str(entry["source_path"]))
    owner = entry.get("canonical_owner")
    operator = entry.get("operator")
    if governance is not None:
        owner = owner or governance[0]
        operator = operator or governance[1]
    caller_evidence = (
        "runtime registration confirmed; repository static caller not found; "
        "external/operator caller evidence remains unknown"
    )
    return {
        **entry,
        "status": "retired_410",
        "canonical_owner": owner,
        "business_scenario": entry.get("business_scenario") or f"Retire the bounded entry {identity} after its canonical replacement is available.",
        "operator": operator,
        "replacement": replacement,
        "replacement_readback": replacement,
        "caller_evidence": caller_evidence,
        "external_operator_evidence": caller_evidence,
        "deletion_gate": (
            "blocked_media_successor_schema_and_runtime_gate"
            if identity in SOURCE_MEDIA_RETIRED_HTTP_ENTRIES
            else "blocked_external_evidence: remove only after external/operator caller "
            "evidence and replacement migration are complete"
        ),
        "final_zero_reference_oracle": (
            f"zero inbound callers and zero runtime references to retired identity {identity}"
        ),
        "focused_regression": entry.get("focused_regression") or (
            "tests/test_task97_finance_import_job_retirement.py; "
            "tests/test_jobs_public_observation_route.py"
            if identity == "api:GET /api/v1/finance-import/jobs/{job_id}"
            else f"entry queue discovery plus focused retirement contract for {entry['source_path']}"
        ),
        "terminal_receipt": f"entrypoint-review-v1:{identity}:retired_410",
    }


def main() -> int:
    entries = build_review_queue()
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(_render_queue(entries), encoding="utf-8")
    review_count = sum(entry["status"] == "review_required" for entry in entries)
    print(f"entrypoint_review_queue entries={len(entries)} review_required={review_count}")
    return 0


def _discover_api_entries() -> list[dict[str, object]]:
    paths = [ROOT / "api/main.py", *(ROOT / "api/routes").glob("*.py"), ROOT / "line/line_bot.py"]
    return [entry for path in paths if path.name != "__init__.py" for entry in _api_entries(path)]


def _api_entries(path: Path) -> list[dict[str, object]]:
    tree = _tree(path)
    prefix_by_name = _router_prefixes(tree)
    return [
        _new_entry("api", f"{method.upper()} {_route_path(prefix_by_name, decorator)}", path)
        for function in tree.body
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in function.decorator_list
        for method in [_http_method(decorator)]
        if method is not None
    ]


def _router_prefixes(tree: ast.Module) -> dict[str, str]:
    return {
        target.id: _keyword_string(value, "prefix")
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        for value in [node.value]
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in {"APIRouter", "FastAPI"}
    }


def _http_method(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
        return None
    method = decorator.func.attr.lower()
    return method if method in HTTP_METHODS else None


def _route_path(prefix_by_name: dict[str, str], decorator: ast.expr) -> str:
    assert isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
    owner = decorator.func.value
    prefix = prefix_by_name.get(owner.id, "") if isinstance(owner, ast.Name) else ""
    suffix = decorator.args[0].value if decorator.args and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str) else ""
    return f"{prefix}{suffix}" or "/"


def _discover_ui_entries() -> list[dict[str, object]]:
    modules = _runtime_page_registry()
    return [
        _new_entry("ui", f"{module.removeprefix('ui.pages.')}.py", ROOT / "ui" / "pages" / f"{module.removeprefix('ui.pages.')}.py")
        for module in modules
    ]


def _runtime_page_registry() -> list[str]:
    tree = _tree(ROOT / "ui" / "app.py")
    for node in tree.body:
        if isinstance(node, ast.Assign):
            is_registry = any(isinstance(target, ast.Name) and target.id == "PAGE_REGISTRY" for target in node.targets)
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "PAGE_REGISTRY":
            is_registry = True
            value_node = node.value
        else:
            is_registry = False
            value_node = None
        if not is_registry or value_node is None:
            continue
        return list(dict.fromkeys(
            value.value for value in ast.walk(value_node)
            if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.startswith("ui.pages.")
        ))
    raise ValueError("ui/app.py PAGE_REGISTRY not found")


def _discover_react_entries() -> list[dict[str, object]]:
    nav_source = REACT_NAV_PATH.read_text(encoding="utf-8")
    app_source = REACT_APP_PATH.read_text(encoding="utf-8")
    nav_ids = re.findall(r"\{\s*id:\s*'([a-z0-9-]+)'\s*,", nav_source)
    render_ids = set(re.findall(r"currentPage\s*===\s*'([a-z0-9-]+)'", app_source))
    entries = []
    for page_id in dict.fromkeys(nav_ids):
        entry = _new_entry("ui-react", f"#{page_id}", REACT_NAV_PATH)
        entry["witnesses"] = {
            "nav": REACT_NAV_PATH.relative_to(ROOT).as_posix(),
            "render": REACT_APP_PATH.relative_to(ROOT).as_posix() if page_id in render_ids else None,
        }
        rollback = REACT_ROLLBACKS.get(page_id)
        if rollback is None or page_id not in render_ids:
            entry["review_reason"] = "blocked_react_registry_drift"
        else:
            entry["streamlit_entry"], entry["rollback_deep_link"], entry["replacement_group"] = rollback
        entries.append(entry)
    return entries


def _page_title(path: Path) -> str | None:
    return next((value.value for node in _tree(path).body if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name) and target.id == "title" for value in [node.value] if isinstance(value, ast.Constant) and isinstance(value.value, str)), None)


def _discover_cli_entries() -> list[dict[str, object]]:
    return [_new_entry("cli", path.relative_to(ROOT).as_posix(), path) for path in (ROOT / "scripts").rglob("*.py") if _has_main_guard(path)]


def _has_main_guard(path: Path) -> bool:
    return any(isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__" for node in _tree(path).body)


def _new_entry(kind: str, label: str, path: Path) -> dict[str, object]:
    return {"entry_id": f"{kind}:{label}", "kind": kind, "source_path": path.relative_to(ROOT).as_posix(), "status": "review_required"}


def _existing_entries() -> dict[str, dict[str, object]]:
    if not QUEUE_PATH.exists():
        return {}
    return {
        str(entry["entry_id"]): entry
        for line in QUEUE_PATH.read_text(encoding="utf-8").splitlines()
        if line
        for entry in [json.loads(line)]
    }


def _merge_reviewed_entry(entry: dict[str, object], existing: dict[str, dict[str, object]]) -> dict[str, object]:
    reviewed = existing.get(str(entry["entry_id"]), {})
    if reviewed.get("status") in {None, "review_required"}:
        return entry
    return {**entry, **{key: value for key, value in reviewed.items() if key not in {"kind", "source_path"}}}


def _govern_entry(entry: dict[str, object]) -> dict[str, object]:
    entry = _expand_legacy_placeholder(entry)
    entry = _expand_review_required_entry(entry)
    status = str(entry["status"])
    terminal_disposition = TERMINAL_DISPOSITION_BY_STATUS.get(status)
    if status == "review_required":
        terminal_disposition = (
            "rewrite_to_canonical"
            if str(entry["entry_id"]) in SOURCE_LOCAL_REWRITE_HTTP_ENTRIES
            or str(entry["source_path"]) == "ui/pages/09_data_import.py"
            else "blocked_external_evidence"
        )
    if terminal_disposition is None:
        return entry
    entry_id = str(entry["entry_id"])
    replacement = str(entry.get("replacement") or (entry_id if status == "active" else "none"))
    caller_evidence = str(
        entry.get("caller_evidence")
        or f"runtime-discovered {entry['kind']} entry; operator={entry.get('operator', 'not-evidenced')}"
    )
    return {
        **entry,
        "runtime_registration": f"{entry['source_path']}::{entry_id}",
        "current_inbound_callers": caller_evidence,
        "external_operator_evidence": str(
            entry.get("external_operator_evidence") or caller_evidence
        ),
        "replacement_path_or_symbol": replacement,
        "replacement_readback": str(
            entry.get("replacement_readback")
            or (f"current canonical entry readback: {entry_id}" if status == "active" else replacement)
        ),
        "deletion_410_gate": str(
            entry.get("deletion_gate")
            or (
                "not_applicable_active_canonical"
                if status == "active"
                else "blocked_external_evidence"
                if status == "review_required"
                else f"status:{status}"
            )
        ),
        "focused_regression": str(
            entry.get("focused_regression")
            or f"entry queue discovery plus focused contract tests for {entry['source_path']}"
        ),
        "final_zero_reference_oracle": str(
            entry.get("final_zero_reference_oracle")
            or ("not_applicable_active_canonical" if status == "active" else f"zero runtime reference to retired identity {entry_id}")
        ),
        "terminal_disposition": terminal_disposition,
        "terminal_receipt": str(entry.get("terminal_receipt") or f"entrypoint-review-v1:{entry_id}:{terminal_disposition}"),
    }


def _expand_review_required_entry(entry: dict[str, object]) -> dict[str, object]:
    if entry.get("status") != "review_required":
        return entry
    identity = str(entry["entry_id"])
    if identity in SOURCE_OWNER_COMMAND_REWRITE_HTTP_ENTRIES:
        return entry
    source_path = str(entry["source_path"])
    if source_path == "api/routes/line_mobile_admin.py":
        if "/customer-service/" in identity:
            owner = "Customer Service"
            operator = "authenticated LINE mobile customer-service operator"
        elif "/identity-reviews/" in identity:
            owner = "LINE Identity"
            operator = "authenticated LINE mobile identity-review operator"
        else:
            raise ValueError(f"unmapped LINE mobile review entry: {identity}")
    elif source_path == "ui_react/src/components/MasterLayout.tsx":
        owner = REVIEW_REQUIRED_REACT_OWNERS.get(identity)
        if owner is None:
            raise ValueError(f"unmapped React review entry: {identity}")
        operator = f"authenticated internal user of the {identity} navigation entry"
    else:
        governance = REVIEW_REQUIRED_PATH_GOVERNANCE.get(source_path)
        if governance is None:
            raise ValueError(f"unmapped review-required entry: {identity} ({source_path})")
        owner, operator = governance
    if source_path == "ui_react/src/components/MasterLayout.tsx":
        caller_evidence = (
            f"MasterLayout navigation and App authenticated-shell rendering confirm {identity}; "
            "typed page clients provide the current internal caller evidence"
        )
    elif source_path.startswith("scripts/"):
        caller_evidence = (
            f"Task 97 production-script inventory confirms CLI registration for {identity}; "
            "external/operator execution authority remains incomplete"
        )
    elif identity in SOURCE_MEDIA_REWRITE_HTTP_ENTRIES:
        caller_evidence = (
            f"runtime registration and typed controlled-file client confirm {identity}; "
            "the Scheduling reference/finalize/lease successor is not released"
        )
    else:
        caller_evidence = (
            f"runtime-discovered exact entry {identity}; repository registration is evidenced; "
            "external/operator caller evidence remains incomplete"
        )
    terminal_disposition = (
        "rewrite_to_canonical"
        if identity in SOURCE_LOCAL_REWRITE_HTTP_ENTRIES
        or source_path == "ui/pages/09_data_import.py"
        else "blocked_external_evidence"
    )
    status = (
        "active"
        if source_path == "ui_react/src/components/MasterLayout.tsx"
        else "review_required"
    )
    replacement = (
        identity
        if status == "active"
        else "Client or Staff owning typed BeClass command inside the Case Import outer Unit of Work"
        if identity in SOURCE_OWNER_COMMAND_REWRITE_HTTP_ENTRIES
        else "Global durable-job retry/supersede mechanism"
        if identity in SOURCE_ANOMALY_REWRITE_HTTP_ENTRIES
        else "Scheduling-owned reference-aware controlled-file workflow after the additive Media successor gate"
        if identity in SOURCE_MEDIA_REWRITE_HTTP_ENTRIES
        else "ui-react:#data-import"
        if source_path == "ui/pages/09_data_import.py"
        else "none (canonical or cutover replacement not yet evidenced)"
    )
    return {
        **entry,
        "status": status,
        "canonical_owner": owner,
        "business_scenario": f"Execute or read the bounded {owner} scenario identified by {identity}.",
        "operator": operator,
        "caller_evidence": caller_evidence,
        "replacement": replacement,
        "replacement_readback": (
            f"current canonical entry readback: {identity}"
            if status == "active"
            else "blocked until the owning typed command provides fresh authoritative readback"
            if identity in SOURCE_OWNER_COMMAND_REWRITE_HTTP_ENTRIES
            else "blocked until the Media successor provides authoritative Scheduling reference and finalize-state readback"
            if identity in SOURCE_MEDIA_REWRITE_HTTP_ENTRIES
            else "not evidenced"
        ),
        "deletion_gate": (
            "not_applicable_active_canonical"
            if status == "active"
            else "blocked_owner_command_contract"
            if identity in SOURCE_OWNER_COMMAND_REWRITE_HTTP_ENTRIES
            else "blocked_media_successor_schema_and_runtime_gate"
            if identity in SOURCE_MEDIA_REWRITE_HTTP_ENTRIES
            else "blocked_external_evidence"
        ),
        "focused_regression": (
            "tests/test_controlled_file_api.py; tests/test_controlled_file_reference_finalize_1015.py; "
            "tests/test_controlled_file_workflow.py; ui_react/src/tests/data_import_entry_cutover.test.tsx"
            if identity in SOURCE_MEDIA_REWRITE_HTTP_ENTRIES
            else "tests/test_beclass_import_review_owner_command_gate.py"
            if identity in SOURCE_OWNER_COMMAND_REWRITE_HTTP_ENTRIES
            else f"entry queue discovery plus focused contract tests for {source_path}"
        ),
        "final_zero_reference_oracle": (
            "not_applicable_active_canonical"
            if status == "active"
            else "zero runtime references to the fail-closed writer after the owning typed command is composed"
            if identity in SOURCE_OWNER_COMMAND_REWRITE_HTTP_ENTRIES
            else "new controlled-file apply/download paths require reference/finalize/lease successor; legacy paths remain readable only until explicit retirement gate"
            if identity in SOURCE_MEDIA_REWRITE_HTTP_ENTRIES
            else f"zero inbound callers and zero runtime references to unresolved identity {identity}"
        ),
        "terminal_receipt": (
            f"entrypoint-review-v1:{identity}:"
            f"{'active_canonical' if status == 'active' else terminal_disposition}"
        ),
    }


def _expand_legacy_placeholder(entry: dict[str, object]) -> dict[str, object]:
    if entry.get("canonical_owner") != "owning bounded domain":
        return entry
    source_path = str(entry["source_path"])
    entry_id = str(entry["entry_id"])
    if source_path.endswith("customer_service.py"):
        owner, scenario, operator = "Customer Service", "Manage and read a bounded customer-service ticket.", "authenticated customer-service operator"
    elif source_path.endswith("line_identity_management.py") or source_path.endswith("line_identity.py"):
        owner, scenario, operator = "LINE Identity", "Validate or administer a bounded LINE identity lifecycle action.", "authenticated LINE identity operator or verified LINE principal"
    elif source_path.endswith("contract_signing.py"):
        owner, scenario, operator = "Contract Signing", "Download one versioned contract-signing document for a case.", "authenticated contract-signing operator"
    elif source_path.endswith("candidate_contact_pool.py"):
        owner, scenario, operator = "Scheduling Candidate Contact", "Read or update the bounded candidate-contact plan for one case.", "authenticated scheduling operator"
    elif source_path.endswith("leave_substitution.py"):
        owner, scenario, operator = "Scheduling", "Read the bounded leave-substitution assignments for one case.", "authenticated scheduling operator"
    elif source_path.endswith("matching_schedule_confirmation.py"):
        owner, scenario, operator = "Scheduling", "Preview, send, read, or update one bounded matching schedule confirmation.", "authenticated scheduling operator"
    elif source_path.endswith("service_date_confirmation.py"):
        owner, scenario, operator = "Scheduling", "Preview, apply, or read one case's versioned service-date confirmation.", "authenticated scheduling operator"
    elif source_path.endswith("multi_caregiver_case_assignments.py"):
        owner, scenario, operator = "Scheduling", "Read one staff member's bounded assignment schedule projection.", "authenticated scheduling operator"
    elif source_path.endswith("line_staff_self_service.py"):
        owner, scenario, operator = "Orders / Scheduling projections", "Serve a verified staff member's bounded order or schedule projection through LINE.", "verified and bound staff member"
    elif source_path.endswith("04_finance.py"):
        owner, scenario, operator = "Finance UI composition", "Render bounded owner projections for finance operations without owning their facts.", "authenticated finance operator"
    else:
        raise ValueError(f"unmapped legacy placeholder: {entry_id} ({source_path})")
    return {**entry, "canonical_owner": owner, "business_scenario": scenario, "operator": operator}


def _keyword_string(call: ast.Call, keyword: str) -> str:
    value = next((item.value for item in call.keywords if item.arg == keyword), None)
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else ""


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _render_queue(entries: list[dict[str, object]]) -> str:
    return "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries)


if __name__ == "__main__":
    raise SystemExit(main())
