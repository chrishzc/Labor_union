/**
 * File: case_manual_supplement_workbench.test.tsx
 * Description: 驗證案件抽屜手動補登款項工作台（操作銀行、交易方向、期款對象、金額帶入與自動銷帳提交）。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CaseManualSupplementWorkbench } from '../../../../../../../components/CaseManualSupplementWorkbench';
import { financeAccountingClient, type AccountingItem, type CaseAccounting } from '../../../../../../../api/finance_import/finance_accounting_client';
import { ApiHttpError, ApiTimeoutError } from '../../../../../../../api/shared/typed_errors';
import { sessionClient, type AdminPublic } from '../../../../../../../api/auth/session_client';
import { manualSupplementStorageKey } from '../../../../../../../api/finance_import/case_manual_supplement_pending';

vi.mock('../../../../../../../api/auth/session_client', () => ({
  sessionClient: { fetchCurrentUser: vi.fn(), getUser: vi.fn(), getToken: vi.fn() },
}));

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

const admin: AdminPublic = { id: 1, username: 'synthetic', display_name: 'Synthetic', role: 'admin',
  capabilities: [], is_root: false, access_control_version: 1 };

afterEach(() => vi.restoreAllMocks());

describe('CaseManualSupplementWorkbench', () => {
  const onSuccess = vi.fn();
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    vi.mocked(sessionClient.getToken).mockReturnValue('synthetic-session');
    vi.mocked(sessionClient.getUser).mockReturnValue(admin);
    vi.mocked(sessionClient.fetchCurrentUser).mockResolvedValue(admin);
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
    expect(screen.queryByRole('radio', { name: '政府入款（G 補助）' })).not.toBeInTheDocument();
    expect(screen.getByText('政府補助入款請從「銀行對帳」選取原政府流水，進入政府整期核對。')).toBeInTheDocument();

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

  it('resets the overage choice when target or direction changes before a refund command', async () => {
    vi.mocked(financeAccountingClient.manualSupplement).mockResolvedValue({ case_no: '115001' } as CaseAccounting);
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('將超收差額列為客戶退款'));
    fireEvent.change(screen.getByLabelText('沖銷對象／期款'), { target: { value: 'client-obligation:115001:first' } });
    expect(screen.getByLabelText('將超收差額列為客戶退款')).not.toBeChecked();
    fireEvent.click(screen.getByLabelText('將超收差額列為客戶退款'));
    fireEvent.click(screen.getByLabelText('客戶退款（出款）'));
    expect(screen.queryByLabelText('將超收差額列為客戶退款')).not.toBeInTheDocument();
    expect(screen.getByLabelText('將超付差額列為客戶追償')).not.toBeChecked();
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

  it('persists before POST and restores the original command after remount even when the target has settled', async () => {
    const storedKey = manualSupplementStorageKey('115001');
    vi.mocked(financeAccountingClient.manualSupplement).mockImplementationOnce(async (caseNo, command, key) => {
      const persisted = JSON.parse(window.sessionStorage.getItem(storedKey)!);
      expect(persisted).toEqual({ version: 1, actorId: 1, caseNo, command, key });
      expect(persisted).not.toHaveProperty('token');
      throw new ApiTimeoutError(10000);
    }).mockResolvedValueOnce({ case_no: '115001' } as CaseAccounting);
    const first = render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.change(screen.getByLabelText('補登金額 (NT$)'), { target: { value: '10000' } });
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await screen.findByRole('button', { name: '確認原操作結果' });
    const original = vi.mocked(financeAccountingClient.manualSupplement).mock.calls[0];
    first.unmount();
    // A new component has no prior refs; only same-tab storage can restore it.
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={[]}
      staffItems={[]} onSuccess={onSuccess} onClose={onClose} />);
    const retry = await screen.findByRole('button', { name: '確認原操作結果' });
    expect(screen.getByLabelText('補登金額 (NT$)')).toHaveValue(10000);
    expect(screen.getByLabelText('補登金額 (NT$)')).toBeDisabled();
    fireEvent.click(retry);
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(vi.mocked(financeAccountingClient.manualSupplement).mock.calls[1]).toEqual(original);
    expect(window.sessionStorage.getItem(storedKey)).toBeNull();
  });

  it('does not replay another administrator pending command using a newly authenticated administrator', async () => {
    vi.mocked(financeAccountingClient.manualSupplement).mockRejectedValueOnce(new ApiTimeoutError(10000));
    const first = render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await screen.findByRole('button', { name: '確認原操作結果' });
    const raw = window.sessionStorage.getItem(manualSupplementStorageKey('115001'));
    first.unmount();
    vi.mocked(sessionClient.fetchCurrentUser).mockResolvedValue({ ...admin, id: 2 });
    // Deliberately keep getUser() cached as A: /me, not the cache, decides.
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('原管理員登入查回'));
    expect(screen.getByRole('button', { name: '確認補登並自動銷帳' })).toBeDisabled();
    expect(financeAccountingClient.manualSupplement).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.getItem(manualSupplementStorageKey('115001'))).toBe(raw);
  });

  it('blocks a live administrator switch before retry and preserves the original record', async () => {
    vi.mocked(financeAccountingClient.manualSupplement).mockRejectedValueOnce(new ApiTimeoutError(10000));
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    const retry = await screen.findByRole('button', { name: '確認原操作結果' });
    const raw = window.sessionStorage.getItem(manualSupplementStorageKey('115001'));
    const other = { ...admin, id: 2 };
    vi.mocked(sessionClient.fetchCurrentUser).mockResolvedValue(other);
    vi.mocked(sessionClient.getUser).mockReturnValue(other);
    fireEvent.click(retry);
    await waitFor(() => expect(screen.getAllByRole('alert').some(element => element.textContent?.includes('原管理員登入查回'))).toBe(true));
    expect(financeAccountingClient.manualSupplement).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.getItem(manualSupplementStorageKey('115001'))).toBe(raw);
  });

  it.each(['{broken', JSON.stringify({ version: 1, actorId: 1, caseNo: '115001', key: '', command: {} })])('blocks corrupt pending data without clearing it (%s)', async raw => {
    window.sessionStorage.setItem(manualSupplementStorageKey('115001'), raw);
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    expect(screen.getByRole('alert')).toHaveTextContent('無法安全讀取或保留原補登操作');
    expect(screen.getByRole('button', { name: '確認補登並自動銷帳' })).toBeDisabled();
    expect(financeAccountingClient.manualSupplement).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem(manualSupplementStorageKey('115001'))).toBe(raw);
  });

  it('never POSTs when the browser cannot persist the command', async () => {
    const originalStorage = window.sessionStorage;
    const failedWrite = vi.fn(() => { throw new Error('storage unavailable'); });
    vi.spyOn(window, 'sessionStorage', 'get').mockReturnValue({
      getItem: (key: string) => originalStorage.getItem(key), setItem: failedWrite,
    } as unknown as Storage);
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('無法安全讀取或保留原補登操作'));
    expect(financeAccountingClient.manualSupplement).not.toHaveBeenCalled();
    expect(failedWrite).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: '確認補登並自動銷帳' })).toBeDisabled();
  });

  it('keeps the original record when success cleanup fails and safely retries after storage recovers', async () => {
    vi.mocked(financeAccountingClient.manualSupplement).mockResolvedValue({ case_no: '115001' } as CaseAccounting);
    const originalStorage = window.sessionStorage;
    const failedCleanup = vi.fn(() => { throw new Error('storage unavailable'); });
    const storage = vi.spyOn(window, 'sessionStorage', 'get').mockReturnValue({
      getItem: (key: string) => originalStorage.getItem(key),
      setItem: (key: string, value: string) => originalStorage.setItem(key, value), removeItem: failedCleanup,
    } as unknown as Storage);
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('補登已完成，但無法清理原操作紀錄'));
    const original = vi.mocked(financeAccountingClient.manualSupplement).mock.calls[0];
    expect(window.sessionStorage.getItem(manualSupplementStorageKey('115001'))).not.toBeNull();
    expect(onClose).not.toHaveBeenCalled();
    expect(failedCleanup).toHaveBeenCalledOnce();
    storage.mockRestore();
    fireEvent.click(screen.getByRole('button', { name: '重新讀取補登狀態' }));
    fireEvent.click(await screen.findByRole('button', { name: '確認原操作結果' }));
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(vi.mocked(financeAccountingClient.manualSupplement).mock.calls[1]).toEqual(original);
    expect(window.sessionStorage.getItem(manualSupplementStorageKey('115001'))).toBeNull();
  });

  it.each([false, true])('restores a cold same-tab journal only for the authenticated original administrator (logged out: %s)', async loggedOut => {
    const saved = { version: 1, actorId: 1, caseNo: '115001', key: 'original-pending-key', command: {
      bank: 'taishin', direction: 'client_receipt', target_item: 'client-obligation:115001:deposit',
      amount_ntd: 13600, transaction_date: '2026-11-05', reason: null, allow_overage_disposition: true,
    } };
    const raw = JSON.stringify(saved);
    window.sessionStorage.setItem(manualSupplementStorageKey('115001'), raw);
    if (loggedOut) {
      vi.mocked(sessionClient.getToken).mockReturnValue(null);
      vi.mocked(sessionClient.fetchCurrentUser).mockRejectedValue(new ApiHttpError(401, 'unauthenticated', '未登入'));
    } else {
      vi.mocked(financeAccountingClient.manualSupplement).mockResolvedValue({ case_no: '115001' } as CaseAccounting);
    }
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    if (loggedOut) {
      await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('無法確認原補登的登入管理員'));
      expect(financeAccountingClient.manualSupplement).not.toHaveBeenCalled();
      expect(window.sessionStorage.getItem(manualSupplementStorageKey('115001'))).toBe(raw);
    } else {
      fireEvent.click(await screen.findByRole('button', { name: '確認原操作結果' }));
      await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
      expect(financeAccountingClient.manualSupplement).toHaveBeenCalledWith(saved.caseNo, saved.command, saved.key);
      expect(window.sessionStorage.getItem(manualSupplementStorageKey('115001'))).toBeNull();
    }
  });

  it('can read back an existing government operation without offering a new case-level government entry', async () => {
    const saved = { version: 1, actorId: 1, caseNo: '115001', key: 'existing-government-key', command: {
      bank: 'taishin', direction: 'government_subsidy', target_item: 'government_subsidy',
      amount_ntd: 1000, transaction_date: '2026-11-05', reason: null, allow_overage_disposition: false,
    } };
    window.sessionStorage.setItem(manualSupplementStorageKey('115001'), JSON.stringify(saved));
    vi.mocked(financeAccountingClient.manualSupplement).mockResolvedValue({ case_no: '115001' } as CaseAccounting);
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.click(await screen.findByRole('button', { name: '確認原操作結果' }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(financeAccountingClient.manualSupplement).toHaveBeenCalledWith(saved.caseNo, saved.command, saved.key);
    expect(screen.queryByRole('radio', { name: '政府入款（G 補助）' })).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem(manualSupplementStorageKey('115001'))).toBeNull();
  });

  it('persists explicit refund recovery and restores its original mode and key after an unknown result', async () => {
    vi.mocked(financeAccountingClient.manualSupplement).mockRejectedValueOnce(new ApiTimeoutError(10000))
      .mockResolvedValueOnce({ case_no: '115001' } as CaseAccounting);
    const first = render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('客戶退款（出款）'));
    expect(screen.getByLabelText('將超付差額列為客戶追償')).not.toBeChecked();
    fireEvent.change(screen.getByLabelText('補登金額 (NT$)'), { target: { value: '5100' } });
    fireEvent.click(screen.getByLabelText('將超付差額列為客戶追償'));
    fireEvent.click(screen.getByRole('button', { name: '確認補登並自動銷帳' }));
    await screen.findByRole('button', { name: '確認原操作結果' });
    const original = vi.mocked(financeAccountingClient.manualSupplement).mock.calls[0];
    expect(original[1]).toMatchObject({ direction: 'client_refund', target_item: 'client-obligation:115001:refund',
      amount_ntd: 5100, allow_overage_disposition: true });
    first.unmount();
    render(<CaseManualSupplementWorkbench caseNo="115001" clientItems={mockClientItems}
      staffItems={mockStaffItems} onSuccess={onSuccess} onClose={onClose} />);
    const retry = await screen.findByRole('button', { name: '確認原操作結果' });
    expect(screen.getByLabelText('將超付差額列為客戶追償')).toBeChecked();
    expect(screen.getByLabelText('客戶退款（出款）')).toBeChecked();
    expect(screen.getByLabelText('客戶收款（入帳）')).toBeDisabled();
    fireEvent.click(screen.getByLabelText('客戶收款（入帳）'));
    expect(screen.getByLabelText('客戶退款（出款）')).toBeChecked();
    fireEvent.click(retry);
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(vi.mocked(financeAccountingClient.manualSupplement).mock.calls[1]).toEqual(original);
    expect(window.sessionStorage.getItem(manualSupplementStorageKey('115001'))).toBeNull();
  });
});
