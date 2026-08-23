/**
 * File: account_query_page.test.tsx
 * Description: 驗證帳號中心 lazy GET、真實資料槽位與 mutation disabled 邊界。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { accountDirectoryClient } from '../api/access/account_directory_client';
import { auditQueryClient } from '../api/access/audit_query_client';
import { jobObservationClient } from '../api/jobs/job_observation_client';
import { AccountManagementPage } from '../pages/AccountManagementPage';
import { ACCOUNT_DIRECTORY_FIXTURE, AUDIT_PAGE_FIXTURE, JOB_OBSERVATION_FIXTURE } from './fixtures/access/account_query_contract_fixtures';

describe('AccountManagementPage query slice', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(accountDirectoryClient, 'query').mockResolvedValue(ACCOUNT_DIRECTORY_FIXTURE);
    vi.spyOn(auditQueryClient, 'query').mockResolvedValue(AUDIT_PAGE_FIXTURE);
    vi.spyOn(jobObservationClient, 'query').mockResolvedValue(JOB_OBSERVATION_FIXTURE);
  });

  it('renders the account GET and leaves unsupported controls disabled', async () => {
    render(<AccountManagementPage />);
    await waitFor(() => expect(screen.getByText(/根帳號/, { exact: false })).toBeInTheDocument());
    expect(accountDirectoryClient.query).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: /建立工作人員帳號/ })).toBeDisabled();
    expect(screen.getByText(/Email \/ IP \/ 最後登入/)).toBeInTheDocument();
  });

  it('loads audit lazily and does not query jobs until a job id is submitted', async () => {
    render(<AccountManagementPage />);
    await waitFor(() => expect(screen.getByText(/根帳號/, { exact: false })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: /安全操作與 Session/ }));
    await waitFor(() => expect(screen.getByText('authentication')).toBeInTheDocument());
    expect(auditQueryClient.query).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('tab', { name: /背景排程與系統看板/ }));
    expect(jobObservationClient.query).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Job ID'), { target: { value: 'job-observation-1' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢狀態' }));
    await waitFor(() => expect(screen.getByText('job-observation-1')).toBeInTheDocument());
    expect(jobObservationClient.query).toHaveBeenCalledTimes(1);
  });
});
