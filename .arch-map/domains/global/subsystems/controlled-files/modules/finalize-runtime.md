# Module: finalize-runtime

## Parent
- domain: `global`
- subsystem: `controlled-files`

## Responsibility
Bounded 1015 finalize-intent runner. It claims pending or recoverable intents,
commits short CAS checkpoints around the local storage integrity read, and never
reports availability without digest-verified storage bytes.

## Implementation
- domain contracts: `domains/controlled_files/reference_finalize.py`
- workflow: `subsystems/controlled_files/reference_finalize.py`
- MySQL runner: `infrastructure/mysql/controlled_file_finalize_worker.py`
- Shared-root production transport can set `layout_only=True`; its bounded selection includes only new 01–04 locators, preserving all pending legacy objects. Existing default runner behavior remains available to its original consumers.

## Verification
- integration_root: `tests/domains/global/subsystems/controlled-files/integration/`
- test: `test_controlled_file_finalize_runner.py`

## Change triggers
Reconcile when finalize state transitions, lease/checkpoint boundaries, worker
selection, or the controlled-file storage adapter changes.
