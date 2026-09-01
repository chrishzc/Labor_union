# Module: finalize-runtime

## Parent
- domain: `global`
- subsystem: `controlled-files`

## Responsibility
Bounded 1015 finalize-intent runner. It claims pending or recoverable intents,
commits short CAS checkpoints around the local storage integrity read, and never
reports availability without digest-verified storage bytes.

## Implementation
- workflow: `subsystems/controlled_files/reference_finalize.py`
- MySQL runner: `infrastructure/mysql/controlled_file_finalize_worker.py`

## Verification
- integration_root: `tests/domains/global/subsystems/controlled-files/integration/`
- test: `test_controlled_file_finalize_runner.py`

## Change triggers
Reconcile when finalize state transitions, lease/checkpoint boundaries, worker
selection, or the controlled-file storage adapter changes.
