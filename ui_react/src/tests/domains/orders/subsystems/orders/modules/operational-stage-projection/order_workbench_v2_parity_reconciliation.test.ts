import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');

const drawerSource = source('src/components/OrderWorkbenchV2Drawer.tsx');
const appSource = source('src/App.tsx');
const layoutSource = source('src/components/MasterLayout.tsx');
const workbenchSource = source('src/pages/OrderWorkbenchV2Page.tsx');
const schedulingSource = source('src/pages/SchedulingPage.tsx');

describe('Order Workbench V2 parity reconciliation', () => {
  it('routes intake repair, historical restart, replacement, and accounting blockers through existing owner flows', () => {
    expect(drawerSource).toContain('<OrderIntakeRepairPanel');
    expect(drawerSource).toContain('aria-label="歷史訂單精算天數重啟"');
    expect(drawerSource).toContain('void restartHistoricalOrderIntoNormalFlow()');
    expect(drawerSource).toContain('historicalServiceAccountingClient.queryPrecisionRestart(caseNo)');
    expect(drawerSource).toContain('historicalServiceAccountingClient.previewPrecisionRestart(caseNo)');
    expect(drawerSource).toContain('historicalServiceAccountingClient.applyPrecisionRestart(');
    expect(drawerSource).toContain("observed.order_status !== '訂單成立'");
    expect(drawerSource).toContain('data-surface-id="orders.service-before-replacement.entry"');
    expect(drawerSource).toContain('<ServiceBeforeReplacementActions');
    expect(drawerSource).toContain("historicalAccounting.status === 'error'");
  });

  it('uses the workbench as the sole canonical order navigation after #148', () => {
    expect(appSource).toContain("'order-beta': 'order-workbench-v2'");
    expect(appSource).toContain("currentPage === 'order-workbench-v2' && <OrderWorkbenchV2Page />");
    expect(appSource).toContain("return 'order-workbench-v2'");
    expect(layoutSource).toContain("{ id: 'order-workbench-v2', icon: LayoutDashboard, label: '待辦看板'");
    expect(layoutSource).not.toContain("'order-tracker'");
    expect(layoutSource).not.toContain("'orders'");
    expect(appSource).not.toContain("currentPage === 'order-tracker'");
    expect(appSource).not.toContain("currentPage === 'orders'");
    expect(schedulingSource).toContain('#order-workbench-v2?case_no=');
    expect(schedulingSource).not.toContain('#orders?case_no=');
  });

  it('does not reintroduce the retired handcrafted contract-document presentation', () => {
    expect(drawerSource).toContain('<ContractExternalSigningActions');
    expect(workbenchSource).not.toContain('<OrderCaregiverContractPanel');
    expect(workbenchSource).not.toContain('<OrderClientContractPanel');
    expect(workbenchSource).not.toContain('契約草稿預覽（非正式）');
    expect(workbenchSource).not.toContain('contractDocView');
    expect(workbenchSource).not.toContain('contractDocFullscreen');
  });
});
