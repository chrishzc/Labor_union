import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState, type ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UnsavedChangesProvider, useUnsavedNavigation } from '../../../../../../components/UnsavedChanges';
import { AccountingParametersPage, initialPricingPolicy } from '../../../../../../pages/AccountingParametersPage';
import { PaymentDestinationConfigurationPanel } from '../../../../../../components/PaymentDestinationConfigurationPanel';
import { FinanceStatementArchive } from '../../../../../../components/FinanceStatementArchive';
import { SubsidyPeriodWorkbench } from '../../../../../../components/SubsidyPeriodWorkbench';
import { accountingPricingClient, type PricingCatalog } from '../../../../../../api/client_finance/accounting_pricing_client';
import { paymentDestinationClient } from '../../../../../../api/client_finance/payment_destination_client';
import { financeAccountingClient } from '../../../../../../api/finance_import/finance_accounting_client';
import { subsidyPeriodClient } from '../../../../../../api/government_subsidy/period_reconciliation_client';
import { ApiHttpError, ApiNetworkError } from '../../../../../../api/shared/typed_errors';

function Navigation({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(true);
  const { requestLeave } = useUnsavedNavigation();
  return <><button onClick={() => requestLeave(() => setOpen(false))}>離開帳務頁</button>{open ? children : <p>已離開帳務頁</p>}</>;
}
function mount(children: ReactNode) { render(<UnsavedChangesProvider><Navigation>{children}</Navigation></UnsavedChangesProvider>); }
async function leaveAndSave() {
  fireEvent.click(screen.getByRole('button', { name: '離開帳務頁' }));
  const dialog = await screen.findByRole('dialog');
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
    fireEvent.change(await screen.findByLabelText('社福 客戶用盡後時薪'), { target: { value: '310' } });
    expect(screen.getByLabelText('變更說明（選填）')).not.toBeRequired();
    await leaveAndSave(); await screen.findByText('已離開帳務頁');
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ effective_on: initialPricingPolicy().effective_on }), 0, '', expect.any(String));
  });

  it('keeps the original account command locked after uncertain save and reuses its key', async () => {
    const before = { configured: true, account_display: 'synthetic-old', revision: 1 };
    vi.spyOn(paymentDestinationClient, 'query').mockResolvedValueOnce(before).mockResolvedValue({ ...before, account_display: 'synthetic-new', revision: 2 });
    vi.spyOn(paymentDestinationClient, 'preview').mockResolvedValue({ current: before, candidate_account_display: 'synthetic-new', expected_revision: 1, preview_fingerprint: 'a'.repeat(64) });
    const apply = vi.spyOn(paymentDestinationClient, 'apply').mockRejectedValueOnce(new ApiNetworkError()).mockResolvedValue({ account_display: 'synthetic-new', resulting_revision: 2, preview_fingerprint: 'a'.repeat(64) });
    mount(<PaymentDestinationConfigurationPanel reload={0} />);
    fireEvent.change(await screen.findByLabelText('工會／代收付帳戶'), { target: { value: 'synthetic-new' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存帳戶' }));
    await screen.findByRole('button', { name: '重試原儲存' });
    fireEvent.click(screen.getByRole('button', { name: '離開帳務頁' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('button', { name: '捨棄變更並離開' })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole('button', { name: '繼續編輯' }));
    fireEvent.click(screen.getByRole('button', { name: '重試原儲存' }));
    await screen.findByText('工會／代收付帳戶已更新。');
    expect(apply.mock.calls[0][2]).toBe(apply.mock.calls[1][2]);
    fireEvent.click(screen.getByRole('button', { name: '離開帳務頁' }));
    await screen.findByText('已離開帳務頁');
  });

  it('preserves an invalid manual statement and only leaves after a confirmed save', async () => {
    const manual = vi.spyOn(financeAccountingClient, 'manual').mockRejectedValueOnce(new ApiHttpError(422, 'invalid', 'invalid')).mockResolvedValue({ identity: 'manual:1', saved_count: 1, excluded_count: 0 });
    mount(<FinanceStatementArchive />);
    fireEvent.change(screen.getByLabelText('交易日（必填）'), { target: { value: '2026-10-29' } });
    fireEvent.change(screen.getByLabelText('支出'), { target: { value: '100' } });
    fireEvent.change(screen.getByLabelText('備註'), { target: { value: 'synthetic transfer' } });
    await leaveAndSave();
    await screen.findByRole('alert');
    expect(screen.queryByText('已離開帳務頁')).not.toBeInTheDocument();
    expect(screen.getByLabelText('支出')).toHaveValue('100');
    const dialog = screen.getByRole('dialog');
    await waitFor(() => expect(within(dialog).getByRole('button', { name: '儲存變更並離開' })).toBeEnabled());
    fireEvent.click(within(dialog).getByRole('button', { name: '儲存變更並離開' }));
    await screen.findByText('已離開帳務頁'); expect(manual).toHaveBeenCalledTimes(2);
  });

  it('requires an explicit duplicate decision and clears its draft after saving', async () => {
    const duplicate = vi.spyOn(financeAccountingClient, 'duplicate').mockResolvedValue({ identity: 'manual:1', saved_count: 0, excluded_count: 1 });
    mount(<FinanceStatementArchive />);
    fireEvent.change(screen.getByLabelText('後到的銀行明細識別'), { target: { value: 'bank:2' } });
    fireEvent.change(screen.getByLabelText('保留的既存明細識別'), { target: { value: 'manual:1' } });
    fireEvent.click(screen.getByLabelText('已確認兩者為同一筆交易，保留既存明細'));
    await leaveAndSave(); await screen.findByText('已離開帳務頁');
    expect(duplicate).toHaveBeenCalledWith('bank:2', 'manual:1', expect.any(String));
  });

  it('saves an exact whole-period receipt before leaving and rejects amount mismatch', async () => {
    vi.spyOn(subsidyPeriodClient, 'query').mockImplementation(async period => ({ period, version: 1, label: 'synthetic period', lines: [{ case_no: 'synthetic-case', service_end_date: '2026-01-20', amount_ntd: 6000, unavailable_reason: null }], total_ntd: 6000, coverage: [], blocked_cases: [], recorded_lines: [], changed_cases: [], can_reconcile: true }));
    vi.spyOn(subsidyPeriodClient, 'bankRows').mockResolvedValue([{ id: 2, paid_on: '2026-06-01', amount_ntd: 6000 }]);
    const reconcile = vi.spyOn(subsidyPeriodClient, 'reconcile').mockResolvedValue({ receipt_id: 1 });
    mount(<SubsidyPeriodWorkbench onOpenCase={() => {}} />);
    await screen.findByText(/本期補助總額/);
    fireEvent.change(screen.getByLabelText('政府銀行款項'), { target: { value: '2' } });
    await leaveAndSave(); await screen.findByText('已離開帳務頁');
    expect(reconcile).toHaveBeenCalledTimes(1);
    expect(reconcile.mock.calls[0][1]).toBe(2);
  });
});
