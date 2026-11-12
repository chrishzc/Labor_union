/**
 * File: accounting_parameters_components.test.tsx
 * Description: 驗證帳務參數卡、內嵌列與右側調整抽屜（含原住民 80h／350 元預設）行為。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AccountingParametersCard } from '../../../../../../../components/AccountingParametersCard';
import { AccountingParametersBar } from '../../../../../../../components/AccountingParametersBar';
import { AccountingParametersDrawer } from '../../../../../../../components/AccountingParametersDrawer';
import { accountingPricingClient, type CasePricing } from '../../../../../../../api/client_finance/accounting_pricing_client';
import { historicalServiceAccountingClient } from '../../../../../../../api/orders/historical_service_accounting_client';

vi.mock('../../../../../../../api/orders/historical_service_accounting_client', () => ({
  historicalServiceAccountingClient: { query: vi.fn(), preview: vi.fn(), apply: vi.fn() },
}));

vi.mock('../../../../../../../api/client_finance/accounting_pricing_client', async importOriginal => {
  const actual = await importOriginal<typeof import('../../../../../../../api/client_finance/accounting_pricing_client')>();
  return {
    ...actual,
    accountingPricingClient: {
      catalog: vi.fn(),
      savePolicy: vi.fn(),
      queryCase: vi.fn(),
      previewCase: vi.fn(),
      applyCase: vi.fn(),
    },
  };
});

const mockPricing: CasePricing = {
  case_no: '115000088',
  revision: 1,
  source: 'policy',
  terms: {
    identity_name: '補助市民',
    rule: 'citizen',
    subsidy_hours: 120,
    client: { covered: 350, excess: 300 },
    payroll: { covered: 350, excess: 450 },
  },
  impact: {
    covered_hours: 120,
    excess_hours: 40,
    client_amount: 12000,
    staff_covered_amount: 54000,
    staff_excess_amount: 18000,
    staff_total_amount: 72000,
    subsidy_amount: 42000,
    subsidy_return_amount: 0,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AccountingParametersCard component', () => {
  it('keeps missing pricing unknown and uses only the supplied formal amounts', async () => {
    vi.mocked(accountingPricingClient.queryCase).mockRejectedValue(new Error('source unavailable'));
    render(<AccountingParametersCard caseNo="115000088" customerAmountNtd={12000}
      staffAmountNtd={30000} onOpenEdit={vi.fn()} />);
    await waitFor(() => expect(accountingPricingClient.queryCase).toHaveBeenCalledWith('115000088'));
    expect(screen.getByRole('status')).toHaveTextContent('計價依據待確認');
    expect(screen.getByText('待確認（補助時數待確認）')).toBeVisible();
    expect(screen.queryByText(/160h|0h|\$250|\$300/)).not.toBeInTheDocument();
    expect(screen.getByText(/客戶應繳 NT\$ 12,000/)).toBeVisible();
    expect(screen.getByText(/月嫂基準應付 NT\$ 30,000/)).toBeVisible();
  });

  it('renders twin rates, subsidy identity, hourly rates and triggers onOpenEdit', () => {
    const handleOpenEdit = vi.fn();
    render(
      <AccountingParametersCard
        caseNo="115000088"
        pricing={mockPricing}
        multiBirthCount="雙胞胎"
        customerAmountNtd={12000}
        staffAmountNtd={72000}
        onOpenEdit={handleOpenEdit}
      />
    );

    expect(screen.getByText('雙胞胎 (2位·加成)')).toBeInTheDocument();
    expect(screen.getByText('補助市民 (120h)')).toBeInTheDocument();
    expect(screen.getByText('$300')).toBeInTheDocument();
    expect(screen.getByText('$450')).toBeInTheDocument();
    expect(screen.getByText(/客戶應繳 NT\$ 12,000/)).toBeInTheDocument();
    expect(screen.getByText(/月嫂基準應付 NT\$ 72,000/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /調整帳務參數/ }));
    expect(handleOpenEdit).toHaveBeenCalledTimes(1);
  });
});

describe('AccountingParametersBar component', () => {
  it('renders inline parameters and opens drawer', () => {
    const handleOpenEdit = vi.fn();
    render(
      <AccountingParametersBar
        caseNo="115000088"
        pricing={mockPricing}
        multiBirthCount="雙胞胎"
        customerStage2Due={12000}
        onOpenEdit={handleOpenEdit}
      />
    );

    expect(screen.getByText('雙胞胎')).toBeInTheDocument();
    expect(screen.getByText('補助市民 (120h)')).toBeInTheDocument();
    expect(screen.getByText('$300/h')).toBeInTheDocument();
    expect(screen.getByText('NT$ 12,000')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /原地更正參數/ }));
    expect(handleOpenEdit).toHaveBeenCalledTimes(1);
  });
});

describe('AccountingParametersDrawer component', () => {
  it('loads case pricing, toggles twins, adjusts rates and applies changes', async () => {
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(structuredClone(mockPricing));
    vi.mocked(accountingPricingClient.applyCase).mockResolvedValue({ revision: 2 });
    const handleCommitted = vi.fn();
    const handleClose = vi.fn();

    render(
      <AccountingParametersDrawer
        caseNo="115000088"
        isOpen={true}
        onClose={handleClose}
        onCommitted={handleCommitted}
        initialPricing={mockPricing}
        initialMultiBirthCount="雙胞胎"
      />
    );

    expect(await screen.findByText('調整本案帳務參數 · 115000088')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '調整歷史訂單服務天數' })).not.toBeInTheDocument();

    // Toggle to single birth
    const singleBtn = screen.getByRole('button', { name: /單胞胎/ });
    fireEvent.click(singleBtn);

    // Enter a reason and submit
    const reasonInput = screen.getByLabelText(/調整原因說明/);
    fireEvent.change(reasonInput, { target: { value: '更正為單胞胎計算' } });

    const submitBtn = screen.getByRole('button', { name: /儲存本案帳務參數並重算/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(accountingPricingClient.applyCase).toHaveBeenCalledTimes(1);
      expect(handleCommitted).toHaveBeenCalledTimes(1);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });
  });

  it('saves historical days for the same case and refreshes reconciliation', async () => {
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(mockPricing);
    const facts = {
      case_no: mockPricing.case_no,
      lifecycle_status: '歷史訂單－服務完成',
      lifecycle_version: 1,
      adoption_receipt_id: 1,
      adoption_source_identity: 'source',
      historical_day_revision: 0,
      client_finance_version: 1,
      payroll_version: 1,
      contracted_service_days: 20,
      service_hours_per_day: 8,
      contractual_floor_fee_ntd: 0,
      client_identity_status: '一般市民',
      assignments: [{
        assignment_identity: 'assignment-1', staff_id: 1, staff_name: '測試月嫂',
        policy_version: '1', policy_kind: 'citizen' as const, hourly_rate_ntd: 300,
      }],
    };
    const preview = {
      facts,
      total_actual_service_days: 18,
      total_actual_service_hours: '144',
      historical_floor_fee_ntd: 0,
      historical_double_pay_days: 0 as const,
      historical_double_pay_hours: '0' as const,
      allocations: [],
      payroll_assignments: [],
      staff_obligation_amount_ntd: 43_200,
      client_obligation_amount_ntd: 43_200,
      client_service_receivable_ntd: 43_200,
      client_subsidy_hours: 0,
      client_self_pay_service_hours: 144,
      preview_fingerprint: 'a'.repeat(64),
    };
    vi.mocked(historicalServiceAccountingClient.query).mockResolvedValue(facts);
    vi.mocked(historicalServiceAccountingClient.preview).mockResolvedValue(preview);
    vi.mocked(historicalServiceAccountingClient.apply).mockResolvedValue({
      case_no: facts.case_no,
      resulting_historical_day_revision: 1,
      resulting_client_finance_version: 1,
      resulting_payroll_version: 1,
      total_actual_service_days: 18,
      client_obligation_amount_ntd: 43_200,
      staff_obligation_amount_ntd: 43_200,
      preview_fingerprint: preview.preview_fingerprint,
      replayed: false,
    });
    const onCommitted = vi.fn();
    render(<AccountingParametersDrawer caseNo={facts.case_no} isOpen canEditHistoricalDays
      onClose={vi.fn()} onCommitted={onCommitted} />);

    fireEvent.click(screen.getByRole('button', { name: '調整歷史訂單服務天數' }));
    fireEvent.change(await screen.findByRole('spinbutton', { name: /實際服務天數/ }), { target: { value: '18' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存服務天數' }));

    await screen.findByText(/實際服務天數已儲存/);
    const days = [{ assignment_identity: 'assignment-1', staff_id: 1, actual_service_days: 18 }];
    expect(historicalServiceAccountingClient.query).toHaveBeenCalledWith(facts.case_no);
    expect(historicalServiceAccountingClient.preview).toHaveBeenCalledWith(facts.case_no, days);
    expect(historicalServiceAccountingClient.apply).toHaveBeenCalledWith(preview, days, '');
    expect(accountingPricingClient.applyCase).not.toHaveBeenCalled();
    expect(onCommitted).toHaveBeenCalledTimes(1);
  });

  it('switches indigenous identity preset to 80h cap and 350 covered rate', async () => {
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(structuredClone(mockPricing));
    render(
      <AccountingParametersDrawer
        caseNo="115000088"
        isOpen={true}
        onClose={vi.fn()}
        onCommitted={vi.fn()}
        initialPricing={mockPricing}
        initialMultiBirthCount={null}
      />
    );
    const select = await screen.findByLabelText(/補助身分等級/);
    fireEvent.change(select, { target: { value: 'indigenous' } });
    expect(screen.getByLabelText(/補助時數上限/)).toHaveValue(80);
    expect(screen.getByLabelText('補助範圍內客戶時薪')).toHaveValue(350);
    expect(screen.getByText(/原住民市民（預設上限 80h · 350 元）/)).toBeInTheDocument();
  });
});
