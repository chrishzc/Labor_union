import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import {
  historicalScheduleSegments,
  HistoricalRestartArrangementPanel,
} from '../../../../../../../components/HistoricalRestartArrangementPanel';

const dates = ['2026-09-08', '2026-09-09', '2026-09-11', '2026-09-12'];
const staff = [
  { staff_id: 12, staff_name: '王月嫂' },
  { staff_id: 13, staff_name: '李月嫂' },
];

it('列出既定月嫂及各自可選的服務日期', () => {
  const onSelect = vi.fn();
  render(<HistoricalRestartArrangementPanel staff={staff} dates={dates}
    allocation={{ [dates[0]]: 12 }} disabled={false} onSelect={onSelect} />);

  const first = screen.getByRole('group', { name: /王月嫂/ });
  const second = screen.getByRole('group', { name: /李月嫂/ });
  expect(within(first).getByRole('button', { name: /2026-09-08/ })).toHaveAttribute('aria-pressed', 'true');
  expect(within(second).getByRole('button', { name: /2026-09-08/ })).toBeDisabled();
  fireEvent.click(within(second).getByRole('button', { name: /2026-09-11/ }));
  expect(onSelect).toHaveBeenCalledWith(dates[2], 13);
});

it('只接受每位月嫂各一段連續的服務日序列，非服務日不切斷分段', () => {
  expect(historicalScheduleSegments(staff, dates, {})).toBeNull();
  expect(historicalScheduleSegments(staff, dates, {
    [dates[0]]: 12, [dates[1]]: 13, [dates[2]]: 12, [dates[3]]: 13,
  })).toBeNull();
  expect(historicalScheduleSegments(staff, dates, {
    [dates[0]]: 13, [dates[1]]: 12, [dates[2]]: 12, [dates[3]]: 12,
  })).toEqual([
    { staff_id: 13, service_dates: dates.slice(0, 1) },
    { staff_id: 12, service_dates: dates.slice(1) },
  ]);
});
