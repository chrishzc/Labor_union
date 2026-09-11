/**
 * File: account_management_no_fake_mutation.test.tsx
 * Description: 鎖定 Account 頁除核准 Audit GET 外不開啟假 mutation。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AccountManagementPage } from '../pages/AccountManagementPage';
import { accountDirectoryClient } from '../api/access/account_directory_client';
import { accountCenterClient } from '../api/access/account_center_client';
import { ACCOUNT_DIRECTORY_FIXTURE } from './fixtures/access/account_query_contract_fixtures';
import { AccountCreateCommandSchema, AccountPasswordResetCommandSchema } from '../api/access/account_center_schemas';

describe('Account Management mutation boundary', () => {
  afterEach(() => vi.restoreAllMocks());

  it.each([9, 10, 11, 12])('uses the 10-character minimum in create/reset schemas (%i)', (length) => {
    const common = { password: 'x'.repeat(length), reason: 'mock boundary', idempotency_key: 'mock-password' };
    expect(AccountCreateCommandSchema.safeParse({ ...common, username: 'mock-user', display_name: 'Mock' }).success).toBe(length >= 10);
    expect(AccountPasswordResetCommandSchema.safeParse({ ...common, expected_version: 1 }).success).toBe(length >= 10);
  });

  it('enables create and reset confirmation at 10 characters, but not 9', async () => {
    vi.spyOn(accountDirectoryClient, 'query').mockResolvedValue(ACCOUNT_DIRECTORY_FIXTURE.map(user => ({...user, is_root: false})));
    render(<AccountManagementPage />);
    await screen.findByText('root-user');
    fireEvent.click(screen.getByRole('button', { name: /建立工作人員帳號/ }));
    fireEvent.change(screen.getByLabelText('新帳號'), { target: { value: 'mock-user' } });
    fireEvent.change(screen.getByLabelText('顯示名稱'), { target: { value: 'Mock' } });
    fireEvent.change(screen.getByLabelText('操作原因'), { target: { value: 'mock 驗收' } });
    for (const length of [9, 10]) {
      fireEvent.change(screen.getByLabelText('新密碼'), { target: { value: 'x'.repeat(length) } });
      expect(screen.getByRole('button', { name: '確認執行' }).hasAttribute('disabled')).toBe(length < 10);
    }
    fireEvent.click(screen.getByRole('button', { name: '關閉帳號操作' }));
    fireEvent.click(screen.getAllByRole('button', { name: '重設密碼' })[0]);
    fireEvent.change(screen.getByLabelText('操作原因'), { target: { value: 'mock 驗收' } });
    for (const length of [9, 10]) {
      fireEvent.change(screen.getByLabelText('重設密碼'), { target: { value: 'x'.repeat(length) } });
      expect(screen.getByRole('button', { name: '確認執行' }).hasAttribute('disabled')).toBe(length < 10);
    }
  });

  it('opens target-specific forms without mutations and keeps confirmation disabled without a reason', async () => {
    vi.spyOn(accountDirectoryClient, 'query').mockResolvedValue(ACCOUNT_DIRECTORY_FIXTURE.map(user => ({...user, is_root: false})));
    const calls = [vi.spyOn(accountCenterClient, 'create'), vi.spyOn(accountCenterClient, 'resetPassword'), vi.spyOn(accountCenterClient, 'resetMfa'), vi.spyOn(accountCenterClient, 'revokeSessions'), vi.spyOn(accountCenterClient, 'setEnabled')];
    render(<AccountManagementPage />);
    await waitFor(() => expect(screen.getByText('root-user')).toBeInTheDocument());
    for (const pattern of [
      /建立工作人員帳號/,
      /重設 MFA/,
      /強制登出/,
      /停權/,
    ]) {
      fireEvent.click(screen.getAllByRole('button', { name: pattern })[0]);
      expect(screen.getByRole('button', { name: '確認執行' })).toBeDisabled();
      expect(screen.getByLabelText('操作原因')).toHaveValue('');
      fireEvent.click(screen.getByRole('button', { name: '關閉帳號操作' }));
    }
    fireEvent.click(screen.getAllByRole('button', { name: '重設密碼' })[0]);
    expect(screen.queryByLabelText('新帳號')).not.toBeInTheDocument();
    expect(screen.getByLabelText('重設密碼')).toHaveValue('');
    fireEvent.change(screen.getByLabelText('操作原因'), { target: { value: '本人要求重設' } });
    expect(screen.getByRole('button', { name: '確認執行' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '關閉帳號操作' }));
    calls.forEach((call) => expect(call).not.toHaveBeenCalled());
    fireEvent.click(screen.getByRole('tab', { name: /驗證器動態碼/ }));
    expect(document.querySelector('[data-control-id="account.mfa.enroll"]')).toBeNull();
    expect(screen.queryByRole('tab', { name: /背景工作狀態/ })).not.toBeInTheDocument();
    for (const id of ['account.jobs.cancel', 'account.jobs.retry', 'account.jobs.run']) {
      expect(document.querySelector(`[data-control-id="${id}"]`)).toBeNull();
    }
    expect(screen.queryByText(/建立成功|停權成功|重試成功|取消成功/)).not.toBeInTheDocument();
  });
});
