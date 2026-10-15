import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientRegistryVirtualAccount } from '../../../../../../../components/ClientRegistryVirtualAccount';
import { ApiHttpError, ApiTimeoutError } from '../../../../../../../api/shared/typed_errors';

const mocks = vi.hoisted(() => ({ query: vi.fn(), apply: vi.fn() }));
vi.mock('../../../../../../../api/client_finance/case_virtual_account_client', () => ({ caseVirtualAccountClient: mocks }));
const old = '99781699114001', next = '99781699114999';
const view = { case_no: '114000001', imported_virtual_accounts: [old], built_in_virtual_account: old, mapping_ids: [1] };
const receipt = { case_no: view.case_no, before: [old], virtual_account: next };
const deferred = () => { let resolve!: (value?: unknown) => void; const promise = new Promise(done => { resolve = done; }); return { resolve, promise }; };

beforeEach(() => {
  vi.resetAllMocks();
  mocks.query.mockResolvedValue(view);
  mocks.apply.mockResolvedValue(receipt);
});
const mount = async (onRefresh = vi.fn().mockResolvedValue(undefined)) => {
  const onStateChange = vi.fn();
  const rendered = render(<ClientRegistryVirtualAccount caseNo={view.case_no} disabled={false} onRefresh={onRefresh} onStateChange={onStateChange} />);
  await screen.findByLabelText('匯入虛擬帳號');
  return { onRefresh, onStateChange, ...rendered };
};
const edit = () => fireEvent.change(screen.getByLabelText('匯入虛擬帳號'), { target: { value: next } });
const save = () => fireEvent.click(screen.getByRole('button', { name: /^儲存虛擬帳號$/ }));

describe('名冊虛擬帳號設定', () => {
  it('saves directly without a reason or preview and waits for account and roster readback', async () => {
    const refresh = deferred();
    const state = await mount(vi.fn(() => refresh.promise));
    expect(screen.queryByLabelText('虛擬帳號修改原因')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '預覽帳號變更' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^儲存虛擬帳號$/ })).toBeDisabled();
    edit();
    mocks.query.mockResolvedValue({ ...view, imported_virtual_accounts: [next], mapping_ids: [2] });
    save();
    await waitFor(() => expect(state.onRefresh).toHaveBeenCalledOnce());
    expect(mocks.apply).toHaveBeenCalledWith({ case_no: view.case_no, virtual_account: next, expected_mapping_ids: [1] }, expect.stringMatching(/^case-va-/));
    expect(screen.queryByText('虛擬帳號已儲存，名冊資料已更新。')).not.toBeInTheDocument();
    expect(state.onStateChange).toHaveBeenLastCalledWith({ dirty: true, busy: true });
    await act(async () => refresh.resolve());
    expect(await screen.findByText('虛擬帳號已儲存，名冊資料已更新。')).toBeInTheDocument();
    expect(screen.getByLabelText('匯入虛擬帳號')).toHaveValue(next);
    expect(state.onStateChange).toHaveBeenLastCalledWith({ dirty: false, busy: false });
  });

  it('preserves a stale draft and requires current data before saving again', async () => {
    const state = await mount();
    edit();
    mocks.apply.mockRejectedValueOnce(new ApiHttpError(409, 'case_virtual_account_stale', '帳號已被其他人更新，請重新讀取。'));
    save();
    await screen.findByText('帳號已被其他人更新，請重新讀取。');
    expect(screen.getByLabelText('匯入虛擬帳號')).toHaveValue(next);
    expect(screen.getByRole('button', { name: /^儲存虛擬帳號$/ })).toBeDisabled();
    expect(state.onStateChange).toHaveBeenLastCalledWith({ dirty: true, busy: false });
    mocks.query.mockResolvedValue({ ...view, mapping_ids: [2] });
    fireEvent.click(screen.getByRole('button', { name: '重新讀取虛擬帳號' }));
    await waitFor(() => expect(screen.getByLabelText('匯入虛擬帳號')).toHaveValue(old));
    edit(); save();
    await screen.findByText('虛擬帳號已儲存，名冊資料已更新。');
    expect(mocks.apply.mock.calls[1][0].expected_mapping_ids).toEqual([2]);
  });

  it('keeps unknown outcomes locked and retries only the same command and key', async () => {
    const state = await mount();
    edit();
    mocks.apply.mockRejectedValueOnce(new ApiTimeoutError(10000));
    save();
    const retry = await screen.findByRole('button', { name: '確認同一筆儲存結果' });
    expect(screen.getByLabelText('匯入虛擬帳號')).toBeDisabled();
    expect(screen.getByRole('button', { name: '取消帳號變更' })).toBeDisabled();
    expect(state.onStateChange).toHaveBeenLastCalledWith({ dirty: true, busy: true });
    const command = mocks.apply.mock.calls[0];
    mocks.query.mockResolvedValue({ ...view, imported_virtual_accounts: [next], mapping_ids: [2] });
    fireEvent.click(retry);
    await screen.findByText('虛擬帳號已儲存，名冊資料已更新。');
    expect(mocks.apply.mock.calls[1]).toEqual(command);
  });

  it('retries failed readback without applying a second mutation', async () => {
    const onRefresh = vi.fn().mockRejectedValueOnce(new Error('清單無法讀取')).mockResolvedValue(undefined);
    const state = await mount(onRefresh);
    edit();
    mocks.query.mockResolvedValue({ ...view, imported_virtual_accounts: [next], mapping_ids: [2] });
    save();
    const retry = await screen.findByRole('button', { name: '重新讀取已儲存帳號' });
    expect(state.onStateChange).toHaveBeenLastCalledWith({ dirty: true, busy: true });
    fireEvent.click(retry);
    await screen.findByText('虛擬帳號已儲存，名冊資料已更新。');
    expect(mocks.apply).toHaveBeenCalledOnce();
    expect(onRefresh).toHaveBeenCalledTimes(2);
  });

  it('creates a new account without asking for a reason', async () => {
    mocks.query.mockResolvedValue({ ...view, imported_virtual_accounts: [], mapping_ids: [] });
    await mount();
    expect(screen.getByLabelText('匯入虛擬帳號')).toHaveValue('');
    edit(); save();
    await screen.findByText('虛擬帳號已儲存，名冊資料已更新。');
    expect(mocks.apply.mock.calls[0][0].expected_mapping_ids).toEqual([]);
  });

  it('ignores late readback after switching cases', async () => {
    const pending = deferred();
    const state = await mount();
    edit();
    mocks.query.mockReturnValueOnce(pending.promise);
    save();
    await waitFor(() => expect(state.onRefresh).toHaveBeenCalledOnce());
    mocks.query.mockResolvedValue({ ...view, case_no: '114000002' });
    state.rerender(<ClientRegistryVirtualAccount caseNo="114000002" disabled={false} onRefresh={state.onRefresh} onStateChange={state.onStateChange} />);
    await waitFor(() => expect(screen.getByLabelText('匯入虛擬帳號')).toHaveValue(old));
    await act(async () => pending.resolve({ ...view, imported_virtual_accounts: [next] }));
    expect(screen.getByLabelText('匯入虛擬帳號')).toHaveValue(old);
    expect(screen.queryByText('虛擬帳號已儲存，名冊資料已更新。')).not.toBeInTheDocument();
  });
});
