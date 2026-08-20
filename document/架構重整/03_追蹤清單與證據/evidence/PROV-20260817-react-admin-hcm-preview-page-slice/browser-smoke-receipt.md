# HCM Preview page-slice browser smoke receipt

Status: `NOT_REQUIRED_BY_HUMAN_DECISION`

This execution did not have an authenticated real Chrome session or a user-selected sanitized `.xlsx` available through the browser-control boundary. No dev token, mocked Network response, direct DB query, old screenshot, component fixture or prior Phase 4A-P receipt was substituted.

## Evidence still required

1. Real account/password Challenge followed by six-digit TOTP verification.
2. `#data-import` page with all six cards visible.
3. Drawer open and file selection producing zero HCM requests.
4. Exactly one `POST /api/v1/case-import/hcm/workbooks/preview` after explicit click, with multipart key `workbook`.
5. Sanitized response six-field aggregate matched to DOM digest／fingerprint／counts.
6. Row-detail unavailable slot visible; HCM Apply and other five cards native disabled.
7. Same-name/different-bytes selection clears prior DOM and does not auto-POST.
8. Apply clicks and disabled-card clicks create zero follow-up request.
9. Reload／expired memory session does not anonymously send HCM Preview.

2026-08-17使用者明確裁決不需要合成／真xlsx Preview browser gate；本receipt停止等待，不冒充PASS。
Successor改驗「本次新增訂單＋問題清單」GET→DOM，Apply仍另案。
