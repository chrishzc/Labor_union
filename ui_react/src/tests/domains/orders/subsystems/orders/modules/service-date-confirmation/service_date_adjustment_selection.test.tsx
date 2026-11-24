import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { OrderServiceDateAdjustment } from '../../../../../../../components/OrderServiceDateAdjustment';
import type { ServiceDateAdjustmentQuery } from '../../../../../../../api/orders/order_mutation_schemas';

const mutations = vi.hoisted(() => ({ preview: vi.fn(), apply: vi.fn() }));
vi.mock('../../../../../../../api/orders/order_mutation_client', () => ({
  previewServiceDateAdjustment: mutations.preview,
  applyServiceDateAdjustment: mutations.apply,
}));

type Day = ServiceDateAdjustmentQuery['days'][number];
const first: Day = { service_date: '2026-10-01', staff_id: 3, hours_override: 4, service_hours: 4 };
const second: Day = { ...first, service_date: '2026-10-02' };
const independent: Day = { ...first, service_date: '2026-10-03' };
const other: Day = { ...first, service_date: '2026-10-04' };
const original: Day = { ...first, service_date: '2026-10-05', hours_override: null, service_hours: 8 };
const merged: Day = { ...first, service_date: '2026-10-06', hours_override: 8, service_hours: 8 };
const query: ServiceDateAdjustmentQuery = {
  days: [first, second, independent, other],
  staff: [{ staff_id: 3, staff_name: '陳月嫂' }],
  pairs: [{ receipt_id: 41, removed: [original], inserted: [first, second] }],
  total_hours: 16,
  contracted_daily_hours: 8,
  first_schedule_days: [],
};
const preview = {
  order_version: 1, scheduling_version: 5, confirmed_version: null, preview_fingerprint: 'a'.repeat(64),
  removed: [independent, other], inserted: [merged],
};

beforeEach(() => {
  mutations.preview.mockReset().mockResolvedValue(preview);
  mutations.apply.mockReset().mockResolvedValue({ receipt_id: 42, scheduling_version: 6, confirmed_version: null });
});

function editor(currentQuery = query) {
  render(<OrderServiceDateAdjustment caseNo="ADJUST-SELECTION" query={currentQuery}
    onCancel={vi.fn()} onSaved={vi.fn().mockResolvedValue(undefined)} />);
  return within(screen.getByRole('group', { name: '合併或分裂日期' }));
}

function chooseTarget(adjust: ReturnType<typeof editor>) {
  fireEvent.change(adjust.getByLabelText('套用日期'), { target: { value: merged.service_date } });
  fireEvent.change(adjust.getByRole('combobox', { name: '服務月嫂' }), { target: { value: '3' } });
}

it('逐日排班僅有 4 小時時直接開啟合併，先填套用日期仍須選滿兩日', () => {
  const adjust = editor();
  expect(adjust.getByRole('heading', { name: '合併服務日期' })).toBeInTheDocument();
  expect(adjust.getByText('合併日期 4+4→8')).toBeInTheDocument();
  expect(adjust.queryByRole('button', { name: /合併日期|分裂日期/ })).not.toBeInTheDocument();
  expect(adjust.getByRole('heading', { name: '選擇要合併的日期' })).toBeInTheDocument();
  expect(adjust.getByRole('heading', { name: '選擇要套用的日期' })).toBeInTheDocument();
  chooseTarget(adjust);
  expect(adjust.getByText('請先完成步驟1的日期選擇。')).toBeInTheDocument();
  expect(adjust.getByRole('button', { name: '儲存日期調整' })).toBeDisabled();
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${independent.service_date}` }));
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${other.service_date}` }));
  expect(adjust.getByText('已選 2/2')).toBeInTheDocument();
  expect(adjust.getByRole('button', { name: '儲存日期調整' })).toBeEnabled();
  fireEvent.click(adjust.getByRole('button', { name: `移除 ${independent.service_date}` }));
  expect(adjust.getByRole('button', { name: '儲存日期調整' })).toBeDisabled();
  expect(mutations.preview).not.toHaveBeenCalled();
});

it('逐日排班僅有 8 小時時直接開啟分裂，也可復原已合併的服務日', async () => {
  const adjust = editor({
    ...query, days: [merged], contracted_daily_hours: 4, total_hours: 8,
    pairs: [{ receipt_id: 42, removed: [first, second], inserted: [merged] }],
  });
  expect(adjust.getByRole('heading', { name: '分裂服務日期' })).toBeInTheDocument();
  expect(adjust.getByText('分裂日期 8→4+4')).toBeInTheDocument();
  expect(adjust.queryByRole('button', { name: /合併日期|分裂日期/ })).not.toBeInTheDocument();
  expect(adjust.getByLabelText('第2天日期')).toBeInTheDocument();
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${merged.service_date}` }));
  const restore = adjust.getByRole('region', { name: '復原原來的服務日期' });
  expect(restore).toHaveTextContent(`${first.service_date}・陳月嫂・4 小時`);
  expect(restore).toHaveTextContent(`${second.service_date}・陳月嫂・4 小時`);
  expect(adjust.queryByLabelText('第2天日期')).not.toBeInTheDocument();
  mutations.preview.mockResolvedValue({ ...preview, removed: [merged], inserted: [first, second] });
  fireEvent.click(adjust.getByRole('button', { name: '儲存日期調整' }));
  await waitFor(() => expect(mutations.apply).toHaveBeenCalledTimes(1));
  expect(mutations.preview).toHaveBeenCalledWith('ADJUST-SELECTION', {
    source_dates: [merged.service_date], targets: [], reverse_receipt_id: 42,
  });
});

it('符合條件的 4 與 8 小時排班並存時可切換操作', () => {
  const adjust = editor({ ...query, days: [...query.days, original], total_hours: 24 });
  const merge = adjust.getByRole('button', { name: /合併日期/ });
  const split = adjust.getByRole('button', { name: /分裂日期/ });
  expect(merge).toHaveAttribute('aria-pressed', 'true');
  expect(adjust.getByRole('button', { name: `服務日期 ${original.service_date}` })).toBeDisabled();
  fireEvent.click(split);
  expect(split).toHaveAttribute('aria-pressed', 'true');
  expect(adjust.getByRole('button', { name: `服務日期 ${original.service_date}` })).toBeEnabled();
  expect(adjust.getByRole('button', { name: `服務日期 ${first.service_date}` })).toBeDisabled();
  expect(adjust.getByLabelText('第1天服務月嫂')).toBeEnabled();
  fireEvent.click(merge);
  expect(adjust.getByLabelText('套用日期')).toBeEnabled();
});

it.each([
  { name: '只有 9 小時', additionalDays: [] },
  { name: '另有一個 4 小時日', additionalDays: [first] },
])('逐日排班 $name 時顯示空態', ({ additionalDays }) => {
  const nineHours = { ...original, service_hours: 9 };
  const adjust = editor({ ...query, days: [nineHours, ...additionalDays], pairs: [], total_hours: 9 + additionalDays.length * 4 });
  expect(adjust.getByText('目前沒有可合併的 4 小時日期或可分裂的 8 小時日期。')).toBeInTheDocument();
  expect(adjust.getAllByRole('button')).toHaveLength(1);
  expect(adjust.getByRole('button', { name: '取消日期調整' })).toBeEnabled();
});

it('查詢更新後切換成可用操作，並清除舊操作的草稿', () => {
  const onSaved = vi.fn();
  const onCancel = vi.fn();
  const { rerender } = render(<OrderServiceDateAdjustment caseNo="ADJUST-SELECTION" query={query}
    onCancel={onCancel} onSaved={onSaved} />);
  const adjust = within(screen.getByRole('group', { name: '合併或分裂日期' }));
  chooseTarget(adjust);
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${independent.service_date}` }));
  rerender(<OrderServiceDateAdjustment caseNo="ADJUST-SELECTION"
    query={{ ...query, days: [original], pairs: [], total_hours: 8 }} onCancel={onCancel} onSaved={onSaved} />);
  expect(adjust.getByRole('heading', { name: '分裂服務日期' })).toBeInTheDocument();
  expect(adjust.getByText('已選 0/1')).toBeInTheDocument();
  expect(adjust.getByLabelText('第1天日期')).toHaveValue('');
});

it('離開復原配對後只合併新選取的兩個服務日', async () => {
  const adjust = editor();
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${first.service_date}` }));
  expect(adjust.getByRole('region', { name: '復原原來的服務日期' })).toBeInTheDocument();

  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${independent.service_date}` }));
  expect(adjust.queryByRole('region', { name: '復原原來的服務日期' })).not.toBeInTheDocument();
  for (const day of [first, second]) {
    expect(adjust.getByRole('button', { name: `服務日期 ${day.service_date}` })).toHaveAttribute('aria-pressed', 'false');
  }
  expect(adjust.getByRole('button', { name: '儲存日期調整' })).toBeDisabled();

  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${other.service_date}` }));
  chooseTarget(adjust);
  fireEvent.click(adjust.getByRole('button', { name: '儲存日期調整' }));
  await waitFor(() => expect(mutations.apply).toHaveBeenCalledTimes(1));
  expect(mutations.preview).toHaveBeenCalledWith('ADJUST-SELECTION', {
    source_dates: [independent.service_date, other.service_date],
    targets: [{ service_date: merged.service_date, staff_id: 3 }], reverse_receipt_id: null,
  });
});

it.each([first.service_date, second.service_date])('選取 %s 仍可復原整組分裂日期', async source => {
  mutations.preview.mockResolvedValue({ ...preview, removed: [first, second], inserted: [original] });
  const adjust = editor();
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${source}` }));
  for (const day of [first, second]) {
    expect(adjust.getByRole('button', { name: `服務日期 ${day.service_date}` })).toHaveAttribute('aria-pressed', 'true');
  }
  expect(adjust.getByRole('region', { name: '復原原來的服務日期' })).toHaveTextContent(original.service_date);
  fireEvent.click(adjust.getByRole('button', { name: '儲存日期調整' }));
  await waitFor(() => expect(mutations.apply).toHaveBeenCalledTimes(1));
  expect(mutations.preview).toHaveBeenCalledWith('ADJUST-SELECTION', {
    source_dates: [source], targets: [], reverse_receipt_id: 41,
  });
});

it('指定新日期時可合併一個分裂結果與另一個服務日', async () => {
  const adjust = editor();
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${first.service_date}` }));
  fireEvent.click(adjust.getByRole('button', { name: '改為指定新日期' }));
  fireEvent.click(adjust.getByRole('button', { name: `服務日期 ${independent.service_date}` }));
  expect(adjust.queryByRole('region', { name: '復原原來的服務日期' })).not.toBeInTheDocument();
  chooseTarget(adjust);
  fireEvent.click(adjust.getByRole('button', { name: '儲存日期調整' }));
  await waitFor(() => expect(mutations.apply).toHaveBeenCalledTimes(1));
  expect(mutations.preview).toHaveBeenCalledWith('ADJUST-SELECTION', {
    source_dates: [first.service_date, independent.service_date],
    targets: [{ service_date: merged.service_date, staff_id: 3 }], reverse_receipt_id: null,
  });
});
