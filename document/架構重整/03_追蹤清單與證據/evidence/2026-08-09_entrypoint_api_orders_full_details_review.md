---
entry_id: "api:PUT /api/v1/orders/{case_no}/full-details"
status: retired_410
verified_at: 2026-08-09
---

# Orders full-details API entry review

## Business decision

舊管理端若想以一個 generic full-details request 直接修改案件，會混合客戶姓名、生命周期與其他
不同 owner 的資料，不能再執行。此 entry 因舊 API consumer 仍可能呼叫而保留 HTTP boundary，
但只回 typed `410 Gone`。

## Replacement

管理員若只需更正客戶姓名，改由 Orders typed
`POST /api/v1/orders/{case_no}/client-name/preview`，確認 preview fingerprint 後呼叫
`POST /api/v1/orders/{case_no}/client-name/apply`。其他欄位必須前往各自 owning Domain 的 typed
Preview／Apply，不再接受 generic full-details writer。

## Verification

`tests/test_order_full_details_entry_retirement.py` 驗證 status、retirement code 與兩個 replacement
path；route 不進入 generic mutation implementation。
