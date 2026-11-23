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
  - 現行公開明細的測試替身透過唯讀 `query_current` 取得資料，並檢查復原描述包含可辨識的來源與版本，不執行業務 owner 的寫入。
  - 在相同測試檔的未知定義／動作與格式不符案例，路由層回傳明確的 `422`；不是 registry 直接回傳 HTTP 狀態。

## Change triggers
Reconcile when closed code identity、recovery descriptor fields、source binding或public detail action contract改變。
