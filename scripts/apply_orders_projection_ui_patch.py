"""Temporarily apply exact React projection edits on the working branch."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


TARGET_PATHS = (
    "ui_react/src/pages/OrdersPage.tsx",
    "ui_react/src/pages/OrderTrackerPage.tsx",
    "ui_react/src/tests/orders_page_real_data.test.tsx",
    "ui_react/src/tests/order_tracker_real_data.test.tsx",
)


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


def patch_order_tracker_tests() -> None:
    path = Path("ui_react/src/tests/order_tracker_real_data.test.tsx")

    replace_once(
        path,
        "    stagePage.items[0].sop_steps[1].status = 'in_progress';\n"
        "    stagePage.items[0].sop_steps[2].status = 'blocked';",
        "    stagePage.items[0].sop_steps[1].status = 'in_progress';\n"
        "    stagePage.items[0].current_sop_step = 2;\n"
        "    stagePage.items[0].sop_steps[2].status = 'blocked';",
    )
    replace_once(
        path,
        "  it('isolates incomplete historical imports as data correction instead of a business stage', async () => {",
        "  it('uses the server current SOP step when the current work is blocked', async () => {\n"
        "    const stagePage = buildOrdersStageProjectionFixture(realisticOrderSummaryPage);\n"
        "    const timeline = stagePage.items[0];\n"
        "    timeline.current_sop_step = 3;\n"
        "    timeline.sop_steps = timeline.sop_steps.map((step) => ({\n"
        "      ...step,\n"
        "      status: step.ordinal < 3 ? 'completed' as const : step.ordinal === 3 ? 'blocked' as const : 'not_started' as const,\n"
        "      blockers: step.ordinal === 3 ? [{ code: 'current_blocker', message: '目前作業受阻。' }] : [],\n"
        "    }));\n"
        "    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(stagePage);\n\n"
        "    render(<OrderTrackerPage />);\n"
        "    await screen.findByText('ORD-2026-0801');\n"
        "    fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0801/ }));\n\n"
        "    const current = document.querySelector('[data-surface-id=\"order-tracker.sop.step.3\"]');\n"
        "    expect(current).toHaveAttribute('data-status', 'blocked');\n"
        "    expect(current).toHaveAttribute('aria-current', 'step');\n"
        "    expect(screen.getByText('目前作業受阻。')).toBeInTheDocument();\n"
        "  });\n\n"
        "  it('renders cancelled orders outside both the seven stages and data-correction region', async () => {\n"
        "    const stagePage = buildOrdersStageProjectionFixture(realisticOrderSummaryPage);\n"
        "    const cancelled = stagePage.items[0];\n"
        "    cancelled.current_stage_code = null;\n"
        "    cancelled.current_sop_step = null;\n"
        "    cancelled.terminal_state = 'cancelled';\n"
        "    cancelled.stages = cancelled.stages.map((stage) => ({\n"
        "      ...stage,\n"
        "      status: 'unavailable' as const,\n"
        "      warnings: [{ code: 'order_cancelled', message: '訂單已取消。' }],\n"
        "      availability_reason: 'order_cancelled',\n"
        "    }));\n"
        "    cancelled.sop_steps = cancelled.sop_steps.map((step) => ({\n"
        "      ...step,\n"
        "      status: 'unavailable' as const,\n"
        "      warnings: [{ code: 'order_cancelled', message: '訂單已取消。' }],\n"
        "      availability_reason: 'order_cancelled',\n"
        "    }));\n"
        "    stagePage.stage_counts.intake_terms = 0;\n"
        "    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(stagePage);\n\n"
        "    render(<OrderTrackerPage />);\n\n"
        "    await screen.findByText('已取消訂單');\n"
        "    const cancelledRegion = document.querySelector('[data-surface-id=\"order-tracker.cancelled-orders\"]');\n"
        "    const correctionRegion = document.querySelector('[data-surface-id=\"order-tracker.unclassified-orders\"]');\n"
        "    expect(cancelledRegion).toHaveTextContent('ORD-2026-0801');\n"
        "    expect(cancelledRegion).toHaveTextContent('訂單已取消');\n"
        "    expect(correctionRegion).not.toHaveTextContent('ORD-2026-0801');\n"
        "    expect(screen.getByText(/已取消是終止狀態/)).toBeInTheDocument();\n"
        "  });\n\n"
        "  it('isolates incomplete historical imports as data correction instead of a business stage', async () => {",
    )
    replace_once(
        path,
        "    incomplete.current_stage_code = null;\n"
        "    incomplete.stages = incomplete.stages.map((stage, index) => ({",
        "    incomplete.current_stage_code = null;\n"
        "    incomplete.current_sop_step = null;\n"
        "    incomplete.stages = incomplete.stages.map((stage, index) => ({",
    )
    replace_once(
        path,
        "    secondStagePage.items[0].current_stage_code = 'matching_willingness';\n"
        "    secondStagePage.stage_counts.intake_terms = 0;",
        "    secondStagePage.items[0].current_stage_code = 'matching_willingness';\n"
        "    secondStagePage.items[0].current_sop_step = 2;\n"
        "    secondStagePage.stage_counts.intake_terms = 0;",
    )


def patch_orders_page_tests() -> None:
    path = Path("ui_react/src/tests/orders_page_real_data.test.tsx")

    replace_once(
        path,
        "  it('searches all lifecycle states and clears the old stage filter', async () => {",
        "  it('filters cancelled orders from the terminal projection instead of a business stage', async () => {\n"
        "    const stagePage = buildOrdersStageProjectionFixture(realisticOrderSummaryPage);\n"
        "    stagePage.items[0].current_stage_code = null;\n"
        "    stagePage.items[0].current_sop_step = null;\n"
        "    stagePage.items[0].terminal_state = 'cancelled';\n"
        "    stagePage.stage_counts.intake_terms = 0;\n"
        "    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(stagePage);\n\n"
        "    render(<OrdersPage />);\n"
        "    await screen.findByText('ORD-2026-0801');\n\n"
        "    const cancelledFilter = screen.getByRole('button', { name: '已取消 (1)' });\n"
        "    fireEvent.click(cancelledFilter);\n"
        "    expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument();\n"
        "    expect(screen.queryByText('ORD-2026-0802')).not.toBeInTheDocument();\n"
        "    expect(screen.getByRole('button', { name: '2. 媒合與徵詢意願 (0)' })).toBeEnabled();\n"
        "  });\n\n"
        "  it('searches all lifecycle states and clears the old stage filter', async () => {",
    )
    replace_once(
        path,
        "  it('deduplicates the StrictMode initial summary load to one transport request', async () => {",
        "  it('reloads cancellation facts when the shared workbench switches to another order', async () => {\n"
        "    const firstQuery = { ...cancellationQuery, lifecycle_status: '訂單取消' as const };\n"
        "    const secondQuery = { ...cancellationQuery, case_no: 'ORD-2026-0802', lifecycle_status: '洽談中' as const };\n"
        "    vi.mocked(orderCancellationClient.query).mockImplementation(async (caseNo) => (\n"
        "      caseNo === 'ORD-2026-0801' ? firstQuery : secondQuery\n"
        "    ));\n\n"
        "    render(<OrdersPage />);\n"
        "    await screen.findByText('ORD-2026-0801');\n"
        "    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);\n"
        "    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));\n"
        "    expect(await screen.findByText('🚫 不可再次取消')).toBeInTheDocument();\n"
        "    fireEvent.click(screen.getByRole('button', { name: 'Close drawer' }));\n\n"
        "    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[1]);\n"
        "    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));\n\n"
        "    await waitFor(() => expect(orderCancellationClient.query).toHaveBeenLastCalledWith(\n"
        "      'ORD-2026-0802',\n"
        "      expect.any(AbortSignal),\n"
        "    ));\n"
        "    expect(screen.getByText('🟢 允許取消試算')).toBeInTheDocument();\n"
        "    expect(screen.queryByText('🚫 不可再次取消')).not.toBeInTheDocument();\n"
        "  });\n\n"
        "  it('deduplicates the StrictMode initial summary load to one transport request', async () => {",
    )


def commit_and_push() -> None:
    head_ref = os.environ.get("GITHUB_HEAD_REF")
    if os.environ.get("GITHUB_ACTIONS") != "true" or not head_ref:
        return
    subprocess.run(["git", "add", *TARGET_PATHS], check=True)
    changed = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        check=False,
    ).returncode
    if changed == 0:
        return
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(
        [
            "git",
            "config",
            "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "fix(orders-ui): isolate cancellation and render terminal projection",
        ],
        check=True,
    )
    subprocess.run(["git", "push", "origin", f"HEAD:{head_ref}"], check=True)


def main() -> None:
    patch_orders_page()
    patch_order_tracker_page()
    patch_order_tracker_tests()
    patch_orders_page_tests()
    commit_and_push()


if __name__ == "__main__":
    main()
