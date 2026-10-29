import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { accountingPricingClient, type CasePricing, type PricingCatalog } from '../../../../../../../api/client_finance/accounting_pricing_client';
import { ApiHttpError, ApiNetworkError } from '../../../../../../../api/shared/typed_errors';
import { AccountingParametersPage } from '../../../../../../../pages/AccountingParametersPage';
import { CasePricingAdjustmentPanel } from '../../../../../../../components/CasePricingAdjustmentPanel';
import { UnsavedChangesProvider, useUnsavedNavigation } from '../../../../../../../components/UnsavedChanges';

vi.mock('../../../../../../../api/client_finance/accounting_pricing_client', async importOriginal => {
  const actual = await importOriginal<typeof import('../../../../../../../api/client_finance/accounting_pricing_client')>();
  return { ...actual, accountingPricingClient: { catalog: vi.fn(), savePolicy: vi.fn(), queryCase: vi.fn(), previewCase: vi.fn(), applyCase: vi.fn() } };
});

const current: CasePricing = { case_no: 'synthetic-case', revision: 0, source: 'policy',
  terms: { identity_name: '社福', rule: 'social', subsidy_hours: 120,
    client: { covered: 350, excess: 350 }, payroll: { covered: 350, excess: 350 } },
  impact: { covered_hours: 120, excess_hours: 40, client_amount: 14000, staff_covered_amount: 42000,
    staff_excess_amount: 14000, staff_total_amount: 56000, subsidy_amount: 42000, subsidy_return_amount: 0 } };

beforeEach(() => { vi.clearAllMocks(); });

describe('Standalone accounting parameter policy', () => {
  it('keeps independent excess rates, inherits new identities and confirms saved version by readback', async () => {
    let catalog: PricingCatalog = { revision: 0, versions: [] };
    vi.mocked(accountingPricingClient.catalog).mockImplementation(async () => structuredClone(catalog));
    vi.mocked(accountingPricingClient.savePolicy).mockImplementation(async (policy, revision, reason) => {
      catalog = { revision: revision + 1, versions: [{ revision: revision + 1, policy, actor: 'synthetic-admin', reason }] };
      return { revision: revision + 1 };
    });
    render(<UnsavedChangesProvider><AccountingParametersPage /></UnsavedChangesProvider>);
    const excess = await screen.findByLabelText('社福 客戶用盡後時薪');
    fireEvent.change(excess, { target: { value: '300' } });
    fireEvent.change(screen.getByLabelText('社福 月嫂用盡後時薪'), { target: { value: '310' } });
    expect(screen.getByLabelText('社福 客戶補助內時薪')).toHaveValue(350);
    expect(screen.getByLabelText('社福 月嫂補助內時薪')).toHaveValue(350);
    fireEvent.change(screen.getByLabelText('新增身分名稱'), { target: { value: '新增身分' } });
    fireEvent.change(screen.getByLabelText('沿用身分規則'), { target: { value: 'social' } });
    fireEvent.click(screen.getByRole('button', { name: '新增身分' }));
    expect(screen.getByLabelText('新增身分 客戶用盡後時薪')).toHaveValue(300);
    expect(screen.getByLabelText('變更說明（選填）')).not.toBeRequired();
    fireEvent.click(screen.getByRole('button', { name: '儲存新版本' }));
    await screen.findByText('版本 1 已儲存；依生效日期套用新案件。');
    expect(accountingPricingClient.savePolicy).toHaveBeenCalledTimes(1);
    const saved = vi.mocked(accountingPricingClient.savePolicy).mock.calls[0][0];
    expect(saved.identities.find(item => item.identity_name === '社福')?.payroll).toEqual({ covered: 350, excess: 310 });
    expect(screen.queryByRole('tab', { name: '收款帳戶' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '版本紀錄' }));
    await screen.findByText('synthetic-admin');
  });
});

describe('Subsidy pricing protections', () => {
  it.each(['citizen', 'social'] as const)('keeps historical unequal %s rates readable and blocks save until equal', async rule => {
    const legacy: CasePricing = { ...current, terms: { ...current.terms, rule, client: { covered: 301, excess: 330 }, payroll: { covered: 300, excess: 310 } } };
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(legacy);
    vi.mocked(accountingPricingClient.applyCase).mockImplementation(async (_case, terms) => {
      vi.mocked(accountingPricingClient.queryCase).mockResolvedValue({ ...legacy, revision: 1, terms });
      return { revision: 1 };
    });
    render(<UnsavedChangesProvider><CasePricingAdjustmentPanel caseNo="synthetic-case" revision={0} onCommitted={vi.fn(async () => {})} onStateChange={vi.fn()} /></UnsavedChangesProvider>);
    await screen.findByText('補助範圍內的客戶時薪與月嫂時薪必須相等，才能向政府報帳。');
    const save = screen.getByRole('button', { name: '儲存本案調整' });
    fireEvent.change(screen.getByLabelText('客戶用盡後時薪'), { target: { value: '340' } });
    expect(save).toBeDisabled();
    fireEvent.click(save);
    expect(accountingPricingClient.applyCase).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('月嫂補助內時薪'), { target: { value: '301' } });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await screen.findByText('本案人工計價已儲存並確認；帳務已同步。');
    const terms = vi.mocked(accountingPricingClient.applyCase).mock.calls[0][1];
    expect(terms.client).toEqual({ covered: 301, excess: 340 });
    expect(terms.payroll).toEqual({ covered: 301, excess: 310 });
    expect(accountingPricingClient.previewCase).not.toHaveBeenCalled();
  });

  it('shows disabled zero non-citizen subsidy fields and keeps self-pay editable', async () => {
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue({ ...current, terms: { ...current.terms, identity_name: '非市民', rule: 'non_citizen', subsidy_hours: 0, client: { covered: 0, excess: 330 }, payroll: { covered: 0, excess: 310 } } });
    render(<UnsavedChangesProvider><CasePricingAdjustmentPanel caseNo="synthetic-case" revision={0} onCommitted={vi.fn(async () => {})} onStateChange={vi.fn()} /></UnsavedChangesProvider>);
    for (const label of ['補助時數上限（小時）', '客戶補助內時薪', '月嫂補助內時薪']) {
      const field = await screen.findByLabelText(label);
      expect(field).toHaveValue(0); expect(field).toBeDisabled();
    }
    expect(screen.getByLabelText('客戶用盡後時薪')).toHaveValue(330);
    expect(screen.getByLabelText('月嫂用盡後時薪')).toHaveValue(310);
    fireEvent.change(screen.getByLabelText('客戶用盡後時薪'), { target: { value: '340' } });
    expect(screen.getByRole('button', { name: '儲存本案調整' })).toBeEnabled();
  });

  it('protects identity and twins policy settings, with zero non-citizen covered rates', async () => {
    vi.mocked(accountingPricingClient.catalog).mockResolvedValue({ revision: 0, versions: [] });
    render(<UnsavedChangesProvider><AccountingParametersPage /></UnsavedChangesProvider>);
    expect(await screen.findByLabelText('非市民 客戶補助內時薪')).toHaveValue(0);
    expect(screen.getByLabelText('非市民 月嫂補助內時薪')).toHaveValue(0);
    expect(screen.getByLabelText('非市民 客戶用盡後時薪')).toHaveValue(320);
    fireEvent.change(screen.getByLabelText('社福 客戶補助內時薪'), { target: { value: '351' } });
    const save = screen.getByRole('button', { name: '儲存新版本' });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('社福 月嫂補助內時薪'), { target: { value: '351' } });
    expect(save).toBeEnabled();
    fireEvent.change(screen.getByLabelText('雙胞胎客戶補助內時薪'), { target: { value: '451' } });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('雙胞胎月嫂補助內時薪'), { target: { value: '451' } });
    expect(save).toBeEnabled();
    expect(accountingPricingClient.savePolicy).not.toHaveBeenCalled();
  });
});

describe('Client registry case pricing section', () => {
  it('saves directly with a blank reason and preserves one command key after an uncertain apply', async () => {
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(current);
    vi.mocked(accountingPricingClient.previewCase).mockImplementation(async (_case, terms) => ({ current, candidate: terms,
      before: current.impact, after: { ...current.impact, client_amount: 12000 }, preview_fingerprint: 'a'.repeat(64) }));
    vi.mocked(accountingPricingClient.applyCase).mockRejectedValueOnce(new ApiNetworkError()).mockImplementationOnce(async (_case, terms) => {
      vi.mocked(accountingPricingClient.queryCase).mockResolvedValue({ ...current, revision: 1, source: 'manual', terms });
      return { revision: 1 };
    });
    const committed = vi.fn(async () => {});
    render(<UnsavedChangesProvider><CasePricingAdjustmentPanel caseNo="synthetic-case" revision={0} onCommitted={committed} onStateChange={vi.fn()} /></UnsavedChangesProvider>);
    await screen.findByLabelText('客戶用盡後時薪');
    expect(screen.getByRole('button', { name: '儲存本案調整' })).toBeDisabled();
    expect(screen.queryByLabelText('補助給付方式')).not.toBeInTheDocument();
    expect(document.querySelector('input[type=date]')).toBeNull();
    fireEvent.change(screen.getByLabelText('客戶用盡後時薪'), { target: { value: '300' } });
    expect(screen.queryByText('影響預覽')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '預覽影響' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('調整原因（選填）')).not.toBeRequired();
    fireEvent.click(screen.getByRole('button', { name: '儲存本案調整' }));
    expect(accountingPricingClient.previewCase).not.toHaveBeenCalled();
    await screen.findByRole('button', { name: '重試原操作與回讀' });
    expect(screen.getByLabelText('客戶用盡後時薪')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '重試原操作與回讀' }));
    await screen.findByText('本案人工計價已儲存並確認；帳務已同步。');
    const calls = vi.mocked(accountingPricingClient.applyCase).mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[0][3]).toBe('');
    expect(calls[0][4]).toEqual(calls[1][4]);
    expect(committed).toHaveBeenCalledTimes(1);
  });

  function NavigationHarness() {
    const [open, setOpen] = useState(true);
    const { requestLeave } = useUnsavedNavigation();
    return <><button onClick={() => requestLeave(() => setOpen(false))}>關閉案件</button>{open
      ? <CasePricingAdjustmentPanel caseNo="synthetic-case" revision={0} onCommitted={async () => {}} onStateChange={() => {}} />
      : <p>已離開案件</p>}</>;
  }

  it('protects close and browser unload, and saves before leaving without a preview', async () => {
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(current);
    vi.mocked(accountingPricingClient.applyCase).mockImplementation(async (_case, terms) => {
      vi.mocked(accountingPricingClient.queryCase).mockResolvedValue({ ...current, revision: 1, source: 'manual', terms });
      return { revision: 1 };
    });
    render(<UnsavedChangesProvider><NavigationHarness /></UnsavedChangesProvider>);
    fireEvent.change(await screen.findByLabelText('月嫂用盡後時薪'), { target: { value: '310' } });
    const unload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '關閉案件' }));
    let dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('350')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '繼續編輯' }));
    expect(screen.getByLabelText('月嫂用盡後時薪')).toHaveValue(310);
    fireEvent.click(screen.getByRole('button', { name: '關閉案件' }));
    dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: '儲存變更並離開' }));
    await screen.findByText('已離開案件');
    expect(accountingPricingClient.previewCase).not.toHaveBeenCalled();
    expect(accountingPricingClient.applyCase).toHaveBeenCalledTimes(1);
    const cleanUnload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(cleanUnload);
    expect(cleanUnload.defaultPrevented).toBe(false);
  });

  it('keeps a rejected save on screen and allows explicit discard without another write', async () => {
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(current);
    vi.mocked(accountingPricingClient.applyCase).mockRejectedValue(new ApiHttpError(409, 'case_pricing_stale', 'changed'));
    render(<UnsavedChangesProvider><NavigationHarness /></UnsavedChangesProvider>);
    fireEvent.change(await screen.findByLabelText('客戶用盡後時薪'), { target: { value: '300' } });
    fireEvent.click(screen.getByRole('button', { name: '關閉案件' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: '儲存變更並離開' }));
    await screen.findByText('資料已變更，或涉及已核銷補助的更正；請重新查詢並核對。');
    await waitFor(() => expect(within(dialog).getByRole('button', { name: '捨棄變更並離開' })).toBeEnabled());
    expect(screen.queryByText('已離開案件')).not.toBeInTheDocument();
    expect(screen.getByLabelText('客戶用盡後時薪')).toHaveValue(300);
    fireEvent.click(within(dialog).getByRole('button', { name: '捨棄變更並離開' }));
    await screen.findByText('已離開案件');
    expect(accountingPricingClient.applyCase).toHaveBeenCalledTimes(1);
  });
});
