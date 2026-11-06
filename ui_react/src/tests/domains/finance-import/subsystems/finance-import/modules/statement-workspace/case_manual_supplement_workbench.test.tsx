/**
 * File: case_manual_supplement_workbench.test.tsx
 * Description: 驗證案件抽屜手動補登款項工作台（操作銀行、交易方向、期款對象、金額帶入與自動銷帳提交）。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CaseManualSupplementWorkbench } from '../../../../../../../components/CaseManualSupplementWorkbench';
import { financeAccountingClient, type AccountingItem, type CaseAccounting } from '../../../../../../../api/finance_import/finance_accounting_client';
import { ApiHttpError, ApiTimeoutError } from '../../../../../../../api/shared/typed_errors';

vi.mock('../../../../../../../api/finance_import/finance_accounting_client', () => ({
  financeAccountingClient: {
    manualSupplement: vi.fn(),
  },
}));

const mockClientItems: AccountingItem[] = [
  {
    identity: 'client-obligation:115001:deposit',
    direction: 'receivable',
    label: '訂金',
    party: '王小美',
    expected_ntd: 13500,
    actual_ntd: 0,
    remaining_ntd: 13500,
    has_payment: false,
    version: '1',
    due_date: '2026-10-29',
    payment_stage: 'deposit',
  },
  {
    identity: 'client-obligation:115001:first',
    direction: 'receivable',
    label: '第一期',
    party: '王小美',
    expected_ntd: 40500,
    actual_ntd: 0,
    remaining_ntd: 40500,
    has_payment: false,
    version: '1',
    due_date: '2026-11-09',
    payment_stage: 'first',
  },
  {
    identity: 'client-obligation:115001:refund',
    direction: 'payable',
    label: '中途終止退款',
    party: '王小美',
    expected_ntd: 5000,
    actual_ntd: 0,
    remaining_ntd: 5000,
    has_payment: false,
    version: '1',
    due_date: null,
  },
];

const mockStaffItems: AccountingItem[] = [
  {
    identity: 'staff-obligation:115001:service_pay',
    direction: 'payable',
    label: '月嫂服務費',
    party: '陳月嫂',
    expected_ntd: 38000,
    actual_ntd: 0,
    remaining_ntd: 38000,
    has_payment: false,
    version: '1',
    due_date: '2026-12-15',
  },
];

describe('CaseManualSupplementWorkbench', () => {
  const onSuccess = vi.fn();
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders bank selection (永豐, 台新) and default client receipt direction', () => {
    render(
      <CaseManualSupplementWorkbench
        caseNo="115001"
        clientItems={mockClientItems}
        staffItems={mockStaffItems}
        onSuccess={onSuccess}
        onClose={onClose}
      />
    );

    // 驗證標題
    expect(screen.getByText('手動補登款項並自動銷帳')).toBeInTheDocument();

    // 驗證操作銀行選項
    expect(screen.getByLabelText('永豐銀行')).toBeChecked();
    expect(screen.getByLabelText('台新銀行')).not.toBeChecked();

    // 驗證預設交易方向為客戶收款
    expect(screen.getByLabelText('客戶收款（入帳）')).toBeChecked();
    expect(screen.getByLabelText('將超收差額列為客戶退款')).not.toBeChecked();

    // 驗證沖銷對象預設帶入第一項（訂金）且金額為 13500
    const amountInput = screen.getByLabelText('補登金額 (NT$)') as HTMLInputElement;
    expect(amountInput.value).toBe('13500');
  });

  it('allows switching operation bank to 台新銀行', () => {
    render(
      <CaseManualSupplementWorkbench
        caseNo="115001"
        clientItems={mockClientItems}
        staffItems={mockStaffItems}
        onSuccess={onSuccess}
        onClose={onClose}
      />
    );

    const taishinRadio = screen.getByLabelText('台新銀行');
    fireEvent.click(taishinRadio);
    expect(taishinRadio).toBeChecked();
  });

  it('updates candidate target items and amount when switching to staff salary or client refund', () => {
    render(
      <CaseManualSupplementWorkbench
        caseNo="115001"
        clientItems={mockClientItems}
        staffItems={mockStaffItems}
        onSuccess={onSuccess}
        onClose={onClose}
      />
    );

    // 切換為月嫂薪資
    fireEvent.click(screen.getByLabelText('月嫂薪資（出款）'));
    expect(screen.getByText(/陳月嫂 · 月嫂服務費/)).toBeInTheDocument();
    expect((screen.getByLabelText('補登金額 (NT$)') as HTMLInputElement).value).toBe('38000');

    // 切換為客戶退款
    fireEvent.click(screen.getByLabelText('客戶退款（出款）'));
    expect(screen.getByText(/客戶退款 · 中途終止退款/)).toBeInTheDocument();
    expect((screen.getByLabelText('補登金額 (NT$)') as HTMLInputElement).value).toBe('5000');
  });

  it('submits manual supplement command with bank selection and calls onSuccess', async () => {
    const mockUpdatedCase = { case_no: '115001' } as CaseAccounting;
    vi.mocked(financeAccountingClient.manualSupplement).mockResolvedValue(mockUpdatedCase);

    render(
      <CaseManualSupplementWorkbench
        caseNo="115001"
        clientItems={mockClientItems}
        staffItems={mockStaffItems}
        onSuccess={onSuccess}
        onClose={onClose}
      />
    );

    // 選擇台新銀行
    fireEvent.click(screen.getByLabelText('台新銀行'));

    // 修改補登金額為 10000（部分收款）
    const amountInput = screen.getByLabelText('補登金額 (NT$)');
    fireEvent.change(amountInput, { target: { value: '10000' } });

    // 輸入備註
    const reasonInput = screen.getByLabelText('備註說明（選填）');
    fireEvent.change(reasonInput, { target: { value: '臨櫃現金存入' } });

    // 提交
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));

    await waitFor(() => {
      expect(financeAccountingClient.manualSupplement).toHaveBeenCalledWith(
        '115001',
        expect.objectContaining({
          bank: 'taishin',
          direction: 'client_receipt',
          target_item: 'client-obligation:115001:deposit',
          amount_ntd: 10000,
          reason: '臨櫃現金存入',
          allow_overage_disposition: false,
        }),
        expect.any(String)
      );
      expect(onSuccess).toHaveBeenCalledWith(mockUpdatedCase);
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('submits the full receipt amount with explicit overage disposition only when chosen', async () => {
    vi.mocked(financeAccountingClient.manualSupplement).mockResolvedValue({ case_no: '115001' } as CaseAccounting);
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.change(screen.getByLabelText('補登金額 (NT$)'), { target: { value: '13600' } });
    fireEvent.click(screen.getByLabelText('將超收差額列為客戶退款'));
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await waitFor(() => expect(financeAccountingClient.manualSupplement).toHaveBeenCalledWith(
      '115001', expect.objectContaining({ amount_ntd: 13600, allow_overage_disposition: true }), expect.any(String),
    ));
  });

  it('resets the overage choice when target or direction changes and never sends it for refunds', async () => {
    vi.mocked(financeAccountingClient.manualSupplement).mockResolvedValue({ case_no: '115001' } as CaseAccounting);
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('將超收差額列為客戶退款'));
    fireEvent.change(screen.getByLabelText('沖銷對象／期款'), { target: { value: 'client-obligation:115001:first' } });
    expect(screen.getByLabelText('將超收差額列為客戶退款')).not.toBeChecked();
    fireEvent.click(screen.getByLabelText('將超收差額列為客戶退款'));
    fireEvent.click(screen.getByLabelText('客戶退款（出款）'));
    expect(screen.queryByLabelText('將超收差額列為客戶退款')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await waitFor(() => expect(financeAccountingClient.manualSupplement).toHaveBeenCalledWith(
      '115001', expect.objectContaining({ direction: 'client_refund', allow_overage_disposition: false }), expect.any(String),
    ));
  });

  it('shows the owner refund-account blocker and keeps the form open', async () => {
    vi.mocked(financeAccountingClient.manualSupplement).mockRejectedValue(new ApiHttpError(422, 'client_refund_recipient_snapshot_missing', '缺少有效退款帳戶，無法建立超收退款。'));
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('將超收差額列為客戶退款'));
    fireEvent.change(screen.getByLabelText('補登金額 (NT$)'), { target: { value: '13600' } });
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('缺少客戶退款帳戶'));
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByLabelText('將超收差額列為客戶退款')).toBeChecked();
  });

  it.each([new ApiTimeoutError(10000), new ApiHttpError(503, 'accounting_unavailable', '結果未明')])('retries unknown results with the exact original command and key while freezing edits (%s)', async failure => {
    vi.mocked(financeAccountingClient.manualSupplement)
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce({ case_no: '115001' } as CaseAccounting);
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '確認原操作結果' })).toBeEnabled());
    const original = vi.mocked(financeAccountingClient.manualSupplement).mock.calls[0];
    expect(screen.getByLabelText('補登金額 (NT$)')).toBeDisabled();
    expect(screen.getByLabelText('將超收差額列為客戶退款')).toBeDisabled();
    expect(screen.getByRole('button', { name: '關閉補登表單' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '確認原操作結果' }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(vi.mocked(financeAccountingClient.manualSupplement).mock.calls[1]).toEqual(original);
  });

  it('retains the same command key after definite rejection and creates a new one only for changed intent', async () => {
    vi.mocked(financeAccountingClient.manualSupplement).mockRejectedValue(
      new ApiHttpError(422, 'client_receipt_overpaid', '請選擇超收處置。'),
    );
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.change(screen.getByLabelText('補登金額 (NT$)'), { target: { value: '13600' } });
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('請選擇超收處置'));
    const original = vi.mocked(financeAccountingClient.manualSupplement).mock.calls[0];
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await waitFor(() => expect(financeAccountingClient.manualSupplement).toHaveBeenCalledTimes(2));
    expect(vi.mocked(financeAccountingClient.manualSupplement).mock.calls[1]).toEqual(original);
    await waitFor(() => expect(screen.getByRole('button', { name: '確認補登並自動銷帳' })).toBeEnabled());
    fireEvent.click(screen.getByLabelText('將超收差額列為客戶退款'));
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await waitFor(() => expect(financeAccountingClient.manualSupplement).toHaveBeenCalledTimes(3));
    const changed = vi.mocked(financeAccountingClient.manualSupplement).mock.calls[2];
    expect(changed[1].allow_overage_disposition).toBe(true);
    expect(changed[2]).not.toEqual(original[2]);
  });

  it('does not create a changed command while the original result is unknown', async () => {
    vi.mocked(financeAccountingClient.manualSupplement).mockRejectedValue(new ApiTimeoutError(10000));
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '確認原操作結果' })).toBeEnabled());
    // Even a programmatically injected change cannot bypass the pending command.
    fireEvent.change(screen.getByLabelText('補登金額 (NT$)'), { target: { value: '13600' } });
    fireEvent.click(screen.getByRole('button', { name: '確認原操作結果' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('不能改成另一筆補登'));
    expect(financeAccountingClient.manualSupplement).toHaveBeenCalledTimes(1);
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });
});
