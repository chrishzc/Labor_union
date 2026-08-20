# Phase 2D-H Candidate Change Inventory

日期：2026-08-16  
Branch／HEAD：`main`／`8615225481c8f72a9629289285516189b270cb36`

開工前已有大量 dirty／untracked 使用者成果；本輪未執行 checkout、reset、clean、stash、stage、commit
或push。`tests/test_import_warning_tracking_api.py` 原已修改，`tests/test_anomaly_registry_router.py` 原為
untracked Phase 2D成果，均採語意合併而非覆蓋。

| Path | Candidate SHA256 | Disposition |
|---|---|---|
| `subsystems/anomalies/alert_workflow.py` | `60FE56653F585E0C47960AB84FCE10BDCEF733F544BF5497DF6F778EAE98FC11` | registry enrichment與fail-closed integrity check |
| `api/schemas/anomaly_registry.py` | `16EFB77640A0DBEFB33F4DEA7EEBD835EC433C302DF470177C9734C9E121A26C` | severity/workflow public enum |
| `api/schemas/anomaly_recovery.py` | `84B260595DB53FE637761895AD3B45543803E3B712CE5FB99CA258AA9A6DC648` | recovery context public enum |
| `api/schemas/import_warning_tracking.py` | `62564DCA7895CED44140F3A3B98A2ED4747A0A3A032E48F418502A0DEA7A9D46` | task/preview status與四值request target public enum |
| `tests/test_anomaly_registry_router.py` | `76E2878343D31EED4F02541B20CC4D4C43128687C99E5E2FA0E194A8B1352332` | true Application shape、typed route error、OpenAPI enum tests |
| `tests/test_anomaly_closed_loop_disposable_mysql_e2e.py` | `9B0218E79A0E88867E9D538A2EE6D53060FFC84891C7C4B785A2EBDE986F2403` | canonical registry severity assertion；需disposable MySQL環境 |
| `tests/test_import_warning_tracking_api.py` | `6810043AABE2DA088B537C455D34C8E3ECA155590569735622E2EE13C1A93D65` | six-status、四target與negative/OpenAPI contract |
| `tests/test_import_warning_tracking_api_client.py` | `FAE9B2FA9163C9A3D6C72C853F90897E6F4B0433C93F193C0E1F3C94E1BF4A44` | header與既有client regression保留 |

## Boundary result

- Backend route path、Domain invariant、repository SQL、schema、migration：0 change。
- React production、Auth、shared transport、package/lockfile、Orders：0 change。
- DB change inventory：schema-only 0、system-seed 0、business-row-backfill 0、destructive 0。
