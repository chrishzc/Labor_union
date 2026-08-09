# Availability Query Port Receipt

## Scope

`segmented_availability_query` now owns Scheduling availability orchestration
and pure result shaping only. `MySqlSegmentedAvailabilityFactsRepository` owns
the MySQL read boundary for the case, active staff, assignment occupancy,
legacy schedule occupancy, generation buffers, waiting-deposit locks, and
their seven-day buffers.

## Invariants

- The API request and response contracts are unchanged.
- The query port is read-only: it does not commit, roll back, or use row locks.
- `facts_port` is injectable for subsystem tests; production composes the MySQL
  adapter at the service boundary.
- Case-stage validation, date normalization, occupancy projection, conflict
  derivation, and matching feasibility remain owned by Scheduling.

## Verification

`tests/test_caregiver_segment_availability_service.py` and
`tests/test_segmented_availability_query_port.py` passed: 13 tests.

The fresh writer-inventory v3 candidate and disposition validators also passed
after the source move: 692 findings, 19 unresolved owner candidates, and 616
reviewed disposition records.
