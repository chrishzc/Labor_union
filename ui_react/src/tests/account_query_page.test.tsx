/**
 * File: account_query_page.test.tsx
 * Description: 驗證帳號清冊查詢與帳號操作邊界。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { accountDirectoryClient } from '../api/access/account_directory_client';
import { accountCenterClient } from '../api/access/account_center_client';
import { AccountManagementPage } from '../pages/AccountManagementPage';
import { ACCOUNT_DIRECTORY_FIXTURE } from './fixtures/access/account_query_contract_fixtures';

describe('AccountManagementPage query slice', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(accountDirectoryClient, 'query').mockResolvedValue(ACCOUNT_DIRECTORY_FIXTURE);
  });

  it('renders the account GET and leaves unsupported controls disabled', async () => {
    const create = vi.spyOn(accountCenterClient, 'create').mockRejectedValue(new Error('unexpected mutation'));
    render(<AccountManagementPage />);
    await waitFor(() => expect(screen.getByText(/根帳號/, { exact: false })).toBeInTheDocument());
    expect(accountDirectoryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Root 帳號受保護/)).toBeVisible();
    expect(screen.queryByRole('button', {name: '重設密碼'})).toBeNull();
    expect(screen.queryByRole('button', {name: /強制登出|停權|重設 MFA/})).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /建立工作人員帳號/ }));
    expect(screen.getByRole('dialog', { name: '建立工作人員帳號' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '確認執行' }));
    expect(create).not.toHaveBeenCalled();
    expect(screen.getByText('請填寫或選擇「新帳號」後再儲存。')).toBeInTheDocument();
    expect(screen.getByLabelText('新帳號')).toBeVisible();
    expect(screen.queryByLabelText('重設密碼')).not.toBeInTheDocument();
    expect(screen.queryByText(/Access Control Version|帳號識別|Email \/ IP/)).not.toBeInTheDocument();
  });

  it('confirms only the selected account operation and refreshes the directory', async () => {
    vi.mocked(accountDirectoryClient.query).mockResolvedValue(ACCOUNT_DIRECTORY_FIXTURE.map(user => ({...user, is_root: false})));
    const revoke = vi.spyOn(accountCenterClient, 'revokeSessions').mockResolvedValue({
      operation: 'account-sessions-revoke', target_account_id: 1,
      resulting_access_control_version: 3, receipt_identity: 'a'.repeat(64), replayed: false,
    });
    render(<AccountManagementPage />);
    await screen.findByText(/根帳號/);
    expect(revoke).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /強制登出/ }));
    expect(screen.queryByRole('button', { name: '確認執行' })).not.toBeInTheDocument();
    expect(revoke).toHaveBeenCalledExactlyOnceWith(1, {
      reason: '', expected_version: 2, idempotency_key: expect.any(String),
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(accountDirectoryClient.query).toHaveBeenCalledTimes(2);
  });
});
