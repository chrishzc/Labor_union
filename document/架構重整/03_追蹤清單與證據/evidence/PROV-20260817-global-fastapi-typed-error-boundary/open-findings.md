# Global FastAPI Typed Error Boundary Open Findings

| ID | Finding | Status | Closure |
|---|---|---|---|
| GERR-01 | request correlation唯一值與既有typed payload correlation無損要求衝突 | RESOLVED | exact核准response-only correlation rebase；真typed route tests通過 |
| GERR-02 | `mfa_enrollment_required` legacy detail含敏感challenge資料 | RESOLVED | strict allowlist只輸出核准code/message/retryable；secret/provisioning negative test通過 |
| GERR-03 | 部分`detail.error`缺required fields或category非正式enum | RESOLVED | strict mismatch後使用status-based redacted fallback |
| GERR-04 | React transport有寬鬆`any`／unsafe cast | RESOLVED | strict Zod nested decoder與negative matrix通過 |
| GERR-05 | MasterLayout有2個既有Fast Refresh lint warnings | OPEN_OUT_OF_SCOPE | Shell owner處理；Global lint exit 0，不在本包越界修改 |
| GERR-06 | Vite production bundle大於500kB advisory | OPEN_OUT_OF_SCOPE | Performance/page code-splitting owner後續處理；build exit 0 |

Global boundary已完成。依逐頁精簡遷移裁決，它只在page實際依賴此contract時成為前置，不再阻擋所有
existing typed GET query slice。
