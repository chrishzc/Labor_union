# Module: delivery-provider-transport

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
定義已提交 LINE delivery task 共用的 typed provider outcome，並將 Push／Reply 請求轉接至 LINE Messaging API。此模組不建立 delivery task、不選擇業務收件者，也不在 webhook transaction 執行 provider effect；Reply token 僅供 committed worker 的一次性短效投遞使用。

## Implementation
- primary: `subsystems/line/delivery_contracts.py`
- provider adapter: `infrastructure/line/messaging_api_adapter.py`

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — committed delivery、Reply 優先與 uncertain outcome 禁止 Push fallback。
- `subsystems/line/ports.py::LineMessagingProviderPort` — worker 與 provider adapter 間的 typed boundary。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/delivery-provider-transport/contract/`

## Change triggers
Reconcile when provider outcome typing、Push／Reply transport、Reply token handling或provider adapter focused test root changes。
