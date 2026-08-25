/**
 * File: staff_directory_page.test.tsx
 * Description: 驗證 StaffPage 真摘要卡片、可操作 lifecycle 入口、empty/error 與摘要 Drawer。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { staffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import { staffQualificationMasterClient } from '../api/staff/qualification_master_client';
import { StaffPage } from '../pages/StaffPage';
import {
  STAFF_PAGE_ONE,
} from './fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from './fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from './fixtures/staff/staff_qualification_contract_fixtures';

describe('StaffPage directory presentation', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
  });

  it('renders server summary values without unsupported placeholders', async () => {
    render(<StaffPage />);

    expect(screen.getByText(/正在載入服務人員摘要名冊/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    expect(screen.getByText('📞 09********')).toBeInTheDocument();
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
    await waitFor(() => expect(within(drawer as HTMLElement).getAllByText('在職').length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByText(/整體狀態/)).toBeInTheDocument());
    const selector = screen.getByLabelText('查詢服務人員');
    expect(selector).toBeDisabled();
    fireEvent.change(selector, { target: { value: '12' } });
    expect(selector).toHaveValue('11');
    expect(within(drawer as HTMLElement).getByText(/#11/)).toBeInTheDocument();
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
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
