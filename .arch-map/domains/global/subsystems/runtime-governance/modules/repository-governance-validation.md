# Module: repository-governance-validation

## Parent

- domain: `global`
- subsystem: `runtime-governance`

## Responsibility

驗證 Agent 任務分級、正式規格與證據路由、資料庫變更執行門的文件標記，以及部署與效能規格的退役約束。驗證作業僅讀取 repository 文件。

## Implementation

- `scripts/validate_agent_governance.py`

## Verification

- layout_status: `custom_current`
- test_root: `tests/test_architecture_review_matrix_deployment_retirement.py`
- test_root: `tests/test_formal_spec_index_evidence_paths.py`
- test_root: `tests/test_performance_deployment_profile_retirement.py`
- 既有測試使用檔案所在目錄推導 repository root，沿用原路徑。

## Provenance

- `AGENTS.md`、`document/架構重整/00_Agent任務分級與交付規範.md` 與各檢核直接讀取的 current 規格。
