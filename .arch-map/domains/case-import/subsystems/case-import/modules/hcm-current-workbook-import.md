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
  - `domains/case_import/hcm_resubmission.py` — current review 與歷史 correction evidence 所需的正式 root 映射及 readback facts；沒有工作簿修正候選命令。
  - `subsystems/case_import/hcm_resubmission_workflow.py` — 只保留 Query／skip Preview／Apply；工作簿修正 API、parser、命令與專用 adapters 已退役。
    - `preview_skip`／`apply_skip` — 對 current canonical review 任一未解決欄位逐筆保存人工 disposition；沿用 review version、correction event／receipt／outbox，不寫入 Client／Order。原缺少原因限定入口保留。
  - `infrastructure/mysql/hcm_resubmission_repository.py` — 問題 Query、人工略過、歷史事件／收據；不再提供 Client／Orders mutation。
  - `subsystems/case_import/hcm_resubmission_outbox_consumer.py` — 保留既有及人工略過 committed events 的 fresh-root 驗證與投遞。
- entrypoints:
  - `api/routes/hcm_import.py` — 包含 current field review page／single-review readback。
    - `/hcm/reviews/{review_identity}/skip-missing-reject-reason/{preview|apply}` — 限定欄位的人工略過與 typed stale conflict。
    - `/hcm/reviews/{review_identity}/skip-field/{preview|apply}` — current 缺漏、格式錯誤及未支援欄位均可逐欄略過；新 review 不沿用舊 disposition。
  - `api/dependencies/hcm_import.py`
  - `api/schemas/hcm_import.py`
  - `ui_react/src/api/case_import/hcm_workbook_schemas.ts`
  - `ui_react/src/api/case_import/hcm_resubmission_client.ts`
    - current review `can_correct=false`／`unavailable_reason=hcm_workbook_correction_retired`；讀取問題不影響 Client Profile／Orders 編輯。
    - `loadCurrentHcmReviewsForCases` — 以既有 current review 分頁查詢讀取指定案件的最新欄位問題；支援取消，不寫入或重新判定問題是否解除。

## Dependencies
- outbound: `clients/client-profile/profile-change` — current 欄位警示沿用 Client Profile 正式驗證與名冊允許值；Query 不呼叫 writer。
- outbound: `orders` — HCM reconciliation 只透過 Case Import typed boundary 補入已授權 Orders facts。
- inbound: `case-import/case-import` — authenticated HCM workbook intake。

## Contracts
- HCM 只有姓名、身分資格、報名時間、預計服務日期、希望服務天數、服務時間、服務方式錯誤才觸發 partial intake／待補件；其他錯誤僅警示並照常建立完整案件。Preview／Apply 最低建案資格均為可用案件編號。電話使用 Client-owned 手機／市話格式與正規化。
- HCM `縣市` 為參考欄位：缺漏／非清單值不產生警示或補件理由，不單獨觸發 partial intake；沿用既有正規化。current review Query 忽略歷史縣市警示，不改寫來源、歷史紀錄或既有訂單狀態。
- HCM 管理註記後的原始空白表頭欄正規化為 optional `email`，映射至 Client-owned `clients.email`；空白／缺欄可匯入，非法非空值形成去敏欄位警示及 NULL 主檔值。BeClass email 不互填，既有案件不重匯覆寫。
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — canonical payload exact replay 與 idempotency mismatch。
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — HCM Current workbook policy 與 Case Import ownership。

## Verification
- test_root: `tests/domains/case-import/subsystems/case-import/modules/hcm-current-workbook-import/`

## Provenance
- HCM Current workbook 與 Case Import ownership — `architecture_declared` — `17_External_Integration_LINE_Access正式規格.md`。
- implementation、entrypoint 與 replay flow — `source_observed` — current repository。

## Change triggers
Reconcile when HCM correction retirement、current review／skip contract、HCM Current workbook contract、source fingerprint、replay/idempotency、entrypoint、reconciliation boundary 或 test root 改變。
