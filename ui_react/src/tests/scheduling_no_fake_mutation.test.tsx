/**
 * File: scheduling_no_fake_mutation.test.tsx
 * Description: 驗證 SchedulingPage 國定假日 tab 不自動 mutation，並移除舊未開放控制槽。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { holidayClient } from '../api/scheduling/holiday_client';
import { schedulingCurrentClient } from '../api/scheduling/scheduling_current_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { SchedulingPage } from '../pages/SchedulingPage';
import { SCHEDULING_PROJECTION_READY } from './fixtures/scheduling/scheduling_current_contract_fixtures';

describe('SchedulingPage holiday no fake mutation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({
      items: [{ id: 11, name: '去敏人員甲', phone: null }],
      next_cursor: null,
    });
    vi.spyOn(schedulingCurrentClient, 'queryCurrentCalendar').mockResolvedValue(
      SCHEDULING_PROJECTION_READY,
    );
    vi.spyOn(holidayClient, 'query').mockResolvedValue({
      planning_horizon: { from_date: '2026-01-01', to_date: '2026-12-31' },
      source_identity: 'holiday-test-source',
      calendar_version: 'a'.repeat(64),
      holidays: [],
    });
    vi.spyOn(holidayClient, 'preview');
    vi.spyOn(holidayClient, 'apply');
  });

  it('初次 render 與切換 tab 不自動呼叫 holiday Preview/Apply，舊未開放 controls 不再顯示', async () => {
    render(<SchedulingPage />);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-001').length).toBeGreaterThan(0));
    expect(holidayClient.query).not.toHaveBeenCalled();
    expect(holidayClient.preview).not.toHaveBeenCalled();
    expect(holidayClient.apply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    expect(holidayClient.preview).not.toHaveBeenCalled();
    expect(holidayClient.apply).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '查詢國定假日政策' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '➕ 新增國定假日' }));
    expect(screen.getByRole('button', { name: '套用國定假日變更' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '預覽國定假日變更' })).toBeDisabled();
    expect(document.querySelector('[data-control-id="scheduling.holiday.create"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.holiday.toggle-rest"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.holiday.toggle-pay"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.holiday.delete"]')).not.toBeInTheDocument();
  });
});
