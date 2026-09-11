/**
 * File: account_query_page.test.tsx
 * Description: 驗證帳號中心 lazy GET、真實資料槽位與 mutation disabled 邊界。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { accountDirectoryClient } from '../api/access/account_directory_client';
import { accountCenterClient } from '../api/access/account_center_client';
import { auditQueryClient } from '../api/access/audit_query_client';
import { AccountManagementPage } from '../pages/AccountManagementPage';
import { ACCOUNT_DIRECTORY_FIXTURE, AUDIT_PAGE_FIXTURE } from './fixtures/access/account_query_contract_fixtures';

describe('AccountManagementPage query slice', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(accountDirectoryClient, 'query').mockResolvedValue(ACCOUNT_DIRECTORY_FIXTURE);
    vi.spyOn(auditQueryClient, 'query').mockResolvedValue(AUDIT_PAGE_FIXTURE);
  });

  it('renders the account GET and leaves unsupported controls disabled', async () => {
    render(<AccountManagementPage />);
    await waitFor(() => expect(screen.getByText(/根帳號/, { exact: false })).toBeInTheDocument());
    expect(accountDirectoryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Root 帳號受保護/)).toBeVisible();
    expect(screen.queryByRole('button', {name: '重設密碼'})).toBeNull();
    expect(screen.queryByRole('button', {name: /強制登出|停權|重設 MFA/})).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /建立工作人員帳號/ }));
    expect(screen.getByRole('dialog', { name: '建立工作人員帳號' })).toBeVisible();
    expect(screen.getByRole('button', { name: '確認執行' })).toBeDisabled();
    expect(screen.getByLabelText('新帳號')).toBeVisible();
    expect(screen.queryByLabelText('重設密碼')).not.toBeInTheDocument();
    expect(screen.queryByText(/Access Control Version|帳號識別|Email \/ IP/)).not.toBeInTheDocument();
  });

  it('loads audit lazily and exposes only account, verification, and audit tabs', async () => {
    render(<AccountManagementPage />);
    await waitFor(() => expect(screen.getByText(/根帳號/, { exact: false })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: /安全操作與登入稽核/ }));
    await waitFor(() => expect(screen.getByText('登入驗證')).toBeInTheDocument());
    expect(auditQueryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.getByRole('tab', { name: /內部人員帳號清冊/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /驗證器動態碼/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /安全操作與登入稽核/ })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /背景工作狀態/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('背景工作查詢碼')).not.toBeInTheDocument();
  });

  it('confirms only the selected account operation and refreshes the directory', async () => {
    vi.mocked(accountDirectoryClient.query).mockResolvedValue(ACCOUNT_DIRECTORY_FIXTURE.map(user => ({...user, is_root: false})));
    const revoke = vi.spyOn(accountCenterClient, 'revokeSessions').mockResolvedValue({
      operation: 'account-sessions-revoke', target_account_id: 1,
      resulting_access_control_version: 3, receipt_identity: 'a'.repeat(64), replayed: false,
    });
    render(<AccountManagementPage />);
    await screen.findByText(/根帳號/);
    fireEvent.click(screen.getByRole('button', { name: /強制登出/ }));
    expect(revoke).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('操作原因'), { target: { value: '  已確認登出需求  ' } });
    fireEvent.click(screen.getByRole('button', { name: '確認執行' }));
    expect(screen.getByRole('button', { name: '確認執行' })).toBeDisabled();
    expect(revoke).toHaveBeenCalledExactlyOnceWith(1, {
      reason: '已確認登出需求', expected_version: 2, idempotency_key: expect.any(String),
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(accountDirectoryClient.query).toHaveBeenCalledTimes(2);
  });
});
