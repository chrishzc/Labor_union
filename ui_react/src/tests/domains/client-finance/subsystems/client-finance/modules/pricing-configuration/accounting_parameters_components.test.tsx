/**
 * File: accounting_parameters_components.test.tsx
 * Description: 驗證帳務參數卡、內嵌列與右側調整抽屜的正式計價來源及儲存行為。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AccountingParametersCard } from '../../../../../../../components/AccountingParametersCard';
import { AccountingParametersBar } from '../../../../../../../components/AccountingParametersBar';
import { AccountingParametersDrawer } from '../../../../../../../components/AccountingParametersDrawer';
import { accountingPricingClient, type CasePricing } from '../../../../../../../api/client_finance/accounting_pricing_client';
import { clientRegistryClient } from '../../../../../../../api/client_registry/client_registry_client';
import type { ClientRegistryDetail } from '../../../../../../../api/client_registry/client_registry_schemas';
import { historicalServiceAccountingClient } from '../../../../../../../api/orders/historical_service_accounting_client';
import { ApiHttpError, ApiTimeoutError } from '../../../../../../../api/shared/typed_errors';

vi.mock('../../../../../../../api/client_registry/client_registry_client', () => ({
  clientRegistryClient: { query: vi.fn(), preview: vi.fn(), apply: vi.fn() },
}));

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
    case_total_amount: 72000, union_income_amount: 0, staff_total_amount: 72000,
    subsidy_amount: 42000,
    subsidy_return_amount: 0,
  },
};

function registryBirthCount(value: '單胞胎' | '雙胞胎' | null, editable = true): ClientRegistryDetail {
  return {
    case_no: mockPricing.case_no,
    import_field_issues: [],
    client: {
      client_id: 1,
      version: 0,
      values: {
        name: null, gender: null, phone: null, city: null, address: null,
        residence_type: null, delivery_type: null, baby_info: null, notes: null,
      },
      field_capabilities: {},
    },
    beclass: {
      status: value === null ? 'unbound' : 'ready',
      record_id: value === null ? null : 1,
      source_kind: value === null ? null : 'admin_manual',
      version: value === null ? null : value === '雙胞胎' ? 8 : 7,
      values: value === null ? null : {
        name: null, email: null, phone: null, tel: null, ext: null, city: null,
        zip_code: null, address: null, admin_notes: null, multi_birth_count: value,
      },
      field_capabilities: value === null ? {} : {
        multi_birth_count: {
          owner: 'client_beclass', editable,
          reason: editable ? null : 'multi_birth_count_locked_after_service_start',
          options: ['單胞胎', '雙胞胎'],
        },
      },
    },
    order_information: { status: 'unbound', values: null, field_issues: {} },
    finance: { status: 'not_ready', code: null, values: null },
    order_terms: { status: 'not_ready', code: null, data: null, field_capabilities: {} },
  };
}

const twinChange = { multi_birth_count: '雙胞胎' } as const;
const birthFingerprint = 'b'.repeat(64);

function mockBirthCorrection() {
  vi.mocked(clientRegistryClient.query).mockResolvedValue(registryBirthCount('單胞胎'));
  vi.mocked(clientRegistryClient.preview).mockResolvedValue({
    owner: 'client_beclass', aggregate_identity: mockPricing.case_no, current_version: 7,
    before: { multi_birth_count: '單胞胎' }, after: twinChange, preview_fingerprint: birthFingerprint,
  });
  vi.mocked(clientRegistryClient.apply).mockResolvedValue({
    owner: 'client_beclass', aggregate_identity: mockPricing.case_no, resulting_version: 8,
    changed_fields: ['multi_birth_count'], preview_fingerprint: birthFingerprint,
    readback: twinChange, idempotency_key: 'birth-key', replayed: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(clientRegistryClient.query).mockResolvedValue(registryBirthCount(null));
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

    expect(screen.getByText('雙胞胎 (2位)')).toBeInTheDocument();
    expect(screen.getByText('補助市民 (120h)')).toBeInTheDocument();
    expect(screen.getByText('$300')).toBeInTheDocument();
    expect(screen.getByText('$450')).toBeInTheDocument();
    expect(screen.getByText(/客戶應繳 NT\$ 12,000/)).toBeInTheDocument();
    expect(screen.getByText(/月嫂基準應付 NT\$ 72,000/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /調整帳務參數/ }));
    expect(handleOpenEdit).toHaveBeenCalledTimes(1);
  });

  it('reads separate case total and union income from backend and preserves unknown income', () => {
    const pricing: CasePricing = { ...mockPricing, impact: {
      ...mockPricing.impact, case_total_amount: 5600, client_amount: 5600,
      staff_total_amount: 5120, union_income_amount: 480,
    } };
    const { rerender } = render(<AccountingParametersCard caseNo={pricing.case_no} pricing={pricing} onOpenEdit={vi.fn()} />);
    expect(screen.getByText(/案件總額 NT\$ 5,600 ｜ 工會收入 NT\$ 480/)).toBeVisible();
    expect(screen.getByText(/月嫂基準應付 NT\$ 5,120/)).toBeVisible();
    rerender(<AccountingParametersCard caseNo={pricing.case_no} pricing={{ ...pricing, impact: { ...pricing.impact, union_income_amount: null } }} onOpenEdit={vi.fn()} />);
    expect(screen.getByText(/工會收入 待確認/)).toBeVisible();
  });

  it('shows the registered singleton at a 450 hourly rate', () => {
    render(<AccountingParametersCard caseNo={mockPricing.case_no} pricing={mockPricing}
      multiBirthCount="單胞胎" onOpenEdit={vi.fn()} />);
    expect(screen.getByText(/單胞胎/)).toBeVisible();
    expect(screen.queryByText(/雙胞胎/)).not.toBeInTheDocument();
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

    fireEvent.click(screen.getByRole('button', { name: '更正本案計價參數' }));
    expect(handleOpenEdit).toHaveBeenCalledTimes(1);
  });

  it('uses the registered birth count even when the hourly rate is 450', () => {
    const { rerender } = render(<AccountingParametersBar caseNo={mockPricing.case_no}
      pricing={mockPricing} multiBirthCount="單胞胎" onOpenEdit={vi.fn()} />);
    expect(screen.getByText('單胞胎')).toBeVisible();
    expect(screen.queryByText('雙胞胎')).not.toBeInTheDocument();

    rerender(<AccountingParametersBar caseNo={mockPricing.case_no}
      pricing={mockPricing} multiBirthCount={null} onOpenEdit={vi.fn()} />);
    expect(screen.getByText(/胎數待確認/)).toBeVisible();
    expect(screen.queryByText(/單胞胎|雙胞胎/)).not.toBeInTheDocument();
  });
});

describe('AccountingParametersDrawer component', () => {
  it('confirms the BeClass change, saves the independent 420 rate and reopens as twins', async () => {
    mockBirthCorrection();
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(structuredClone(mockPricing));
    vi.mocked(accountingPricingClient.applyCase).mockResolvedValue({ revision: 2 });
    const handleCommitted = vi.fn();
    const handleClose = vi.fn();
    const props = { caseNo: mockPricing.case_no, onClose: handleClose, onCommitted: handleCommitted };
    const { rerender } = render(<AccountingParametersDrawer {...props} isOpen />);

    expect(await screen.findByRole('button', { name: /單胞胎/, pressed: true })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: /雙胞胎/ }));
    fireEvent.change(screen.getByLabelText('補助用盡後月嫂時薪'), { target: { value: '420' } });
    const reason = '更正雙胞胎並調整月嫂時薪';
    fireEvent.change(screen.getByLabelText(/調整原因說明/), { target: { value: reason } });
    fireEvent.click(screen.getByRole('button', { name: '儲存本案帳務參數並重算' }));

    const confirm = await screen.findByRole('button', { name: '確認胎數並儲存' });
    expect(clientRegistryClient.preview).toHaveBeenCalledWith(mockPricing.case_no, 'beclass', twinChange, 7);
    expect(clientRegistryClient.apply).not.toHaveBeenCalled();
    expect(accountingPricingClient.applyCase).not.toHaveBeenCalled();
    fireEvent.click(confirm);

    await waitFor(() => {
      expect(handleCommitted).toHaveBeenCalledTimes(1);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });
    expect(clientRegistryClient.apply).toHaveBeenCalledExactlyOnceWith(
      mockPricing.case_no, 'beclass', twinChange, 7, birthFingerprint, reason, expect.any(String),
    );
    const afterTerms = { ...mockPricing.terms, payroll: { ...mockPricing.terms.payroll, excess: 420 } };
    expect(accountingPricingClient.applyCase).toHaveBeenCalledExactlyOnceWith(
      mockPricing.case_no, afterTerms, mockPricing.revision, reason, expect.any(String),
    );
    expect(clientRegistryClient.apply).toHaveBeenCalledBefore(vi.mocked(accountingPricingClient.applyCase));

    rerender(<AccountingParametersDrawer {...props} isOpen={false} />);
    vi.mocked(clientRegistryClient.query).mockResolvedValue(registryBirthCount('雙胞胎'));
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue({
      ...mockPricing, revision: 2, source: 'manual', terms: afterTerms,
    });
    rerender(<AccountingParametersDrawer {...props} isOpen />);
    expect(await screen.findByRole('button', { name: /雙胞胎/, pressed: true })).toBeVisible();
    expect(screen.getByLabelText('補助用盡後月嫂時薪')).toHaveValue(420);
  });

  it('saves pre-service birth-only changes without creating a manual rate override', async () => {
    mockBirthCorrection();
    const initial = { ...mockPricing, terms: { ...mockPricing.terms, payroll: { covered: 350, excess: 305 } } };
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(initial);
    const handleClose = vi.fn();
    render(<AccountingParametersDrawer caseNo={mockPricing.case_no} isOpen
      onClose={handleClose} onCommitted={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /雙胞胎/ }));
    expect(screen.getByLabelText('補助用盡後月嫂時薪')).toHaveValue(305);
    fireEvent.click(screen.getByRole('button', { name: '儲存本案帳務參數並重算' }));
    fireEvent.click(await screen.findByRole('button', { name: '確認胎數並儲存' }));
    await waitFor(() => expect(handleClose).toHaveBeenCalledOnce());
    expect(clientRegistryClient.apply).toHaveBeenCalledOnce();
    expect(accountingPricingClient.applyCase).not.toHaveBeenCalled();
  });

  it('reads saved historical birth and pending accounting without an independent pricing write', async () => {
    mockBirthCorrection();
    const historical = (value: '單胞胎' | '雙胞胎'): ClientRegistryDetail => {
      const registered = registryBirthCount(value);
      return { ...registered, beclass: { ...registered.beclass, birth_count_correction_mode: 'historical_service_completed' } };
    };
    const pending = ['historical_pricing_birth_bound_policy_required'];
    const initial = { ...mockPricing, historical: true, terms: { ...mockPricing.terms, payroll: { covered: 350, excess: 305 } } };
    const reread = { ...initial, revision: 2, accounting_pending: pending };
    vi.mocked(clientRegistryClient.query).mockResolvedValueOnce(historical('單胞胎'))
      .mockRejectedValueOnce(new Error('formal read unavailable'))
      .mockResolvedValueOnce(historical('雙胞胎'));
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValueOnce(initial).mockResolvedValue(reread);
    vi.mocked(clientRegistryClient.preview).mockResolvedValueOnce({
      owner: 'client_beclass', aggregate_identity: mockPricing.case_no, current_version: 7,
      before: { multi_birth_count: '單胞胎' }, after: twinChange, preview_fingerprint: birthFingerprint,
      historical_impact: {
        client_updates: [], staff_updates: [], persons: [], client_delta: 0, subsidy_delta: 0, client_exempt: false, pending,
      },
    });
    vi.mocked(clientRegistryClient.apply).mockResolvedValueOnce({
      owner: 'client_beclass', aggregate_identity: mockPricing.case_no, resulting_version: 8,
      changed_fields: ['multi_birth_count'], preview_fingerprint: birthFingerprint,
      readback: twinChange, idempotency_key: 'birth-key', replayed: false, accounting_pending: pending,
    });
    const committed = vi.fn();
    render(<AccountingParametersDrawer caseNo={mockPricing.case_no} isOpen onClose={vi.fn()} onCommitted={committed} />);

    fireEvent.click(await screen.findByRole('button', { name: /雙胞胎/ }));
    expect(screen.getByLabelText('補助用盡後月嫂時薪')).toHaveValue(305);
    fireEvent.click(screen.getByRole('button', { name: '預覽歷史胎數更正' }));
    const confirm = await screen.findByRole('button', { name: '確認胎數並儲存' });
    expect(screen.getByRole('region', { name: '帳務影響' })).toHaveTextContent('缺少本案綁定的正式胎數費率');
    expect(clientRegistryClient.apply).not.toHaveBeenCalled();
    fireEvent.click(confirm);

    fireEvent.click(await screen.findByRole('button', { name: '重新讀取已儲存資料' }));
    expect(await screen.findByText('正式胎數現為雙胞胎。')).toBeVisible();
    expect(screen.getByText(/缺少本案綁定的正式胎數費率/)).toBeVisible();
    expect(clientRegistryClient.query).toHaveBeenCalledTimes(3);
    expect(clientRegistryClient.apply).toHaveBeenCalledOnce();
    expect(accountingPricingClient.applyCase).not.toHaveBeenCalled();
    expect(committed).toHaveBeenCalledOnce();
  });

  it('previews an already corrected twin and reads the confirmed payroll difference', async () => {
    mockBirthCorrection();
    const registered = registryBirthCount(twinChange.multi_birth_count);
    vi.mocked(clientRegistryClient.query).mockResolvedValue({
      ...registered, beclass: { ...registered.beclass, birth_count_correction_mode: 'historical_service_completed' },
    });
    const person = {
      assignment_identity: 'assignment:81', staff_id: 81, staff_name: 'Synthetic staff', hours: 320,
      before_amount: null, after_amount: 96000, delta: null,
      snapshot_hourly_rate: 300, effective_hourly_rate: 450, calculated_amount: 144000,
    };
    const confirmed = { ...person, before_amount: 96000, after_amount: 144000, delta: 48000 };
    const initial = { ...mockPricing, source: 'legacy' as const, historical: true, historical_payroll: [person] };
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValueOnce(initial)
      .mockResolvedValue({ ...initial, revision: 2, historical_payroll: [confirmed] });
    vi.mocked(clientRegistryClient.preview).mockResolvedValueOnce({
      owner: 'client_beclass', aggregate_identity: mockPricing.case_no, current_version: 7,
      before: twinChange, after: twinChange, preview_fingerprint: birthFingerprint,
      historical_impact: {
        client_updates: [], staff_updates: [], persons: [confirmed], client_delta: 0,
        subsidy_delta: 0, client_exempt: false, pending: [],
      },
    });
    render(<AccountingParametersDrawer caseNo={mockPricing.case_no} isOpen onClose={vi.fn()} onCommitted={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: '預覽雙胞胎薪資差額' }));
    expect(clientRegistryClient.preview).toHaveBeenCalledWith(mockPricing.case_no, 'beclass', twinChange, 7);
    fireEvent.click(await screen.findByRole('button', { name: '確認胎數並儲存' }));
    await waitFor(() => expect(screen.getByRole('table', { name: '歷史雙胞胎月嫂應付' })).toHaveTextContent('48,000'));
    expect(clientRegistryClient.apply).toHaveBeenCalledOnce();
    expect(accountingPricingClient.applyCase).not.toHaveBeenCalled();
  });

  it('confirms a historical manual rate separately with the pricing preview fingerprint', async () => {
    const initial = { ...mockPricing, historical: true };
    const terms = { ...initial.terms, payroll: { ...initial.terms.payroll, excess: 420 } };
    const fingerprint = 'c'.repeat(64);
    const registered = registryBirthCount('單胞胎');
    vi.mocked(clientRegistryClient.query).mockResolvedValue({
      ...registered, beclass: { ...registered.beclass, birth_count_correction_mode: 'historical_service_completed' },
    });
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValueOnce(initial)
      .mockResolvedValueOnce({ ...initial, revision: 2, terms });
    vi.mocked(accountingPricingClient.previewCase).mockResolvedValueOnce({
      current: initial, candidate: terms, before: initial.impact, after: initial.impact, preview_fingerprint: fingerprint,
      historical_plan: { client_updates: [], staff_updates: [], persons: [], client_delta: 0, subsidy_delta: 0, client_exempt: false, pending: [] },
    });
    vi.mocked(accountingPricingClient.applyCase).mockResolvedValueOnce({ revision: 2 });
    render(<AccountingParametersDrawer caseNo={initial.case_no} isOpen onClose={vi.fn()} onCommitted={vi.fn()} />);

    fireEvent.change(await screen.findByLabelText('補助用盡後月嫂時薪'), { target: { value: '420' } });
    expect(screen.getByRole('button', { name: /雙胞胎/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '預覽歷史計價更正' }));
    const confirm = await screen.findByRole('button', { name: '確認歷史計價更正' });
    expect(accountingPricingClient.applyCase).not.toHaveBeenCalled();
    fireEvent.click(confirm);

    expect(await screen.findByText('歷史計價更正已儲存。')).toBeVisible();
    expect(accountingPricingClient.applyCase).toHaveBeenCalledExactlyOnceWith(
      initial.case_no, terms, initial.revision, '', expect.any(String), fingerprint,
    );
    expect(clientRegistryClient.apply).not.toHaveBeenCalled();
  });

  it('retries only pricing after the confirmed BeClass correction has committed', async () => {
    mockBirthCorrection();
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(mockPricing);
    vi.mocked(accountingPricingClient.applyCase)
      .mockRejectedValueOnce(new ApiHttpError(422, 'pricing_invalid', '計價設定未儲存'))
      .mockResolvedValueOnce({ revision: 2 });
    const handleClose = vi.fn();
    render(<AccountingParametersDrawer caseNo={mockPricing.case_no} isOpen
      onClose={handleClose} onCommitted={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: /雙胞胎/ }));
    fireEvent.change(screen.getByLabelText('補助用盡後月嫂時薪'), { target: { value: '420' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存本案帳務參數並重算' }));
    fireEvent.click(await screen.findByRole('button', { name: '確認胎數並儲存' }));

    expect(await screen.findByText(/胎數已儲存為雙胞胎/)).toBeVisible();
    expect(handleClose).not.toHaveBeenCalled();
    expect(screen.getByLabelText('補助用盡後月嫂時薪')).toHaveValue(420);
    fireEvent.click(screen.getByRole('button', { name: '儲存本案帳務參數並重算' }));

    await waitFor(() => expect(handleClose).toHaveBeenCalledTimes(1));
    expect(clientRegistryClient.preview).toHaveBeenCalledTimes(1);
    expect(clientRegistryClient.apply).toHaveBeenCalledTimes(1);
    expect(accountingPricingClient.applyCase).toHaveBeenCalledTimes(2);
  });

  it('replays the same BeClass command after a timeout before attempting pricing', async () => {
    mockBirthCorrection();
    vi.mocked(clientRegistryClient.apply).mockRejectedValueOnce(new ApiTimeoutError(1000));
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(mockPricing);
    vi.mocked(accountingPricingClient.applyCase).mockResolvedValue({ revision: 2 });
    const handleClose = vi.fn();
    render(<AccountingParametersDrawer caseNo={mockPricing.case_no} isOpen
      onClose={handleClose} onCommitted={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: /雙胞胎/ }));
    fireEvent.change(screen.getByLabelText('補助用盡後月嫂時薪'), { target: { value: '420' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存本案帳務參數並重算' }));
    fireEvent.click(await screen.findByRole('button', { name: '確認胎數並儲存' }));

    const retry = await screen.findByRole('button', { name: /重試儲存/ });
    expect(accountingPricingClient.applyCase).not.toHaveBeenCalled();
    fireEvent.click(retry);

    await waitFor(() => expect(handleClose).toHaveBeenCalledTimes(1));
    expect(clientRegistryClient.preview).toHaveBeenCalledTimes(1);
    expect(clientRegistryClient.apply).toHaveBeenCalledTimes(2);
    const birthCalls = vi.mocked(clientRegistryClient.apply).mock.calls;
    expect(birthCalls[1]).toEqual(birthCalls[0]);
    expect(accountingPricingClient.applyCase).toHaveBeenCalledExactlyOnceWith(mockPricing.case_no,
      { ...mockPricing.terms, payroll: { ...mockPricing.terms.payroll, excess: 420 } },
      mockPricing.revision, expect.any(String), expect.any(String));
  });

  it.each([
    ['服務開始後胎數鎖定', registryBirthCount('單胞胎', false)],
    ['正式胎數待確認', registryBirthCount(null)],
  ])('單改費率不更正胎數（%s）', async (_scenario, detail) => {
    vi.mocked(clientRegistryClient.query).mockResolvedValue(detail);
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue(mockPricing);
    vi.mocked(accountingPricingClient.applyCase).mockResolvedValue({ revision: 2 });
    const handleClose = vi.fn();
    render(<AccountingParametersDrawer caseNo={mockPricing.case_no} isOpen
      onClose={handleClose} onCommitted={vi.fn()} />);

    expect(await screen.findByRole('button', { name: /雙胞胎/ })).toBeDisabled();
    expect(screen.queryByRole('button', { name: /雙胞胎/, pressed: true })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('補助用盡後月嫂時薪'), { target: { value: '420' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存本案帳務參數並重算' }));

    await waitFor(() => expect(handleClose).toHaveBeenCalledTimes(1));
    expect(clientRegistryClient.preview).not.toHaveBeenCalled();
    expect(clientRegistryClient.apply).not.toHaveBeenCalled();
    expect(accountingPricingClient.applyCase).toHaveBeenCalledWith(mockPricing.case_no,
      { ...mockPricing.terms, payroll: { ...mockPricing.terms.payroll, excess: 420 } },
      mockPricing.revision, expect.any(String), expect.any(String));
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

  it.each([
    ['一般市民', '一般市民', 'citizen', 40, 360],
    ['低收入戶', '補助市民', 'social', 120, 320],
    ['原住民市民', '原住民', 'citizen', 80, 350],
    ['非市民', '非市民', 'non_citizen', 0, 0],
  ] as const)('displays saved %s rules and saves excess rates without changing identity', async (name, label, rule, hours, covered) => {
    const terms: CasePricing['terms'] = { identity_name: name, rule, subsidy_hours: hours,
      client: { covered, excess: 310 }, payroll: { covered, excess: 390 } };
    vi.mocked(accountingPricingClient.queryCase).mockResolvedValue({ ...mockPricing, terms });
    vi.mocked(accountingPricingClient.applyCase).mockResolvedValue({ revision: 2 });
    const onClose = vi.fn();
    render(<AccountingParametersDrawer caseNo={mockPricing.case_no} isOpen onClose={onClose} onCommitted={vi.fn()} />);

    const identity = await screen.findByLabelText('補助身分');
    expect(identity).toHaveValue(label);
    expect(identity).toHaveAttribute('readonly');
    if (name !== label) expect(screen.getByText(`原版本名稱：${name}`)).toBeVisible();
    const cap = screen.getByLabelText(/補助時數上限/);
    const clientCovered = screen.getByLabelText('補助範圍內客戶時薪');
    const payrollCovered = screen.getByLabelText('補助範圍內月嫂時薪');
    expect(cap).toHaveValue(hours);
    expect(clientCovered).toHaveValue(covered);
    expect(payrollCovered).toHaveValue(covered);
    for (const input of [cap, clientCovered, payrollCovered]) {
      if (rule === 'non_citizen') expect(input).toBeDisabled();
      else expect(input).toBeEnabled();
    }
    const clientExcess = screen.getByLabelText('補助用盡後客戶時薪');
    expect(clientExcess).toHaveValue(310);
    fireEvent.change(screen.getByLabelText('補助用盡後月嫂時薪'), { target: { value: '420' } });
    expect(clientExcess).toHaveValue(310);
    expect(screen.queryByText(/160 小時|即時試算|基準應付總額/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '儲存本案帳務參數並重算' }));

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(accountingPricingClient.applyCase).toHaveBeenCalledExactlyOnceWith(mockPricing.case_no,
      { ...terms, payroll: { covered, excess: 420 } }, mockPricing.revision, '', expect.any(String));
    expect(accountingPricingClient.previewCase).not.toHaveBeenCalled();
    expect(clientRegistryClient.preview).not.toHaveBeenCalled();
  });
});
