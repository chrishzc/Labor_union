import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const drawerSource = readFileSync(
  resolve(process.cwd(), 'src/components/OrderWorkbenchV2Drawer.tsx'),
  'utf8',
);

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
});
