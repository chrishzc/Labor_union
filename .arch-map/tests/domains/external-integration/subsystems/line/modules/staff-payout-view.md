module: staff-payout-view
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/staff-payout-view.md
test_root: tests/domains/external-integration/subsystems/line/modules/staff-payout-view/

## Owned verification
- contract: verified binding constrains the query to its canonical `staff_id` and requested target payment month.
- contract: the LIFF page exposes the required per-order amount, payment date and status fields without accepting URL identity.
