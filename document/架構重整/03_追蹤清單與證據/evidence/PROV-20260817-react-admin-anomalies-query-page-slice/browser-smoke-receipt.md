# Anomalies Query Page-Slice Browser Smoke Receipt

Status: `PASS_QUERY_SUCCESS_PATH`（2026-08-17）。
Work Package: `PROV-20260817-react-admin-anomalies-query-page-slice`

使用者完成真password→TOTP；Integration Owner只使用同一volatile Session與既有DB GET，未讀取或記錄
credential、TOTP、token或cookie。

## Required manual evidence

After the user signs in through the existing two-step account → TOTP flow, open `http://127.0.0.1:5173/#anomalies`
and record only sanitized Network/DOM evidence:

1. mount sends one anomaly list GET and one warning-task GET;
2. opening an anomaly card sends one detail GET, and opening a warning sends one referral GET;
3. closing/switching the Drawer aborts or discards stale responses;
4. the DOM shows server-backed values or explicit unavailable text;
5. Claim, Resolve, Recovery and Warning transition controls are native disabled;
6. no POST/PUT/PATCH/DELETE is sent.

Fresh evidence：list與warning tasks各一個GET 200，DOM顯示100 anomalies、2 warning tasks；開啟Drawer後
detail GET 200，開啟HCM-FIELD-002後referral GET 200並顯示owner_preview_apply referral。Claim／Resolve／
Recovery／transition皆native disabled；驗收視窗0 POST/PUT/PATCH/DELETE。Focused 78 tests覆蓋empty/error/
abort/stale。結論：`query-real-data-validated`。
