/**
 * File: scheduling_current_page.test.tsx
 * Description: 驗證 SchedulingPage 真實查詢、request budget、empty/error 與停用操作。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { schedulingCurrentClient } from '../api/scheduling/scheduling_current_client';
import { SchedulingPage } from '../pages/SchedulingPage';
import {
  SCHEDULING_PROJECTION_EMPTY,
  SCHEDULING_PROJECTION_READY,
} from './fixtures/scheduling/scheduling_current_contract_fixtures';

describe('SchedulingPage query-only presentation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({
      items: [
        { id: 11, name: '去敏人員甲', phone: null },
        { id: 12, name: '去敏人員乙', phone: null },
      ],
      next_cursor: null,
    });
    vi.spyOn(schedulingCurrentClient, 'queryCurrentCalendar').mockImplementation(
      async (query) => ({
        ...SCHEDULING_PROJECTION_READY,
        staff_id: query.staffId,
        range_start: query.rangeStart,
        range_end: query.rangeEnd,
        assignments: SCHEDULING_PROJECTION_READY.assignments.map((item) => ({
          ...item,
          staff_id: query.staffId,
        })),
      })
    );
  });

  it('loads one staff page and one selected current calendar, then renders server values', async () => {
    render(<SchedulingPage />);

    expect(screen.getByText(/正在載入服務人員摘要/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    expect(screen.getAllByText('去敏人員甲').length).toBeGreaterThan(0);
    expect(screen.getAllByText('正式服務日').length).toBeGreaterThan(0);
    expect(staffDirectoryClient.queryPage).toHaveBeenCalledTimes(1);
    expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText(/服務人員/), { target: { value: '12' } });
    await waitFor(() =>
      expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenCalledTimes(2)
    );
    expect(schedulingCurrentClient.queryCurrentCalendar).toHaveBeenLastCalledWith(
      expect.objectContaining({ staffId: 12 }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('renders explicit empty and error states', async () => {
    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockResolvedValueOnce(
      SCHEDULING_PROJECTION_EMPTY
    );
    const empty = render(<SchedulingPage />);
    await waitFor(() => expect(screen.getByText(/目前範圍沒有 server projection/)).toBeInTheDocument());
    empty.unmount();

    vi.mocked(schedulingCurrentClient.queryCurrentCalendar).mockRejectedValueOnce(
      new Error('typed scheduling failure')
    );
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('typed scheduling failure'));
  });

  it('keeps non-calendar operations unavailable and native disabled without fake handlers', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));

    expect(document.querySelector('[data-control-id="scheduling.precision.open"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="scheduling.projection.lock"]')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /服務中請假與代班/ }));
    expect(document.querySelector('[data-control-id="scheduling.leave.apply"]')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    expect(document.querySelector('[data-control-id="scheduling.holiday.save"]')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /請假待辦收件匣/ }));
    expect(document.querySelector('[data-control-id="scheduling.leave-inbox.accept"]')).toBeDisabled();
  });
});
