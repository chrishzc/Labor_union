import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');

const drawerSource = source('src/components/OrderWorkbenchV2Drawer.tsx');
const appSource = source('src/App.tsx');
const layoutSource = source('src/components/MasterLayout.tsx');
const ordersPageSource = source('src/pages/OrdersPage.tsx');

describe('Order Workbench V2 parity reconciliation', () => {
  it('routes intake repair, historical restart, replacement, and accounting blockers through existing owner flows', () => {
    expect(drawerSource).toContain('<OrderIntakeRepairPanel');
    expect(drawerSource).toContain('onHistoricalRestartRequested={restartHistoricalOrderIntoNormalFlow}');
    expect(drawerSource).toContain('historicalServiceAccountingClient.queryPrecisionRestart(caseNo)');
    expect(drawerSource).toContain('historicalServiceAccountingClient.previewPrecisionRestart(caseNo)');
    expect(drawerSource).toContain('historicalServiceAccountingClient.applyPrecisionRestart(');
    expect(drawerSource).toContain("observed.order_status !== '訂單成立'");
    expect(drawerSource).toContain('data-surface-id="orders.service-before-replacement.entry"');
    expect(drawerSource).toContain('<ServiceBeforeReplacementActions');
    expect(drawerSource).toContain("historicalAccounting.status === 'error'");
  });

  it('uses the workbench as the canonical navigation entry while legacy routes remain for #148', () => {
    expect(appSource).toContain("'order-beta': 'order-workbench-v2'");
    expect(appSource).toContain("currentPage === 'order-workbench-v2' && <OrderWorkbenchV2Page />");
    expect(appSource).toContain("return 'order-workbench-v2'");
    expect(layoutSource).toContain("{ id: 'order-workbench-v2', icon: '📌', label: '待辦看板'");
    expect(layoutSource).toContain("item.id !== 'order-tracker' && item.id !== 'orders'");
    expect(appSource).toContain("currentPage === 'order-tracker' && <OrderTrackerPage />");
    expect(appSource).toContain("currentPage === 'orders' && <OrdersManagementPage />");
  });

  it('does not reintroduce the retired handcrafted contract-document presentation', () => {
    expect(ordersPageSource).toContain('<ContractExternalSigningActions');
    expect(ordersPageSource).not.toContain('契約草稿預覽（非正式）');
    expect(ordersPageSource).not.toContain('contractDocView');
    expect(ordersPageSource).not.toContain('contractDocFullscreen');
  });
});
