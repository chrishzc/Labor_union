/**
 * File: account_query_page.test.tsx
 * Description: 驗證帳號中心 lazy GET、真實資料槽位與 mutation disabled 邊界。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { accountDirectoryClient } from '../api/access/account_directory_client';
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
    expect(screen.getByRole('button', { name: /建立工作人員帳號/ })).toBeDisabled();
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
});
