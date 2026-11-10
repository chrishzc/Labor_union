import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AccountingParametersCard } from '../../../../../../../components/AccountingParametersCard';
import { AccountingParametersBar } from '../../../../../../../components/AccountingParametersBar';
import { AccountingParametersDrawer } from '../../../../../../../components/AccountingParametersDrawer';
import { accountingPricingClient, type CasePricing } from '../../../../../../../api/client_finance/accounting_pricing_client';

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
});
