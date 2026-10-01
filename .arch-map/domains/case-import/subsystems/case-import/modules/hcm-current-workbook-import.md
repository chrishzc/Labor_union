# Module: hcm-current-workbook-import

## Parent
- domain: `case-import`
- subsystem: `case-import`

## Responsibility
編排 HCM Current workbook 的 Preview／Apply、既有來源 exact replay、review 與 Case Import reconciliation；相同 canonical source 必須回原 receipt，不得由暫存上傳檔名改變 replay 判定。

## Implementation
- primary:
  - `subsystems/case_import/hcm_workbook_import.py`
  - `subsystems/case_import/hcm_adapter.py`
  - `scripts/imports/import_client_hcm.py`
  - `domains/case_import/client_import_validation.py`
  - `domains/case_import/hcm_import_review.py` — 依最新正式 root values 逐欄判定 current 警示；名冊修正有效後自動解除，來源歷史保持不變。
  - `domains/case_import/hcm_resubmission.py` — HCM review 欄位與正式 root targets 的限定映射。
  - `subsystems/case_import/hcm_resubmission_workflow.py`
    - `preview_skip`／`apply_skip` — 只對 current canonical review 的缺少不符合原因保存人工 disposition；沿用 review version、correction event／receipt／outbox，不寫入 Client／Order。
  - `infrastructure/mysql/hcm_resubmission_repository.py`
- entrypoints:
  - `api/routes/hcm_import.py` — 包含 current field review page／single-review readback。
    - `/hcm/reviews/{review_identity}/skip-missing-reject-reason/{preview|apply}` — 限定欄位的人工略過與 typed stale conflict。
  - `api/dependencies/hcm_import.py`
  - `api/schemas/hcm_import.py`
  - `ui_react/src/api/case_import/hcm_workbook_schemas.ts`
  - `ui_react/src/api/case_import/hcm_resubmission_client.ts`
    - `loadCurrentHcmReviewsForCases` — 以既有 current review 分頁查詢讀取指定案件的最新欄位問題；支援取消，不寫入或重新判定問題是否解除。

## Dependencies
- outbound: `clients/client-profile/profile-change` — current 欄位警示沿用 Client Profile 正式驗證與名冊允許值；Query 不呼叫 writer。
- outbound: `orders` — HCM reconciliation 只透過 Case Import typed boundary 補入已授權 Orders facts。
- inbound: `case-import/case-import` — authenticated HCM workbook intake。

## Contracts
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — canonical payload exact replay 與 idempotency mismatch。
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — HCM Current workbook policy 與 Case Import ownership。

## Verification
- test_root: `tests/domains/case-import/subsystems/case-import/modules/hcm-current-workbook-import/`

## Provenance
- HCM Current workbook 與 Case Import ownership — `architecture_declared` — `17_External_Integration_LINE_Access正式規格.md`。
- implementation、entrypoint 與 replay flow — `source_observed` — current repository。

## Change triggers
Reconcile when HCM Current workbook contract、source fingerprint、replay/idempotency、entrypoint、reconciliation boundary 或 test root 改變。
