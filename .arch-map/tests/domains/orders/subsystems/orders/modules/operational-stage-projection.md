module: operational-stage-projection
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/operational-stage-projection.md
test_root: ui_react/src/tests/domains/orders/subsystems/orders/modules/operational-stage-projection/

# Owned verification
- 訂單狀態分類、正式 current owner 階段篩選、完整分頁及部分失敗隔離。
- 完成與取消案件不呈現十三階段導覽，歷史 evidence 與正式派案分開呈現。
