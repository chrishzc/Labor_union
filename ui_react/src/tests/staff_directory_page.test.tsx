/**
 * File: staff_directory_page.test.tsx
 * Description: 驗證 StaffPage 摘要、跨頁搜尋、stale guard、empty/error 與 Drawer。
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import { staffQualificationMasterClient } from '../api/staff/qualification_master_client';
import { StaffPage } from '../pages/StaffPage';
import {
  STAFF_PAGE_ONE,
  STAFF_PAGE_TWO,
} from './fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from './fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from './fixtures/staff/staff_qualification_contract_fixtures';

describe('StaffPage directory presentation', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockImplementation((params) => (
      Promise.resolve(params?.afterId ? STAFF_PAGE_TWO : STAFF_PAGE_ONE)
    ));
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
  });

  it('renders approved server summary values including education without unsupported placeholders', async () => {
    render(<StaffPage />);

    expect(screen.getByText(/正在載入服務人員摘要名冊/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    expect(screen.getByText('📞 09******** · 🎓 大學')).toBeInTheDocument();
    expect(screen.getByText('服務人員摘要 #12')).toBeInTheDocument();
    expect(screen.getByText('目前已載入 2 位服務人員')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '🟢 在職中' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '🏖️ 請長假' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '⏸️ 暫停接案' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '⚪ 已退役' })).not.toBeInTheDocument();
    expect(screen.queryByText(/未開放|後端.*提供|unavailable|資料待補/)).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '辦理退役／復職' })[0]).toBeEnabled();
    expect(document.querySelector('[data-control-id="staff.card.11"]')).toBeVisible();
  });

  it('opens summary drawer without another query', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: /檢視服務人員摘要/ })[0]);

    const drawer = screen.getByText(/服務人員摘要 - 去敏人員甲/).closest('.drawer-container');
    expect(drawer).not.toBeNull();
    expect(within(drawer as HTMLElement).getByText(/#11/)).toBeInTheDocument();
    expect(within(drawer as HTMLElement).getByText(/聯絡電話：09\*{8} · 🎓 大學/)).toBeInTheDocument();
    await waitFor(() => expect(within(drawer as HTMLElement).getAllByText('在職').length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByText(/整體狀態/)).toBeInTheDocument());
    const selector = screen.getByLabelText('查詢服務人員');
    expect(selector).toBeDisabled();
    fireEvent.change(selector, { target: { value: '12' } });
    expect(selector).toHaveValue('11');
    expect(within(drawer as HTMLElement).getByText(/#11/)).toBeInTheDocument();
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
  });

  it('shows a clearable empty state when the loaded directory has no search match', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('即時搜尋月嫂'), { target: { value: '不存在的人員' } });
    await waitFor(() => expect(screen.getByText('找不到符合「不存在的人員」的服務人員。')).toBeInTheDocument());
    expect(document.querySelector('.staff-grid')).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: '清除搜尋' })[0]);
    expect(screen.getByText('去敏人員甲')).toBeInTheDocument();
  });

  it('搜尋時續讀 cursor，能找到初始頁面以外的人員', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('即時搜尋月嫂'), { target: { value: '去敏人員乙' } });

    await waitFor(() => expect(screen.getByText('去敏人員乙')).toBeInTheDocument());
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledWith(
      { pageSize: 200, afterId: 12 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('較舊搜尋回應不會覆蓋較新的查詢結果', async () => {
    let resolveStale: ((value: typeof STAFF_PAGE_TWO) => void) | undefined;
    vi.mocked(staffDirectoryClient.queryPage).mockReset()
      .mockResolvedValueOnce(STAFF_PAGE_ONE)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveStale = resolve; }))
      .mockResolvedValueOnce(STAFF_PAGE_ONE)
      .mockResolvedValueOnce(STAFF_PAGE_TWO);
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('即時搜尋月嫂'), { target: { value: '過期結果' } });
    await waitFor(() => expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByLabelText('即時搜尋月嫂'), { target: { value: '去敏人員乙' } });
    await waitFor(() => expect(screen.getByText('去敏人員乙')).toBeInTheDocument());

    await act(async () => {
      resolveStale?.({ items: [{ id: 99, name: '過期結果', phone: null, education: null }], next_cursor: null });
      await Promise.resolve();
    });
    expect(screen.queryByText('過期結果')).not.toBeInTheDocument();
    expect(screen.getByText('去敏人員乙')).toBeInTheDocument();
  });

  it('renders explicit empty and error states', async () => {
    vi.mocked(staffDirectoryClient.queryPage).mockResolvedValueOnce({
      items: [],
      next_cursor: null,
    });
    const empty = render(<StaffPage />);
    await waitFor(() => expect(screen.getByText(/目前沒有可顯示/)).toBeInTheDocument());
    empty.unmount();

    vi.mocked(staffDirectoryClient.queryPage).mockRejectedValueOnce(new Error('typed failure'));
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('typed failure'));
    fireEvent.click(screen.getByRole('button', { name: '重試名冊查詢' }));
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
  });
});
