/**
 * File: staff_directory_page.test.tsx
 * Description: 驗證 StaffPage 真摘要卡片、unavailable 槽位、empty/error 與摘要 Drawer。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { StaffPage } from '../pages/StaffPage';
import {
  STAFF_PAGE_ONE,
} from './fixtures/staff/staff_directory_contract_fixtures';

describe('StaffPage directory presentation', () => {
  beforeEach(() => {
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue(STAFF_PAGE_ONE);
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
  });

  it('renders server summary values and unavailable slots', async () => {
    render(<StaffPage />);

    expect(screen.getByText(/正在載入服務人員摘要名冊/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    expect(screen.getByText('📞 09********')).toBeInTheDocument();
    expect(screen.getByText('服務人員摘要 #12')).toBeInTheDocument();
    expect(screen.getAllByText(/後端尚未提供 typed contract/).length).toBeGreaterThan(3);
    expect(document.querySelector('[data-control-id="staff.card.11"]')).toBeVisible();
  });

  it('opens summary drawer without another query', async () => {
    render(<StaffPage />);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: /檢視摘要/ })[0]);

    expect(screen.getByText(/服務人員摘要 - 去敏人員甲/)).toBeInTheDocument();
    expect(screen.getByText(/#11/)).toBeInTheDocument();
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
  });
});

