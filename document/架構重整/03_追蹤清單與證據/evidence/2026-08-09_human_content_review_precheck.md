# Human Content Review Precheck

## Scope and result

This is a machine-assisted precheck, not a replacement for the required human content review.
It records the material semantic conflicts adjudicated in the attachment index.

| Attachment | Current content | Conflict or decision required |
|---|---|---|
| `LINE (1).pptx` | LINE automation, order-status tracking, Excel-to-MySQL import, a Streamlit-to-React path, and Agent-driven data modification. | Decide which requirements remain product commitments. The formal baseline keeps Streamlit as a thin adapter, requires typed backend commands, and does not authorize an agent to modify business data. |
| `月子媒合流程圖.canvas` | Direct database updates, fixed message automation, private LINE groups, electronic-signature invitation, and timing rules. | Decide each external provider, message, timing rule, and direct-write flow. These are not evidence of a current public contract. |
| `帳務.xlsx` | Historical bank-statement and database examples, including payment amounts. | Preserve as format/historical evidence only unless a business owner explicitly confirms each rule as current; it must not override the Client Finance / Staff Payables formal model. |
| `資料庫來源表.xlsx` | HCM, staff, insurance, and BeClass source columns, including personal data and subsidy-refund instructions. | Confirm provenance, retention, lawful processing, and canonical identity mapping. It is a source-format record, not a schema or field-authority SSOT. |
| `系統異常警示中心規格書.docx` | A draft that references retired `services/finance_alert_*` modules and keeps several unimplemented or pending business rules. | Reconcile against the Anomalies formal specification and current typed routes before any claim of coverage. The draft cannot be treated as the current implementation record. |
| `服務人員契約.xlsx` | A service-agreement output template with a visible `#VALUE!` formula result in its sampled contract-total cell. | Confirm legal wording, contract issuer, signature flow, required data fields, and formula ownership. The template alone cannot create an external contract API. |
| `週報.xlsx` | Historical operational / subsidy reporting, manually maintained status values, and mixed date representations. | Confirm statutory reporting requirements, retention, reporting owner, and whether this is only an output template rather than a write model. |
| `資料庫原始資料瀏覽_頁面欄位開放權限建議表.xlsx` | Legacy proposal for direct data-browser field editing, based on obsolete page and service references. | Reconcile against Access Control: the formal baseline prohibits bypassing owning-domain commands through a generic data browser. |

## Required human adjudication

For each row, record `covered`, `conflict`, `historical`, or `out-of-scope`, the
formal specification / decision that governs it, and any required retirement or
implementation work. Only then may the attachment index and the formal-spec
decision matrix remove their human-review markers.
