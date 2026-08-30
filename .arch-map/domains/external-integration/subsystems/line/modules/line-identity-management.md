# Module: line-identity-management

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
持久化 canonical LINE identity binding、subject replacement 與 review transition，並以 locked aggregate update 搭配 immutable binding event 維持版本與冪等邊界。

## Implementation
- primary:
  - `infrastructure/mysql/line_identity_review_repository.py`
- entrypoints:
  - `MySqlLineIdentityRepository.replace_subject`

## Dependencies
- outbound: `external-integration/line` — implements the LINE identity typed repository port used by the identity management application.
- inbound: `subsystems/line/identity_management_application.py` — coordinates replacement validation, owner projections, audit and the outer Unit of Work.

## Contracts
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` — same subject type replacement only; expected version and immutable transition event are required.
- `domains/line/identity_binding.py` — `LineIdentityClaim` and binding snapshot/status contract.

## Verification
- static:
  - `python -m py_compile infrastructure/mysql/line_identity_review_repository.py`
- test_root: `tests/domains/external-integration/subsystems/line/modules/line-identity-management/`

## Provenance
- `line_identity_bindings` is the canonical LINE identity root and its repository transition is the persistence adapter — `architecture_declared` — `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md`
- Repository implementation and same-type replacement regression are present at the paths above — `source_observed` — `infrastructure/mysql/line_identity_review_repository.py` and `tests/domains/external-integration/subsystems/line/modules/line-identity-management/regression/test_same_type_replacement.py`

## Change triggers
- Reconcile this module when LINE identity binding ownership, replacement constraints, persistence implementation root, or canonical module test root changes.
