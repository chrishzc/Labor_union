module: client-subsidy-return-query
parent_subsystem: client-finance
architecture: ../../../../../../domains/client-finance/subsystems/client-finance/modules/client-subsidy-return-query.md
test_root: tests/domains/client-finance/subsystems/client-finance/modules/client-subsidy-return-query/

# Owned verification
- `test_subsidy_return_query.py` — 無退款義務仍可查、全補助／取消／已退款排除、凍結金額與正式帳務優先、日期與未知來源、搜尋分頁及 authenticated GET。
