/**
 * File: account_audit_query_flow.test.tsx
 * Description: 驗證 Audit tab lazy list、detail GET 與 stale detail guard。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AccountManagementPage } from '../pages/AccountManagementPage';
import { accountDirectoryClient } from '../api/access/account_directory_client';
import { auditQueryClient } from '../api/access/audit_query_client';
import { ACCOUNT_DIRECTORY_FIXTURE } from './fixtures/access/account_query_contract_fixtures';
import { AUDIT_DETAIL_FIXTURE, AUDIT_PAGE_FIXTURE } from './fixtures/access/audit_query_contract_fixtures';

describe('Account Audit query flow', () => {
  beforeEach(() => {
    vi.spyOn(accountDirectoryClient, 'query').mockResolvedValue(ACCOUNT_DIRECTORY_FIXTURE);
  });
  afterEach(() => vi.restoreAllMocks());

  it('loads list lazily and requests allowlisted detail only after click', async () => {
    const list = vi.spyOn(auditQueryClient, 'query').mockResolvedValue(AUDIT_PAGE_FIXTURE);
    const detail = vi.spyOn(auditQueryClient, 'detail').mockResolvedValue(AUDIT_DETAIL_FIXTURE);
    render(<AccountManagementPage />);
    await waitFor(() => expect(screen.getByText('root-user')).toBeInTheDocument());
    expect(list).not.toHaveBeenCalled();
    expect(detail).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('tab', { name: /安全操作與登入稽核/ }));
    await waitFor(() => expect(screen.getByText('登入驗證')).toBeInTheDocument());
    expect(list).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '查看' }));
    await waitFor(() => expect(screen.getByText('provided')).toBeInTheDocument());
    expect(detail).toHaveBeenCalledWith(10, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(screen.queryByText(/raw_payload|0900000000|secret/)).not.toBeInTheDocument();
  });

  it('does not render a superseded detail response', async () => {
    vi.spyOn(auditQueryClient, 'query').mockResolvedValue(AUDIT_PAGE_FIXTURE);
    let finish: ((value: typeof AUDIT_DETAIL_FIXTURE) => void) | undefined;
    vi.spyOn(auditQueryClient, 'detail').mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    render(<AccountManagementPage />);
    fireEvent.click(screen.getByRole('tab', { name: /安全操作與登入稽核/ }));
    await screen.findByText('登入驗證');
    fireEvent.click(screen.getByRole('button', { name: '查看' }));
    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
    finish?.(AUDIT_DETAIL_FIXTURE);
    await waitFor(() => expect(screen.queryByText('provided')).not.toBeInTheDocument());
  });
});
