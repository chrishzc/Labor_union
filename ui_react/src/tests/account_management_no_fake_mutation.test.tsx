/**
 * File: account_management_no_fake_mutation.test.tsx
 * Description: 鎖定 Account 頁除核准 Audit GET 外不開啟假 mutation。
 */
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AccountManagementPage } from '../pages/AccountManagementPage';
import { accountDirectoryClient } from '../api/access/account_directory_client';
import { ACCOUNT_DIRECTORY_FIXTURE } from './fixtures/access/account_query_contract_fixtures';

describe('Account Management mutation boundary', () => {
  afterEach(() => vi.restoreAllMocks());

  it('keeps account, MFA and job mutation controls natively disabled', async () => {
    vi.spyOn(accountDirectoryClient, 'query').mockResolvedValue(ACCOUNT_DIRECTORY_FIXTURE);
    render(<AccountManagementPage />);
    await waitFor(() => expect(screen.getByText('root-user')).toBeInTheDocument());
    for (const pattern of [
      /建立工作人員帳號/,
      /重設 MFA/,
      /強制登出/,
      /停權/,
    ]) expect(screen.getAllByRole('button', { name: pattern })[0]).toBeDisabled();
    expect(screen.queryByText(/建立成功|停權成功|重試成功|取消成功/)).not.toBeInTheDocument();
  });
});
