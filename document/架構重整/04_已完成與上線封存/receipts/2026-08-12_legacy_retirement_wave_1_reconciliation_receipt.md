---
doc_type: validation-receipt
declared_status: completed
date: 2026-08-12
owner: architecture-governance
work_package: 19
---

# Legacy Retirement Wave 1 reconciliation receipt

## Authorization

On 2026-08-12, the user explicitly authorized retroactive reconciliation and
closeout after discovery that the two Wave 1A removal targets were already
absent from the current source tree.

## Current-state evidence

- Current HEAD: `1333a1fd03dde08c6364ac12758a3c3bf7383364`.
- Historical removal commit: `8f79a4856b90a6de57f726a23e88fda866b23529` on 2026-08-09.
- Absent targets: `services/caregiver_availability_lock_conversion_service.py`
  and `tests/test_caregiver_availability_lock_conversion_service.py`.
- Fresh static caller scan over `api`, `infrastructure`, `line`, `scripts`,
  `subsystems`, `ui`, `tests`, `start.bat`, and `pyproject.toml` found no
  reference to the legacy module or `convert_availability_lock_to_assignments`.
- `api/routes/caregiver_availability_locks.py` retains the deprecated convert
  route as `410 legacy_availability_lock_conversion_retired`, directing users
  to Assignment Plan Query/Preview/Apply.

## Replacement regression

```text
.venv\Scripts\python.exe -m pytest tests/test_waiting_deposit_lock_api_client.py tests/line/subsystems/test_line_waiting_lock_gate_stage7.py -q
5 passed in 0.44s
```

The tests prove the canonical waiting-deposit lock typed API client and the
customer-acceptance gate remain available. No MySQL, production test, schema
application, deployment, data mutation, or external side effect was performed.

## Closeout boundary

This is a retroactive documentation reconciliation. It does not rewrite the
historical authorization state of the 2026-08-09 removal; it records the
current completed state under the user's 2026-08-12 closeout authorization.
