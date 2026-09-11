import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StaffRegistryEditor } from '../../../../../../../components/StaffRegistryEditor';
import { STAFF_PROFILE } from './fixtures/staff_profile_contract_fixtures';

const mocks = vi.hoisted(() => ({ previewProfile: vi.fn(), applyProfile: vi.fn(), previewBank: vi.fn(), applyBank: vi.fn() }));
vi.mock('../../../../../../../api/staff_registry/staff_registry_client', () => ({ staffRegistryClient: mocks }));

describe('Staff registry owner editing', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.previewBank.mockResolvedValue({ staff_id: STAFF_PROFILE.staff_id, current_version: STAFF_PROFILE.bank_accounts_version, operation: 'add', before: null, after: { account_id: null, bank_code: '812', branch_code: '0012', account_last4: '7890', is_primary: false, is_active: true }, preview_fingerprint: 'b'.repeat(64) });
  });

  it('clears the complete bank account after an uncertain result and prevents duplicate in-flight apply', async () => {
    let rejectApply: (error: Error) => void = () => undefined;
    mocks.applyBank.mockImplementation(() => new Promise((_, reject) => { rejectApply = reject; }));
    const onUpdated = vi.fn().mockResolvedValue(undefined);
    render(<StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={onUpdated} />);
    const bank = screen.getByRole('heading', { name: /管理銀行帳戶/ }).closest('section') as HTMLElement;

    fireEvent.change(within(bank).getByLabelText('銀行代碼'), { target: { value: '812' } });
    fireEvent.change(within(bank).getByLabelText('分行代碼'), { target: { value: '0012' } });
    const account = within(bank).getByLabelText('完整新帳號');
    fireEvent.change(account, { target: { value: '1234567890' } });
    fireEvent.click(within(bank).getByRole('button', { name: '預覽變更' }));
    await within(bank).findByText(/末四碼 7890/);
    fireEvent.change(within(bank).getByLabelText('異動原因'), { target: { value: '本人提供新帳戶' } });
    const apply = within(bank).getByRole('button', { name: '確認儲存' });
    fireEvent.click(apply);
    fireEvent.click(apply);
    await waitFor(() => expect(mocks.applyBank).toHaveBeenCalledTimes(1));
    expect(mocks.applyBank.mock.calls[0][5]).toMatch(/^staff-bank-/);
    rejectApply(new Error('連線中斷，結果未知'));
    await waitFor(() => expect(account).toHaveValue(''));
    expect(onUpdated).toHaveBeenCalledTimes(1);
    expect(screen.queryByDisplayValue('1234567890')).not.toBeInTheDocument();
  });
});
