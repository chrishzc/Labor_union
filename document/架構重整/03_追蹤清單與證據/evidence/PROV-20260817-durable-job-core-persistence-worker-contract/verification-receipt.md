# Durable Job Core verification receipt

- Date：2026-08-22
- Final command：見 Core Work Package completion record。
- Result：`86 passed in 7.93s`。
- MySQL subset：`12 passed in 2.63s`，使用 3 個唯一 `lu_test_*` DB，無 skip；測後已清除自身 DB。
- Verified：typed JSON equality、Unicode/null/object/array/number、Key/key collation、same-key replay、四欄 mismatch、legacy NULL、closed success/failure、retry、crash-resume、zero hidden commit、worker transaction owner、heartbeat isolation。
- Not run：existing DB、`union_db`、provider、LINE、public API、browser、React、production、ports 8000／5174／8501。
- Phase 4 prerequisite：`PHASE4_SCENARIO_LINEAGE_METADATA_READY`，未升格 runtime PASS。
