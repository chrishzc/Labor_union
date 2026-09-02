"""Temporarily apply exact React projection edits on the working branch."""

from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0 and new in text:
        return
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_orders_page() -> None:
    path = Path("ui_react/src/pages/OrdersPage.tsx")

    replace_once(
        path,
        "    setNormalFlowRestartedCaseNo(null);\n"
        "    setCancellationDays([]);",
        "    setNormalFlowRestartedCaseNo(null);\n"
        "    setCancellationQuery(null);\n"
        "    setCancellationDays([]);",
    )
    replace_once(
        path,
        "    } else if (tab === 'cancellation') {\n"
        "      if (cancellationQuery === null) {\n"
        "        void loadCancellationTabQueries(activeOrder);\n"
        "      }",
        "    } else if (tab === 'cancellation') {\n"
        "      if (cancellationQuery === null || cancellationQuery.case_no !== activeOrder.id) {\n"
        "        void loadCancellationTabQueries(activeOrder);\n"
        "      }",
    )
    replace_once(
        path,
        "  const previewCancellation = async () => {\n"
        "    if (!cancelOrder || !cancellationQuery) return;",
        "  const previewCancellation = async () => {\n"
        "    if (!cancelOrder || !cancellationQuery || cancellationQuery.case_no !== cancelOrder.id) return;",
    )
    replace_once(
        path,
        "  const allItems = pageData?.items || [];\n"
        "  const filteredOrders = selectedStage === '全部'\n"
        "    ? allItems\n"
        "    : allItems.filter((order) => stageIndex.get(order.id)?.current_stage_code === selectedStage);",
        "  const orderClassification = (timeline: OrderOperationalTimeline | undefined): WorkflowStage | null => (\n"
        "    timeline?.terminal_state === 'cancelled'\n"
        "      ? 'cancelled'\n"
        "      : timeline?.current_stage_code ?? null\n"
        "  );\n"
        "  const allItems = pageData?.items || [];\n"
        "  const filteredOrders = selectedStage === '全部'\n"
        "    ? allItems\n"
        "    : allItems.filter((order) => orderClassification(stageIndex.get(order.id)) === selectedStage);",
    )
    replace_once(
        path,
        "              ? [...stageIndex.values()].filter((timeline) => timeline.current_stage_code === filter.stage).length",
        "              ? [...stageIndex.values()].filter((timeline) => orderClassification(timeline) === filter.stage).length",
    )


def patch_order_tracker_page() -> None:
    path = Path("ui_react/src/pages/OrderTrackerPage.tsx")

    replace_once(
        path,
        "function currentStageLabel(timeline: OrderOperationalTimelinePage['items'][number]): string {\n"
        "  if (!timeline.current_stage_code) return '待判定';",
        "function currentStageLabel(timeline: OrderOperationalTimelinePage['items'][number]): string {\n"
        "  if (timeline.terminal_state === 'cancelled') return '訂單已取消';\n"
        "  if (!timeline.current_stage_code) return '待判定';",
    )
    replace_once(
        path,
        "  if (!timeline) return fallback;\n"
        "  if (!timeline.current_stage_code) {",
        "  if (!timeline) return fallback;\n"
        "  if (timeline.terminal_state === 'cancelled') {\n"
        "    return '訂單已取消；不再屬於七階段進行中工作。';\n"
        "  }\n"
        "  if (!timeline.current_stage_code) {",
    )
    replace_once(
        path,
        "  const selectedCurrentStepOrdinal = selectedTimeline?.sop_steps.find(\n"
        "    (step) => step.status === 'in_progress',\n"
        "  )?.ordinal;",
        "  const selectedCurrentStepOrdinal = selectedTimeline?.current_sop_step ?? undefined;",
    )
    replace_once(
        path,
        "  const visibleTrackerOrders = resolvedData?.unclassifiedOrders.filter(matchesSearch) ?? [];\n"
        "  const visibleStageCount = (stageId: string): number => visibleTrackerOrders.filter(",
        "  const visibleTrackerOrders = resolvedData?.unclassifiedOrders.filter(matchesSearch) ?? [];\n"
        "  const visibleCancelledOrders = stageProjectionState.kind === 'ready'\n"
        "    ? visibleTrackerOrders.filter((order) => (\n"
        "      stageProjectionState.byCaseNo.get(order.id)?.terminal_state === 'cancelled'\n"
        "    ))\n"
        "    : [];\n"
        "  const visibleUnclassifiedOrders = stageProjectionState.kind === 'ready'\n"
        "    ? visibleTrackerOrders.filter((order) => {\n"
        "      const timeline = stageProjectionState.byCaseNo.get(order.id);\n"
        "      return timeline?.terminal_state === null && !timeline.current_stage_code;\n"
        "    })\n"
        "    : visibleTrackerOrders;\n"
        "  const visibleStageCount = (stageId: string): number => visibleTrackerOrders.filter(",
    )
    replace_once(
        path,
        "        : !timeline\n"
        "          ? { title: '階段資料缺失', summary: '此案件未包含於目前的七階段投影，請重新載入摘要。' }\n"
        "          : timeline.current_stage_code\n"
        "            ? { title: '目前卡點／待辦', summary: currentStageSummary(timeline, order.waitingText) }\n"
        "            : { title: '資料完整性異常', summary: currentStageSummary(timeline, order.waitingText) };",
        "        : !timeline\n"
        "          ? { title: '階段資料缺失', summary: '此案件未包含於目前的七階段投影，請重新載入摘要。' }\n"
        "          : timeline.terminal_state === 'cancelled'\n"
        "            ? { title: '訂單已取消', summary: currentStageSummary(timeline, order.waitingText) }\n"
        "            : timeline.current_stage_code\n"
        "              ? { title: '目前卡點／待辦', summary: currentStageSummary(timeline, order.waitingText) }\n"
        "              : { title: '資料完整性異常', summary: currentStageSummary(timeline, order.waitingText) };",
    )
    replace_once(
        path,
        "          <section className=\"tracker-unclassified\" data-surface-id=\"order-tracker.unclassified-orders\">",
        "          {stageProjectionState.kind === 'ready' && visibleCancelledOrders.length > 0 && (\n"
        "            <section className=\"tracker-unclassified\" data-surface-id=\"order-tracker.cancelled-orders\">\n"
        "              <div className=\"tracker-section-heading\">\n"
        "                <div>\n"
        "                  <h2>已取消訂單</h2>\n"
        "                  <p>已取消是終止狀態，不屬於七階段進行中工作。</p>\n"
        "                </div>\n"
        "                <span className=\"tracker-loaded-count\">{visibleCancelledOrders.length} 筆</span>\n"
        "              </div>\n"
        "              <div className=\"pipeline-cards-grid\">\n"
        "                {visibleCancelledOrders.map(renderTrackerCard)}\n"
        "              </div>\n"
        "            </section>\n"
        "          )}\n\n"
        "          <section className=\"tracker-unclassified\" data-surface-id=\"order-tracker.unclassified-orders\">",
    )
    replace_once(
        path,
        "                {visibleTrackerOrders\n"
        "                  .filter(\n"
        "                    (order) =>\n"
        "                      (stageProjectionState.kind !== 'ready' ||\n"
        "                        !stageProjectionState.byCaseNo.get(order.id)?.current_stage_code)\n"
        "                  )\n"
        "                  .map(renderTrackerCard)}",
        "                {visibleUnclassifiedOrders.map(renderTrackerCard)}",
    )


def main() -> None:
    patch_orders_page()
    patch_order_tracker_page()


if __name__ == "__main__":
    main()
