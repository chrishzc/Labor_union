/**
 * File: scheduling_matching_tab_removed.test.tsx
 * Description: 驗證 Scheduling 不再暴露獨立的媒合協調頂層入口。
 */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { SchedulingPage } from '../pages/SchedulingPage';

describe('Scheduling standalone matching navigation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.location.hash = '#scheduling';
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({
      items: [],
      next_cursor: null,
    });
  });

  it('keeps only user-facing scheduling tabs and omits standalone matching coordination', async () => {
    render(<SchedulingPage />);

    expect(screen.getByRole('button', { name: /服務人員排班甘特月曆/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /服務中請假與代班/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /國定假日政策/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /媒合協調/ })).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="scheduling.tab.matching"]')).not.toBeInTheDocument();

    await waitFor(() => expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1));
  });
});
