module: operational-stage-projection
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/operational-stage-projection.md
test_root: ui_react/src/tests/domains/orders/subsystems/orders/modules/operational-stage-projection/
test_root: ui_react/src/tests/order_workbench_v2_candidate_pool_refresh.test.tsx
test_root: ui_react/src/tests/order_workbench_v2_mutation_refresh.test.tsx
test_root: ui_react/src/tests/order_workbench_v2_terms_mutation.test.tsx

# Owned verification
- 訂單狀態分類、正式 current owner 階段篩選、完整分頁及部分失敗隔離；scope 外 terminal 資料漂移不得使目前工作台失效，scope 內無效投影仍須 fail-closed。
- 完成與取消案件不呈現十三階段導覽，歷史 evidence 與正式派案分開呈現。
