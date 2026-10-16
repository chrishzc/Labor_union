module: order-group-coordination
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/order-group-coordination.md
layout_status: custom_current
test_root: tests/domains/external-integration/subsystems/line/modules/order-group-coordination/
ui_integration_root: ui_react/src/tests/domains/external-integration/subsystems/line/integration/

# Owned verification
- `contract/test_order_group_workspace.py` — 執行唯讀 SQL 與 HTTP 查詢，保護 server 分頁、字面案件搜尋、canonical 身分、目前指派與綁定後加入狀況、跨來源事件鍵、資料最小化及零 mutation。
- UI integration `line_order_group_workbench.test.tsx` — 保護精簡清單、查詢邊界、延遲回應、明細／歷程分離、失敗及空值呈現，不提供網頁綁定或發送入口。
- Existing `domain/test_line_order_group_stage6.py`, `domain/test_line_media_group_domain.py`, `subsystems/test_line_order_group_numbered_api.py`, `infrastructure/test_line_mysql_repositories.py` 的既有群組 oracle 維持原位與原語意。
