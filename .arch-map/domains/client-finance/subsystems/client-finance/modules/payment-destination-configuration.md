# Module: payment-destination-configuration

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
2026-11-02 依使用者明確裁決完整退役。沒有 current runtime、UI、Query／Preview／Apply 或帳戶資料用途；單案虛擬帳號不屬此舊設定。此節點只定位不可改寫的歷史 migration 與退役驗收，不再宣告維護功能。

## Implementation
- `db/schema_parts/1029_client_payment_destination_configuration.sql` — immutable historical release evidence only; fresh compact omits all three owned tables.

## Contracts
- `.arch-map/requirements/04_Client_Finance_Domain.md` §8 retirement decision.
- `.arch-map/requirements/19_Global_Entry_Point_Governance.md` — 舊帳戶維護的 GET／Preview／Apply 已從路由與 OpenAPI 移除（文件契約，非執行環境驗證）。
- Physical retirement adapter belongs to Global migration local-database-fresh-reset.

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/payment-destination-configuration/contract/`
- API absence and immutable historical-schema replay evidence only; removed writer/unit/UI expectations do not remain current requirements.
