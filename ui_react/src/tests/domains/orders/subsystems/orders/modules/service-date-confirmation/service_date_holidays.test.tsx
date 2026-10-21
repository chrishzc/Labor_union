import { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { holidayClient } from '../../../../../../../api/scheduling/holiday_client';
import { OrderServiceDateCalendar } from '../../../../../../../components/OrderServiceDateCalendar';

const holiday = { holiday_date: '2026-10-10', holiday_name: '國慶日', is_double_pay_default: false };
const calendar = { planning_horizon: { from_date: '2026-10-01', to_date: '2026-10-31' }, source_identity: 'test', calendar_version: 'a'.repeat(64), holidays: [holiday] };

beforeEach(() => { vi.spyOn(holidayClient, 'query').mockResolvedValue(calendar); });
afterEach(() => { vi.restoreAllMocks(); });

it('已保存的假日上班日獨立顯示假日名稱，不重新選日', async () => {
  const toggle = vi.fn();
  render(<OrderServiceDateCalendar month="2026-10" onMonthChange={vi.fn()} selectedDates={['2026-10-10']} isDateDisabled={() => false} onToggle={toggle} hint="已保存人工日期" />);
  await screen.findByText('國慶日');
  expect(holidayClient.query).toHaveBeenCalledWith({ from_date: '2026-10-01', to_date: '2026-10-31' }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
  expect(screen.getByRole('button', { name: '服務日期 2026-10-10' })).toHaveAttribute('aria-pressed', 'true');
  expect(toggle).not.toHaveBeenCalled();
});

it('排班前可手動點選假日上班，其他人工日期維持原選取', async () => {
  function EditableCalendar() {
    const [dates, setDates] = useState(['2026-10-09']);
    return <OrderServiceDateCalendar month="2026-10" onMonthChange={vi.fn()} selectedDates={dates} isDateDisabled={() => false}
      onToggle={date => setDates(current => current.includes(date) ? current.filter(value => value !== date) : [...current, date])} hint="人工選日" />;
  }
  render(<EditableCalendar />);
  await screen.findByText('國慶日');
  const day = screen.getByRole('button', { name: '服務日期 2026-10-10' });
  fireEvent.click(day);
  expect(day).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: '服務日期 2026-10-09' })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(day);
  expect(day).toHaveAttribute('aria-pressed', 'false');
});

it('正式排班只顯示假日，不改原排班，也不啟用選日', async () => {
  const toggle = vi.fn();
  render(<OrderServiceDateCalendar month="2026-10" onMonthChange={vi.fn()} selectedDates={['2026-10-10']} isDateDisabled={() => true} onToggle={toggle} hint="正式排班" />);
  await screen.findByText('國慶日');
  const day = screen.getByRole('button', { name: '服務日期 2026-10-10' });
  expect(day).toBeDisabled();
  expect(day).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(day);
  expect(toggle).not.toHaveBeenCalled();
});

it('切換到跨年月份會讀取該月假日，忽略上一個月較晚回來的結果', async () => {
  let resolveOld!: (value: typeof calendar) => void;
  vi.mocked(holidayClient.query).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
    .mockResolvedValueOnce({ ...calendar, holidays: [{ ...holiday, holiday_date: '2027-01-01', holiday_name: '元旦' }] });
  const props = { onMonthChange: vi.fn(), selectedDates: ['2026-10-10'], isDateDisabled: () => false, onToggle: vi.fn(), hint: '保留選日' };
  const view = render(<OrderServiceDateCalendar {...props} month="2026-10" />);
  view.rerender(<OrderServiceDateCalendar {...props} month="2027-01" />);
  await screen.findByText('元旦');
  resolveOld(calendar);
  await waitFor(() => expect(screen.queryByText('國慶日')).not.toBeInTheDocument());
  expect(holidayClient.query).toHaveBeenLastCalledWith({ from_date: '2027-01-01', to_date: '2027-01-31' }, expect.anything());
  expect(props.onToggle).not.toHaveBeenCalled();
});

it('假日讀取失敗可重新查詢，保留人工已選日期', async () => {
  vi.mocked(holidayClient.query).mockRejectedValueOnce(new Error('查詢暫時失敗'));
  const toggle = vi.fn();
  render(<OrderServiceDateCalendar month="2026-10" onMonthChange={vi.fn()} selectedDates={['2026-10-10']} isDateDisabled={() => false} onToggle={toggle} hint="保留選日" />);
  await screen.findByRole('alert');
  expect(screen.getByRole('button', { name: '服務日期 2026-10-10' })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(screen.getByRole('button', { name: '重新讀取假日' }));
  await screen.findByText('國慶日');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(toggle).not.toHaveBeenCalled();
});
