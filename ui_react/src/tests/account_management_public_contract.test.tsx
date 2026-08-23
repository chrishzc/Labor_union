/**
 * File: account_management_public_contract.test.tsx
 * Description: 驗證 Account Center mutation 只接受 strict typed receipt 且不顯示秘密資料。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AccountManagementPage } from '../pages/AccountManagementPage';
import { accountDirectoryClient } from '../api/access/account_directory_client';
import { accountCenterClient } from '../api/access/account_center_client';
import { ACCOUNT_DIRECTORY_FIXTURE } from './fixtures/access/account_query_contract_fixtures';

describe('Account Management public mutation contract', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends expected version/reason and renders only safe receipt projection', async () => {
    vi.spyOn(accountDirectoryClient, 'query').mockResolvedValue(ACCOUNT_DIRECTORY_FIXTURE);
    const command = vi.spyOn(accountCenterClient, 'revokeSessions').mockResolvedValue({
      operation: 'account-sessions-revoke',
      target_account_id: 1,
      resulting_access_control_version: 3,
      receipt_identity: 'a'.repeat(64),
      replayed: false,
      account: null,
    });
    render(<AccountManagementPage />);
    await screen.findByText('root-user');
    fireEvent.change(screen.getByLabelText('操作原因'), { target: { value: 'security review' } });
    fireEvent.click(screen.getByRole('button', { name: /強制登出/ }));
    await waitFor(() => expect(screen.getByText(/account-sessions-revoke/)).toBeInTheDocument());
    expect(command).toHaveBeenCalledWith(1, expect.objectContaining({
      reason: 'security review', expected_version: 2, idempotency_key: expect.stringMatching(/^account-/),
    }));
    expect(screen.queryByText('a'.repeat(64))).not.toBeInTheDocument();
    expect(screen.queryByText(/password|secret|recovery code/i)).not.toBeInTheDocument();
  });
});
