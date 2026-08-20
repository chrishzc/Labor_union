# Form Management capability／owner contract matrix

> Evidence only；不構成production、API、文件刪除或entry cutover授權。來源為current active規格與live source。

| Capability | Current implementation/evidence | Candidate owner | Current disposition | 必須裁決 |
|---|---|---|---|---|
| Case context | Orders typed `/form-management-context` | Orders | `KEEP` | React是否只在Orders drawer使用，避免複製client |
| Cross-case statistics | typed query混Orders/Staff/Subsidy/receivable | Reporting coordinator＋各data owner | `DECISION_REQUIRED` | 指標定義、時間窗、PII、是否獨立entry |
| General template catalog | local JSON read/write/delete | 未定 | `REPLACE` | template id/version/digest/lifecycle、publisher、retention |
| Contract template/document | local JSON/HTML與直接下載 | Contract Signing | `REPLACE` | approved template reference、immutable document version、download auth/audit |
| Questionnaire/resume | raw table/column bindings，可含敏感欄位 | Staff / Case Import（未定） | `DECISION_REQUIRED` | root facts、redaction、version、附件/文件owner |
| Placeholder registry | arbitrary DB table/column binding | 各owning Domain提供semantic fields | `RETIRE` raw binding | semantic placeholder IDs、type、masking、missing-data policy |
| Template preview | local renderer | Template owner + secure renderer | `ADAPT` | preview 0 write、escaping/sandbox/CSP、MIME/digest |
| Publish/update | local file overwrite | Template owner | `REPLACE` | CAS/fingerprint/idempotency/replay/receipt |
| Delete | physical local file delete | Template owner | `RETIRE` physical delete by default | retire lifecycle、legal retention、restore procedure |
| Export/download | local PII HTML/download | Document owner | `REPLACE` | capability、masked/full variants、audit、expiry、watermark（如需） |
| React entry identity | none; partial surfaces in Orders/Staff/Reports | Entry Governance | `DECISION_REQUIRED` | dedicated `#form-management`或one-to-many group與rollback |

## Fail-closed rules

- 未凍結owner/SSOT的row不能進production write set。
- raw table/column、raw JSON、local filename或UI label不能成為public identity。
- Contract Signing的正式文件不能由local template file冒充。
- owner未決前Streamlit仍為current rollback entry；React相關mutation/export native disabled。
- 若任何方案需要新persistence/schema，另立DB Work Package並執行完整DB gates。
