/**
 * File: scheduling_matching_entry_cutover.test.tsx
 * Description: 驗證排班中心不再提供 standalone 媒合協調入口。
 */
import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { SchedulingPage } from '../pages/SchedulingPage';

describe('Scheduling standalone matching entry cutover', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.location.hash = '#';
  });

  it('keeps only calendar, leave substitution and holiday tabs', () => {
    window.location.hash = '#scheduling';
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [], next_cursor: null });

    render(<SchedulingPage />);

    const navigation = screen.getByRole('navigation', { name: '排班工作區' });
    expect(within(navigation).getAllByRole('button')).toHaveLength(3);
    expect(within(navigation).queryByRole('button', { name: /媒合協調/ })).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="scheduling.tab.matching"]')).toBeNull();
  });
});
