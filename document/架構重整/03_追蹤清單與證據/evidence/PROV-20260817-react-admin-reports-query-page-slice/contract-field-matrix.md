# Reports Query Page-Slice Contract Matrix

Status: frozen-local-candidate（2026-08-17）

| Boundary | Strict public data | Disposition |
|---|---|---|
| Quarterly GET | year、quarter、generated/source metadata、two partitions、masked rows、server aggregates | wired |
| Annual GET | year、quarter null、same strict redacted view | wired |
| Weekly summary | no approved typed query | unavailable／0 GET |
| Weekly active/hours | no approved typed query | unavailable／0 GET |
| All export routes | binary XLSX | native disabled／0 GET |

JSON row只允許case/eligibility/service facts、server amounts與masked employer/staff/identity/address；full PII與`xlsx_bytes`禁止response/DOM。

