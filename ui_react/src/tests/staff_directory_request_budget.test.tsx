/**
 * File: staff_directory_request_budget.test.tsx
 * Description: 驗證 StaffPage initial／cursor 預算、StrictMode 防重與 tab／Drawer 不重查名冊。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffQualificationMasterClient } from '../api/staff/qualification_master_client';
import { staffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import { StaffPage } from '../pages/StaffPage';
import {
  STAFF_PAGE_ONE,
  STAFF_PAGE_TWO,
} from './fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from './fixtures/staff/staff_qualification_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from './fixtures/staff/staff_lifecycle_contract_fixtures';

describe('StaffPage request budget', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage')
      .mockResolvedValueOnce(STAFF_PAGE_ONE)
      .mockResolvedValueOnce(STAFF_PAGE_TWO);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
  });

  it('uses one initial GET in StrictMode and one GET per manual cursor', async () => {
    render(<React.StrictMode><StaffPage /></React.StrictMode>);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: '載入下一頁' }));
    await waitFor(() => expect(screen.getByText('去敏人員乙')).toBeInTheDocument());
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(2);
    expect(staffDirectoryClient.queryPage).toHaveBeenLastCalledWith(
      { pageSize: 200, afterId: 12 },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('retries the same cursor only after an explicit next-page failure', async () => {
    vi.mocked(staffDirectoryClient.queryPage).mockReset()
      .mockResolvedValueOnce(STAFF_PAGE_ONE)
      .mockRejectedValueOnce(new Error('下一頁暫時失敗'))
      .mockResolvedValueOnce(STAFF_PAGE_TWO);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: '載入下一頁' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '重試載入下一頁' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '重試載入下一頁' }));

    await waitFor(() => expect(screen.getByText('去敏人員乙')).toBeInTheDocument());
    expect(staffDirectoryClient.queryPage).toHaveBeenNthCalledWith(
      3,
      { pageSize: 200, afterId: 12 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('tab switches and Drawer interaction add zero directory requests', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    fireEvent.click(screen.getByRole('button', { name: /服務月嫂名冊/ }));
    fireEvent.click(screen.getAllByRole('button', { name: /檢視服務人員摘要/ })[0]);
    await waitFor(() => expect(screen.getAllByText('在職').length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByText(/整體狀態/)).toBeInTheDocument());

    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
  });

  it('aborts the active request after a real unmount', async () => {
    let receivedSignal: AbortSignal | undefined;
    vi.mocked(staffDirectoryClient.queryPage).mockReset().mockImplementationOnce(
      (_params, options) => {
        receivedSignal = options?.signal;
        return new Promise<never>(() => undefined);
      }
    );
    const view = render(<StaffPage />);
    view.unmount();
    await Promise.resolve();

    expect(receivedSignal?.aborted).toBe(true);
  });
});
