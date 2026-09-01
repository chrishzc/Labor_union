# Test module: matching-coordination-delivery

## Parent
- domain: `external-integration`
- subsystem: `line`

## Architecture
../../../../../../domains/external-integration/subsystems/line/modules/matching-coordination-delivery.md

## Verification
- test_root: tests/domains/external-integration/subsystems/line/modules/matching-coordination-delivery/contract/
- owner: `subsystems/line/matching_coordination_delivery.py`
- source/worker owners: `infrastructure/mysql/line_matching_coordination_delivery_source.py`, `subsystems/line/matching_coordination_delivery_worker.py`, `infrastructure/mysql/matching_coordination_customer_service_source.py`, `subsystems/customer_service/matching_coordination_worker.py`
- oracle: committed M3 handoff projects once to the existing delivery-task port, replay is idempotent, missing recipient/binding/config/message fails closed, success envelopes remain informational-only, local result is deterministic, legacy/manual failures do not block later rows, and LINE-006 readback remains typed.
