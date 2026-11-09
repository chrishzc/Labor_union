import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState, type ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UnsavedChangesProvider, useUnsavedNavigation } from '../../../../../../components/UnsavedChanges';
import { AccountingParametersPage, initialPricingPolicy } from '../../../../../../pages/AccountingParametersPage';
import { SubsidyPeriodWorkbench } from '../../../../../../components/SubsidyPeriodWorkbench';
import { accountingPricingClient, type PricingCatalog } from '../../../../../../api/client_finance/accounting_pricing_client';
import { subsidyPeriodClient } from '../../../../../../api/government_subsidy/period_reconciliation_client';

function Navigation({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(true);
  const { requestLeave } = useUnsavedNavigation();
  return <><button onClick={() => requestLeave(() => setOpen(false))}>離開帳務頁</button>{open ? children : <p>已離開帳務頁</p>}</>;
}
function mount(children: ReactNode) { render(<UnsavedChangesProvider><Navigation>{children}</Navigation></UnsavedChangesProvider>); }
async function leaveAndSave() {
  fireEvent.click(screen.getByRole('button', { name: '離開帳務頁' }));
  const dialog = await screen.findByRole('dialog', {name:'尚有未儲存的變更'});
  const save = within(dialog).getByRole('button', { name: '儲存變更並離開' });
  expect(save).toBeEnabled(); fireEvent.click(save);
}
afterEach(() => vi.restoreAllMocks());

describe('financial forms share direct save and protected navigation', () => {
  it('saves a policy version with an empty reason before leaving', async () => {
    let catalog: PricingCatalog = { revision: 0, versions: [] };
    vi.spyOn(accountingPricingClient, 'catalog').mockImplementation(async () => structuredClone(catalog));
    const save = vi.spyOn(accountingPricingClient, 'savePolicy').mockImplementation(async (policy, revision, reason) => {
      catalog = { revision: revision + 1, versions: [{ revision: revision + 1, policy, actor: 'synthetic', reason }] };
      return { revision: revision + 1 };
    });
    mount(<AccountingParametersPage />);
    fireEvent.change(await screen.findByLabelText('補助市民 客戶用盡後時薪'), { target: { value: '310' } });
    expect(screen.getByLabelText('變更說明（選填）')).not.toBeRequired();
    await leaveAndSave(); await screen.findByText('已離開帳務頁');
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ effective_on: initialPricingPolicy().effective_on }), 0, '', expect.any(String));
  });

  it('saves a confirmed exact whole-period receipt before leaving', async () => {
    vi.spyOn(subsidyPeriodClient, 'query').mockImplementation(async period => ({ period, version: 1, label: 'synthetic period', lines: [{ case_no: 'synthetic-case', service_end_date: '2026-01-20', amount_ntd: 6000, unavailable_reason: null }], total_ntd: 6000, coverage: [], blocked_cases: [], recorded_lines: [], changed_cases: [], can_reconcile: true }));
    vi.spyOn(subsidyPeriodClient, 'bankRows').mockResolvedValue([{ id: 2, paid_on: '2026-06-01', amount_ntd: 6000 }]);
    const apply = vi.spyOn(subsidyPeriodClient, 'difference').mockResolvedValue({} as Awaited<ReturnType<typeof subsidyPeriodClient.difference>>);
    mount(<SubsidyPeriodWorkbench onOpenCase={() => {}} />);
    await screen.findByText('synthetic period');
    fireEvent.change(screen.getByLabelText('已匯入銀行對帳單的政府款項'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('checkbox', {name:'我已核對款項、金額與處理方式'}));
    await leaveAndSave(); await screen.findByText('已離開帳務頁');
    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledWith(expect.objectContaining({action:'initial_receipt',bank_row_id:2,handling:'exact'}));
  });
});
