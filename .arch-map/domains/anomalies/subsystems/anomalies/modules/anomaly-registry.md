# Module: anomaly-registry

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
擁有closed anomaly definition、action descriptor shape與current public detail所消費的source-bound recovery metadata；
不擁有或執行各business owner的mutation。

## Implementation
- `domains/anomalies/registry.py`

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/anomaly-registry/`
- higher_boundary:
  - `tests/domains/anomalies/subsystems/anomalies/integration/test_anomaly_public_detail_recovery_contract.py`

## Change triggers
Reconcile whenclosed code identity、recovery descriptor fields、source binding或public detail action contract改變。
