# Phase 4 runtime receipt registry

此目錄只登錄 Phase 4 scenario 所需的 runtime receipt identity與初始狀態。`manifest.json`中的
`missing`、`not_run`與`blocked`都不是通過證據；`PHASE4_SCENARIO_LINEAGE_METADATA_READY`只表示scenario、
fixture、expected oracle與receipt identity可追溯。

本工作包不執行資料庫、browser、provider或production操作，也不建立任何runtime結果。後續bounded owner必須以
自己的exact Work Package產生fresh receipt；不得直接修改本registry把狀態改成完成。
