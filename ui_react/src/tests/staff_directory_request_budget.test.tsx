/**
 * File: staff_directory_request_budget.test.tsx
 * Description: 驗證 StaffPage initial／cursor 預算、StrictMode 防重與 tab／Drawer 不重查名冊。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

  it('shows validated rows before the final page and then sorts the whole roster in StrictMode', async () => {
    let resolveNextPage: ((value: typeof STAFF_PAGE_TWO) => void) | undefined;
    vi.mocked(staffDirectoryClient.queryPage).mockReset()
      .mockResolvedValueOnce(STAFF_PAGE_ONE)
      .mockImplementationOnce(() => new Promise(resolve => { resolveNextPage = resolve; }));
    render(<React.StrictMode><StaffPage /></React.StrictMode>);
    expect(await screen.findByText('去敏人員甲')).toBeVisible();
    expect(screen.getByText('目前已載入 2 位，名冊仍在載入')).toBeVisible();
    expect(screen.getByText(/公會編號排序與人數會在載入完成後更新/)).toBeVisible();
    expect(screen.queryByText('去敏人員乙')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '載入下一頁' })).not.toBeInTheDocument();

    resolveNextPage?.({ ...STAFF_PAGE_TWO, items: [{ ...STAFF_PAGE_TWO.items[0], union_no: 'A000' }] });
    expect(await screen.findByText('去敏人員乙')).toBeVisible();
    expect(screen.queryByText(/名冊仍在載入/)).not.toBeInTheDocument();
    expect(screen.getByText('目前已載入 3 位服務人員')).toBeVisible();
    const roster = within(screen.getByRole('table', { name: '月嫂名冊清單' }));
    expect(roster.getAllByRole('row').slice(1).map(row => row.getAttribute('aria-label'))).toEqual([
      '開啟 去敏人員乙 的詳情',
      '開啟 去敏人員甲 的詳情',
      '開啟 服務人員摘要 #12 的詳情',
    ]);
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(2);
    expect(staffDirectoryClient.queryPage).toHaveBeenLastCalledWith(
      { pageSize: 200, afterId: 12, includeProfile:true, lifecycleState: 'active' },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('shows no partial roster and retries the complete query after a page failure', async () => {
    vi.mocked(staffDirectoryClient.queryPage).mockReset()
      .mockResolvedValueOnce(STAFF_PAGE_ONE)
      .mockRejectedValueOnce(new Error('下一頁暫時失敗'))
      .mockResolvedValueOnce(STAFF_PAGE_ONE)
      .mockResolvedValueOnce(STAFF_PAGE_TWO);
    render(<StaffPage />);
    const retry = await screen.findByRole('button', { name: '重試名冊查詢' });
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    fireEvent.click(retry);
    await waitFor(() => expect(screen.getByText('去敏人員乙')).toBeInTheDocument());
    expect(staffDirectoryClient.queryPage).toHaveBeenNthCalledWith(
      4,
      { pageSize: 200, afterId: 12, includeProfile:true, lifecycleState: 'active' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('does not display active roster rows after switching to the retired tab during pagination', async () => {
    let resolveActivePage: ((value: typeof STAFF_PAGE_TWO) => void) | undefined;
    let resolveRetiredPage: ((value: typeof STAFF_PAGE_TWO) => void) | undefined;
    vi.mocked(staffDirectoryClient.queryPage).mockReset()
      .mockResolvedValueOnce(STAFF_PAGE_ONE)
      .mockImplementationOnce(() => new Promise(resolve => { resolveActivePage = resolve; }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveRetiredPage = resolve; }));

    render(<StaffPage />);
    expect(await screen.findByText('去敏人員甲')).toBeVisible();
    const activeSignal = vi.mocked(staffDirectoryClient.queryPage).mock.calls[1][1]?.signal;
    fireEvent.click(screen.getByRole('tab', { name: '已退役月嫂' }));
    expect(screen.queryByText('去敏人員甲')).not.toBeInTheDocument();
    expect(activeSignal?.aborted).toBe(true);
    await waitFor(() => expect(staffDirectoryClient.queryPage).toHaveBeenLastCalledWith(
      { pageSize: 200, includeProfile: true, lifecycleState: 'retired' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));

    resolveActivePage?.(STAFF_PAGE_TWO);
    resolveRetiredPage?.({ ...STAFF_PAGE_TWO, items: [{ ...STAFF_PAGE_TWO.items[0], name: '已退役測試人員' }] });
    expect(await screen.findByText('已退役測試人員')).toBeVisible();
    expect(screen.queryByText('去敏人員乙')).not.toBeInTheDocument();
  });

  it('Drawer interactions add zero directory requests after the full roster loads', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: /查看 .* 的詳情/ })[0]);
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(2);
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
    await waitFor(() => expect(receivedSignal).toBeInstanceOf(AbortSignal));
    view.unmount();
    await Promise.resolve();

    expect(receivedSignal?.aborted).toBe(true);
  });
});
