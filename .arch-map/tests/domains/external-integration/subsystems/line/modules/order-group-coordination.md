module: order-group-coordination
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/order-group-coordination.md
layout_status: custom_current
test_root: tests/domains/external-integration/subsystems/line/modules/order-group-coordination/
ui_integration_root: ui_react/src/tests/domains/external-integration/subsystems/line/integration/

# Owned verification
- `contract/test_order_group_commands.py` — 手機空白／換行、格式錯誤與舊指令提示、設定不邀請、網址更新不重綁、權限／核銷 gate、保存失敗回滾路由及 provider 前失效工作取消。
- 同一 `contract/test_order_group_workspace.py` 保護工會 LINE 尚未建群 Query：只列正式已核銷的未結案無群組案件、server 分頁、身分授權、已綁定／沖正後移出及零 mutation。
- `contract/test_order_group_workspace.py` — 執行唯讀 SQL 與 HTTP 查詢，保護 server 分頁、字面案件搜尋、canonical 身分、目前指派與綁定後加入狀況、跨來源事件鍵、資料最小化及零 mutation。
- UI integration `line_order_group_workbench.test.tsx` — 保護精簡清單、查詢邊界、延遲回應、明細／歷程分離、失敗及空值呈現，不提供網頁綁定或發送入口。
- Existing `domain/test_line_order_group_stage6.py`, `domain/test_line_media_group_domain.py`, `subsystems/test_line_order_group_numbered_api.py`, `infrastructure/test_line_mysql_repositories.py` 的既有群組 oracle 維持原位與原語意。
