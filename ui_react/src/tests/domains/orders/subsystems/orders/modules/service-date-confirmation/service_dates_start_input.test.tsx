import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderServiceDatesPanel } from '../../../../../../../components/OrderServiceDatesPanel';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { serviceDatesNeedCompletion } from '../../../../../../../adapters/orders/service_date_start_flow';
import type { ActualStartPreview } from '../../../../../../../api/orders/order_actual_start_client';

const mocks = vi.hoisted(() => ({ getStart: vi.fn(), getCalendar: vi.fn(), getDates: vi.fn(), calculate: vi.fn(),
  previewStart: vi.fn(), applyStart: vi.fn(), previewDates: vi.fn(), applyDates: vi.fn(), holidayQuery: vi.fn() }));
vi.mock('../../../../../../../api/scheduling/holiday_client', () => ({ holidayClient: { query: mocks.holidayQuery } }));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getActualStart: mocks.getStart, getOrderCalendarDetail: mocks.getCalendar } }));
vi.mock('../../../../../../../api/orders/order_actual_start_client', () => ({ orderActualStartClient: { preview: mocks.previewStart, apply: mocks.applyStart } }));
vi.mock('../../../../../../../api/orders/order_mutation_client', () => ({ ordersMutationClient: { getServiceDates: mocks.getDates, previewServiceDates: mocks.previewDates, applyServiceDates: mocks.applyDates } }));
vi.mock('../../../../../../../api/scheduling/schedule_precision_client', () => ({ schedulePrecisionClient: { calculate: mocks.calculate } }));

const CASE = 'ISSUE-335';
const fp = 'a'.repeat(64);
let actual: string | null;
let orderVersion: number;
let confirmedVersion: number | null;
let confirmedDates: string[];
let serviceMode: string;
const days = (start: string, count: number) => Array.from({ length: count }, (_, i) => new Date(Date.parse(`${start}T00:00:00Z`) + i * 86400000).toISOString().slice(0, 10));
const datesQuery = () => ({ case_no: CASE, order_version: orderVersion, scheduling_version: 0,
  contracted_service_days: 3, suggested_dates: [], selectable_dates: days(actual ?? '2026-10-01', 33), current_version: confirmedVersion,
  current_dates: confirmedDates, bound_staff: [], arrangement_pending: false });
const startQuery = () => ({ case_no: CASE, current_actual_start_date: actual, planned_start_date: '2026-10-01', service_data_locked: false,
  order_version: orderVersion, scheduling_version: null, scheduling_generation: null, client_finance_version: null, payroll_version: null, has_formal_assignments: false });
const startCandidate = (date: string): ActualStartPreview => ({ operation: 'date_only', case_no: CASE, before_actual_start_date: actual,
  after_actual_start_date: date, order_version: orderVersion, scheduling_version: null, scheduling_generation: null,
  client_finance_version: null, payroll_version: null, preview_fingerprint: fp });
const result = (start: string) => ({ actual_start_date: start, actual_end_date: days(start, 3)[2], target_service_days: 3,
  total_calendar_days: 3, actual_work_days_count: 3, rest_days_count: 0, national_holidays_found: [], total_estimated_salary: null,
  weekly_stats: [], day_by_day: days(start, 3).map((date, i) => ({ date, day_num: i + 1, is_work_day: true, is_rest_day: false, holiday_name: null })) });

beforeEach(() => {
  Object.values(mocks).forEach((mock) => mock.mockReset());
  mocks.holidayQuery.mockResolvedValue({ holidays: [] });
  orderMutationFlowStore.clearAll(); actual = null; orderVersion = 1; confirmedVersion = null; confirmedDates = []; serviceMode = '連續服務';
  mocks.getStart.mockImplementation(async () => startQuery());
  mocks.getCalendar.mockImplementation(async () => ({ case_no: CASE, service_mode: serviceMode }));
  mocks.getDates.mockImplementation(async () => datesQuery());
  mocks.calculate.mockImplementation(async ({ actual_start_date }) => result(actual_start_date));
  mocks.previewStart.mockImplementation(async (_case, { new_actual_start_date }) => startCandidate(new_actual_start_date));
  mocks.applyStart.mockImplementation(async (_case, payload) => {
    if (payload.expected_order_version !== orderVersion) throw new ApiHttpError(409, 'order_version_conflict', '案件已更新');
    actual = payload.new_actual_start_date; orderVersion++;
    return { operation: 'date_only', case_no: CASE, actual_start_date: actual, order_version: orderVersion,
      scheduling_version: null, scheduling_generation: null, client_finance_version: null, payroll_version: null, preview_fingerprint: fp, changed: true };
  });
  mocks.previewDates.mockImplementation(async (_case, { service_dates }) => {
    if (service_dates.some((date: string) => !datesQuery().selectable_dates.includes(date))) throw new Error('outside range');
    return { case_no: CASE, order_version: orderVersion, scheduling_version: 0, current_version: confirmedVersion,
      service_dates, weeks: [], preview_fingerprint: fp };
  });
  mocks.applyDates.mockImplementation(async (_case, payload) => {
    if (payload.expected_order_version !== orderVersion) throw new ApiHttpError(409, 'stale_preview', '案件已更新');
    confirmedDates = payload.service_dates; confirmedVersion = (confirmedVersion ?? 0) + 1;
    return { case_no: CASE, confirmed_version: confirmedVersion, order_version: orderVersion, scheduling_version: 0,
      service_dates: confirmedDates, preview_fingerprint: fp };
  });
});

it('排班前建議跳過假日，人工選假日上班後可保存並保留到重新開啟', async () => {
  actual = '2026-10-01';
  mocks.holidayQuery.mockResolvedValue({ holidays: [{ holiday_date: '2026-10-02', holiday_name: '測試國定假日', is_double_pay_default: false }] });
  mocks.calculate.mockImplementation(async ({ actual_start_date }) => ({ ...result(actual_start_date), actual_end_date: '2026-10-04',
    day_by_day: days('2026-10-01', 4).map((date, index) => ({ date, day_num: index + 1, is_work_day: date !== '2026-10-02', is_rest_day: date === '2026-10-02', holiday_name: date === '2026-10-02' ? '測試國定假日' : null })) }));
  const view = render(<OrderServiceDatesPanel caseNo={CASE} />);
  await waitFor(() => expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('3 / 3 天'));
  await screen.findByText('測試國定假日');
  const holiday = screen.getByRole('button', { name: '服務日期 2026-10-02' });
  expect(holiday).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(holiday);
  fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-04' }));
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '儲存服務日期' })); });
  await screen.findByText('服務日期已確認並回讀版本 #1。');
  expect(confirmedDates).toEqual(['2026-10-01', '2026-10-02', '2026-10-03']);
  const calculationCount = mocks.calculate.mock.calls.length;
  view.unmount();
  render(<OrderServiceDatesPanel caseNo={CASE} />);
  await screen.findByLabelText('已確認服務日期回讀');
  await screen.findByText('測試國定假日');
  expect(screen.getByRole('button', { name: '服務日期 2026-10-02' })).toHaveAttribute('aria-pressed', 'true');
  expect(mocks.calculate).toHaveBeenCalledTimes(calculationCount);
});

async function input(date: string) {
  await waitFor(() => expect(screen.getByLabelText('實際開始日')).toHaveValue('2026-10-01'));
  fireEvent.change(screen.getByLabelText('實際開始日'), { target: { value: date } });
  await waitFor(() => expect(mocks.calculate).toHaveBeenLastCalledWith(expect.objectContaining({ actual_start_date: date })));
  await waitFor(() => expect(screen.getByLabelText('建議服務日期摘要')).toHaveTextContent(date));
}

it('calculates an empty calendar without writing and saves the unchanged default start through the owner flow', async () => {
  render(<OrderServiceDatesPanel caseNo={CASE} />);
  await waitFor(() => expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('3 / 3 天'));
  expect(actual).toBeNull();
  expect(mocks.applyStart).not.toHaveBeenCalled();
  expect(mocks.applyDates).not.toHaveBeenCalled();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '儲存服務日期' })); });
  await screen.findByText('服務日期已確認並回讀版本 #1。');
  expect(actual).toBe('2026-10-01');
  expect(confirmedDates).toEqual(days('2026-10-01', 3));
  expect(mocks.applyStart).toHaveBeenCalledTimes(1);
});

it('preserves saved manual dates on first read while still confirming a missing actual start when explicitly saved', async () => {
  confirmedDates = ['2026-10-01', '2026-10-03', '2026-10-06']; confirmedVersion = 2;
  render(<OrderServiceDatesPanel caseNo={CASE} />);
  await screen.findByLabelText('已確認服務日期回讀');
  expect(mocks.calculate).not.toHaveBeenCalled();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '儲存服務日期' })); });
  await screen.findByText('服務日期已確認並回讀版本 #3。');
  expect(actual).toBe('2026-10-01');
  expect(confirmedDates).toEqual(['2026-10-01', '2026-10-03', '2026-10-06']);
});
async function confirm() {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '儲存服務日期' })); });
}

describe('#335 direct start input and existing writer integration', () => {
  it('對照原始服務方式勾選星期立即重排，人工確認才保存日期，重開不保存星期選項', async () => {
    mocks.getCalendar.mockResolvedValue({ case_no: CASE, service_mode: null, original_service_type: '休五、日' });
    mocks.calculate.mockImplementation(async ({ actual_start_date, custom_rest_weekdays }) => {
      const selected = days(actual_start_date, 30).filter((value) => !custom_rest_weekdays.includes((new Date(value + 'T00:00:00Z').getUTCDay() + 6) % 7)).slice(0, 3);
      return { ...result(actual_start_date), actual_end_date: selected[2], day_by_day: selected.map((date, i) => ({ date, day_num: i + 1, is_work_day: true, is_rest_day: false, holiday_name: null })) };
    });
    const view = render(<OrderServiceDatesPanel caseNo={CASE} />);
    await waitFor(() => expect(screen.getByLabelText('原訂服務方式')).toHaveTextContent('休五、日'));
    expect(mocks.calculate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox', { name: '星期五' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '星期日' }));
    await waitFor(() => expect(mocks.calculate).toHaveBeenLastCalledWith({ case_no: CASE,
      actual_start_date: '2026-10-01', target_service_days: 3, service_mode: '休五、日', custom_rest_weekdays: [4, 6] }));
    await waitFor(() => expect(screen.getByRole('button', { name: '服務日期 2026-10-05' })).toHaveAttribute('aria-pressed', 'true'));
    expect(screen.getByRole('button', { name: '服務日期 2026-10-02' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: '服務日期 2026-10-04' })).toHaveAttribute('aria-pressed', 'false');
    expect(mocks.applyStart).not.toHaveBeenCalled(); expect(mocks.applyDates).not.toHaveBeenCalled();
    await confirm();
    await screen.findByText('服務日期已確認並回讀版本 #1。');
    expect(mocks.applyDates.mock.calls[0][1].service_dates).toEqual(['2026-10-01', '2026-10-03', '2026-10-05']);
    expect(mocks.applyDates.mock.calls[0][1]).not.toHaveProperty('custom_rest_weekdays');
    view.unmount();
    const calls = mocks.calculate.mock.calls.length;
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    await screen.findByLabelText('已確認服務日期回讀');
    expect(screen.getByLabelText('原訂服務方式')).toHaveTextContent('休五、日');
    expect(screen.getByRole('checkbox', { name: '星期五' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: '星期日' })).not.toBeChecked();
    expect(mocks.calculate).toHaveBeenCalledTimes(calls);
  });

  it('七天全休會停止計算及確認，不提交保存', async () => {
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    await waitFor(() => expect(screen.getByLabelText('實際開始日')).toHaveValue('2026-10-01'));
    for (const label of ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']) {
      fireEvent.click(screen.getByRole('checkbox', { name: label }));
    }
    await screen.findByText('不能將每週七天全部設為休假，請保留至少一天服務日。');
    expect(mocks.applyDates).not.toHaveBeenCalled(); expect(mocks.applyStart).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeDisabled();
    expect(mocks.calculate.mock.calls.every(([request]) => (request.custom_rest_weekdays?.length ?? 0) < 7)).toBe(true);
  });

  it('快速變更休假星期時，較晚返回的舊建議不能覆蓋新日曆或恢复舊預覽', async () => {
    let resolve!: (value: ReturnType<typeof result>) => void;
    mocks.calculate.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    await waitFor(() => expect(screen.getByLabelText('實際開始日')).toHaveValue('2026-10-01'));
    fireEvent.click(screen.getByRole('checkbox', { name: '星期五' }));
    await waitFor(() => expect(mocks.calculate).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('checkbox', { name: '星期日' }));
    await screen.findByLabelText('建議服務日期摘要');
    await act(async () => resolve(result('2026-10-15')));
    expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('2026-10-01');
    expect(screen.getByLabelText('人工選定休假星期')).toHaveTextContent('此次休假：星期五、星期日');
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeEnabled();
    expect(mocks.applyStart).not.toHaveBeenCalled();
    expect(mocks.applyDates).not.toHaveBeenCalled();
  });

  it.each(['2026-09-28', '2026-10-15', '2026-10-31'])('自動以 %s 試算，核對前零寫入，保存後用新版本接續並可重新開啟', async (date) => {
    const onObserved = vi.fn();
    const view = render(<OrderServiceDatesPanel caseNo={CASE} onObserved={onObserved} />);
    await input(date);
    expect(mocks.calculate).toHaveBeenLastCalledWith(expect.objectContaining({ actual_start_date: date }));
    expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent(days(date, 3)[2]);
    expect(screen.getByRole('button', { name: `服務日期 ${date}` })).toHaveAttribute('aria-pressed', 'true');
    expect(mocks.applyStart).not.toHaveBeenCalled(); expect(mocks.applyDates).not.toHaveBeenCalled();
    await confirm();
    await screen.findByText('服務日期已確認並回讀版本 #1。');
    expect(mocks.applyStart).toHaveBeenCalledTimes(1);
    expect(mocks.applyDates).toHaveBeenCalledWith(CASE, expect.objectContaining({ expected_order_version: 2, service_dates: days(date, 3) }), expect.anything());
    const calculations = mocks.calculate.mock.calls.length;
    view.unmount(); render(<OrderServiceDatesPanel caseNo={CASE} />);
    await waitFor(() => expect(screen.getByLabelText('實際開始日')).toHaveValue(date));
    expect(screen.getByLabelText('已確認服務日期回讀')).toHaveTextContent(days(date, 3).join('、'));
    expect(mocks.calculate).toHaveBeenCalledTimes(calculations);
    expect(onObserved).toHaveBeenCalled();
  });

  it('人工換日立即更新選定完工；開始日改變保留人工選日直到明確採用新建議', async () => {
    render(<OrderServiceDatesPanel caseNo={CASE} />); await input('2026-09-28');
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-09-30' }));
    fireEvent.click(screen.getByRole('button', { name: '下一個月' }));
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-02' }));
    expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('2026-10-02');
    fireEvent.change(screen.getByLabelText('實際開始日'), { target: { value: '2026-10-15' } });
    await screen.findByRole('button', { name: '採用新建議' });
    expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('2026-09-28');
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '採用新建議' }));
    expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('2026-10-17');
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeEnabled();
  });

  it('單獨更正開始日後重新讀取仍要求核對舊人工選日，並可採用新建議', async () => {
    const view = render(<OrderServiceDatesPanel caseNo={CASE} />);
    await input('2026-09-28');
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-09-30' }));
    fireEvent.click(screen.getByRole('button', { name: '下一個月' }));
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-02' }));
    fireEvent.change(screen.getByLabelText('實際開始日'), { target: { value: '2026-10-15' } });
    await screen.findByRole('button', { name: '採用新建議' });
    fireEvent.click(screen.getByRole('button', { name: '儲存實際開始日' }));
    await screen.findByText('實際開始日已儲存；服務日期尚未儲存。');
    view.unmount();
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    const adopt = await screen.findByRole('button', { name: '採用新建議' });
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeDisabled();
    fireEvent.click(adopt);
    expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('2026-10-17');
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeEnabled();
  });

  it('開始日成功而服務日期 Preview 失敗，關閉重開保留部分結果並接續，開始日只保存一次', async () => {
    mocks.previewDates.mockRejectedValueOnce(new Error('服務日期核對暫時失敗'));
    const view = render(<OrderServiceDatesPanel caseNo={CASE} />); await input('2026-09-28'); await confirm();
    await screen.findByText(/實際開始日已保存，服務日期尚未完成/);
    view.unmount(); render(<OrderServiceDatesPanel caseNo={CASE} />);
    await screen.findByText(/服務日期尚未完成，請接續核對保存/);
    await confirm(); await screen.findByText('服務日期已確認並回讀版本 #1。');
    expect(mocks.applyStart).toHaveBeenCalledTimes(1); expect(mocks.applyDates).toHaveBeenCalledTimes(1);
  });

  it('開始日已保存但回應遺失，先查詢結果再接續，不重送已成功的開始日', async () => {
    mocks.applyStart.mockImplementationOnce(async (_case, payload) => { actual = payload.new_actual_start_date; orderVersion++; throw new Error('network lost'); });
    render(<OrderServiceDatesPanel caseNo={CASE} />); await input('2026-09-28'); await confirm();
    fireEvent.click(await screen.findByRole('button', { name: '讀取開始日結果並接續保存' }));
    await screen.findByText('服務日期已確認並回讀版本 #1。');
    expect(mocks.applyStart).toHaveBeenCalledTimes(1);
  });

  it('服務日期保存成功但回讀失敗，只重新讀取服務日期，不重送任一寫入', async () => {
    const normalApply = mocks.applyDates.getMockImplementation()!;
    mocks.applyDates.mockImplementationOnce(async (...args) => {
      const receipt = await normalApply(...args); mocks.getDates.mockRejectedValueOnce(new Error('read unavailable')); return receipt;
    });
    render(<OrderServiceDatesPanel caseNo={CASE} />); await input('2026-09-28'); await confirm();
    fireEvent.click(await screen.findByRole('button', { name: '只重新讀取服務日期結果' }));
    await screen.findByText('服務日期已確認並回讀版本 #1。');
    expect(mocks.applyStart).toHaveBeenCalledTimes(1); expect(mocks.applyDates).toHaveBeenCalledTimes(1);
  });

  it('核對後他人修改 Orders，拒絕開始日保存且不提交服務日期', async () => {
    render(<OrderServiceDatesPanel caseNo={CASE} />); await input('2026-09-28');
    orderVersion++;
    await confirm();
    await screen.findByText(/已重新讀取正式資料/); expect(mocks.applyDates).not.toHaveBeenCalled(); expect(actual).toBeNull();
    expect(screen.getByLabelText('實際開始日')).toHaveValue('2026-09-28');
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeDisabled();
  });

  it('延遲 D1 試算不能覆蓋 D2，且輸入清空即停用舊核對', async () => {
    let resolve!: (value: ReturnType<typeof result>) => void;
    mocks.calculate.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    await waitFor(() => expect(screen.getByLabelText('實際開始日')).toHaveValue('2026-10-01'));
    fireEvent.change(screen.getByLabelText('實際開始日'), { target: { value: '2026-09-28' } });
    await waitFor(() => expect(mocks.calculate).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText('實際開始日'), { target: { value: '2026-10-15' } });
    await screen.findByLabelText('建議服務日期摘要');
    await act(async () => resolve(result('2026-09-28')));
    expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('2026-10-15');
    fireEvent.change(screen.getByLabelText('實際開始日'), { target: { value: '' } });
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeDisabled();
  });

  it('精算超出既有範圍時明示原因，不能靜默裁掉日期或寫入', async () => {
    mocks.calculate.mockResolvedValue({ ...result('2026-09-28'), day_by_day: result('2026-12-20').day_by_day });
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    await waitFor(() => expect(screen.getByLabelText('實際開始日')).toHaveValue('2026-10-01'));
    fireEvent.change(screen.getByLabelText('實際開始日'), { target: { value: '2026-09-28' } });
    await screen.findByText(/精算結果超出目前允許/); expect(mocks.applyStart).not.toHaveBeenCalled();
  });

  it('需正式重排時呈現 owner 候選日期，人工選日不一致則零寫入拒絕', async () => {
    mocks.previewStart.mockResolvedValue({ ...startCandidate('2026-09-28'), operation: 'reschedule',
      scheduling_version: 0, actual_start: { case_no: CASE, official_service_dates: ['2026-09-28', '2026-09-30', '2026-10-02'] } });
    render(<OrderServiceDatesPanel caseNo={CASE} />); await input('2026-09-28');
    expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('2026-10-02');
    fireEvent.click(screen.getByRole('button', { name: '下一個月' }));
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-02' }));
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-03' }));
    fireEvent.click(screen.getByRole('button', { name: '儲存服務日期' }));
    await screen.findByText(/目前選日與正式重排結果不同/); expect(mocks.applyStart).not.toHaveBeenCalled();
  });

  it('採用正式重排日期時沿用重排 writer，接續確認使用回讀後的新排班版本', async () => {
    let schedulingVersion = 4;
    const dates = ['2026-09-28', '2026-09-30', '2026-10-02'];
    mocks.getDates.mockImplementation(async () => ({ ...datesQuery(), scheduling_version: schedulingVersion }));
    mocks.getStart.mockImplementation(async () => ({ ...startQuery(), scheduling_version: schedulingVersion, has_formal_assignments: true }));
    mocks.previewStart.mockResolvedValue({ ...startCandidate(dates[0]), operation: 'reschedule',
      scheduling_version: schedulingVersion, actual_start: { case_no: CASE, official_service_dates: dates } });
    mocks.applyStart.mockImplementation(async (_case, payload) => {
      expect(payload).toEqual(expect.objectContaining({ operation: 'reschedule', expected_order_version: 1, expected_scheduling_version: 4 }));
      actual = payload.new_actual_start_date; orderVersion++; schedulingVersion++;
      return { operation: 'reschedule', case_no: CASE, order_version: orderVersion, scheduling_version: schedulingVersion, preview_fingerprint: fp };
    });
    const normalPreview = mocks.previewDates.getMockImplementation()!;
    const normalApply = mocks.applyDates.getMockImplementation()!;
    mocks.previewDates.mockImplementation(async (...args) => ({ ...await normalPreview(...args), scheduling_version: schedulingVersion }));
    mocks.applyDates.mockImplementation(async (...args) => ({ ...await normalApply(...args), scheduling_version: schedulingVersion }));
    render(<OrderServiceDatesPanel caseNo={CASE} />); await input(dates[0]); await confirm();
    await screen.findByText('服務日期已確認並回讀版本 #1。');
    expect(mocks.applyStart).toHaveBeenCalledTimes(1);
    expect(mocks.applyDates).toHaveBeenCalledWith(CASE, expect.objectContaining({
      expected_order_version: 2, expected_scheduling_version: 5, service_dates: dates,
    }), expect.anything());
  });

  it.each(['休周六', '休周日', '週休2日', '連續服務'])('沿用 server 的 %s 計算契約', async (mode) => {
    serviceMode = mode; render(<OrderServiceDatesPanel caseNo={CASE} />); await input('2026-09-28');
    expect(mocks.calculate).toHaveBeenCalledWith({ case_no: CASE, actual_start_date: '2026-09-28', target_service_days: 3, service_mode: mode });
    expect(within(screen.getByLabelText('此次選定服務日期摘要')).getByText('3 / 3 天')).toBeInTheDocument();
  });

  it('第一步已保存時標示下游尚不可接續，服務日期正式回讀後自動解除', async () => {
    mocks.previewDates.mockRejectedValueOnce(new Error('暫時無法核對'));
    render(<OrderServiceDatesPanel caseNo={CASE} />); await input('2026-09-28'); await confirm();
    await screen.findByText(/實際開始日已保存，服務日期尚未完成/);
    expect(serviceDatesNeedCompletion(CASE)).toBe(true);
    await confirm(); await screen.findByText('服務日期已確認並回讀版本 #1。');
    expect(serviceDatesNeedCompletion(CASE)).toBe(false);
    expect(screen.getByLabelText('服務日期計算基準')).toHaveTextContent('正式實際開始日');
  });

  it('未滿約定天數仍可按儲存，警告並定位日期且不送出', async () => {
    render(<OrderServiceDatesPanel caseNo={CASE} />); await input('2026-09-28');
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-09-30' }));
    window.alert = vi.fn();
    const save = screen.getByRole('button', { name: '儲存服務日期' });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    expect(window.alert).toHaveBeenCalledWith('請選滿 3 天服務日期後再儲存。');
    expect(screen.getByLabelText('服務日期選擇')).toHaveFocus();
    expect(screen.getByRole('alert')).toHaveTextContent('請選滿 3 天');
    expect(screen.queryByLabelText('服務日期確認內容')).not.toBeInTheDocument();
    expect(mocks.applyStart).not.toHaveBeenCalled();
  });

  it('直接儲存會先檢查再保存，同一次操作處理中不能重複提交', async () => {
    actual = '2026-10-01'; confirmedVersion = 1; confirmedDates = days(actual, 3);
    let resolve!: (value: object) => void;
    mocks.previewDates.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    await screen.findByLabelText('已確認服務日期回讀');
    expect(screen.queryByRole('button', { name: '預覽服務日期' })).not.toBeInTheDocument();
    const save = screen.getByRole('button', { name: '儲存服務日期' });
    fireEvent.click(save); fireEvent.click(save);
    await waitFor(() => expect(mocks.previewDates).toHaveBeenCalledOnce());
    expect(mocks.applyDates).not.toHaveBeenCalled();
    expect(screen.getByLabelText('實際開始日')).toBeDisabled();
    await act(async () => resolve({ case_no: CASE, order_version: orderVersion, scheduling_version: 0, current_version: confirmedVersion, service_dates: confirmedDates, weeks: [], preview_fingerprint: fp }));
    await screen.findByText('服務日期已確認並回讀版本 #2。');
    expect(mocks.applyDates).toHaveBeenCalledOnce();
  });

  it('上方開始日按鈕只保存開始日，服務日期正式回讀後才前往確認排班', async () => {
    const onOpenArrangement = vi.fn(() => expect(orderMutationFlowStore.getServiceDatesDraft(CASE)?.status).toBe('observed'));
    render(<OrderServiceDatesPanel caseNo={CASE} onOpenArrangement={onOpenArrangement} />);
    await input('2026-09-28');
    fireEvent.click(screen.getByRole('button', { name: '儲存實際開始日' }));
    await screen.findByText('實際開始日已儲存；服務日期尚未儲存。');
    expect(actual).toBe('2026-09-28');
    expect(mocks.applyStart).toHaveBeenCalledOnce();
    expect(mocks.applyDates).not.toHaveBeenCalled();
    expect(serviceDatesNeedCompletion(CASE)).toBe(true);
    expect(onOpenArrangement).not.toHaveBeenCalled();
    await confirm();
    await screen.findByText('服務日期已確認並回讀版本 #1。');
    expect(mocks.applyStart).toHaveBeenCalledOnce();
    expect(mocks.applyDates).toHaveBeenCalledOnce();
    expect(onOpenArrangement).toHaveBeenCalledOnce();
    expect(serviceDatesNeedCompletion(CASE)).toBe(false);
  });

  it('開始日單獨保存結果不明時，接續原操作只核對開始日，不擅自保存日期表', async () => {
    const onOpenArrangement = vi.fn();
    const originalApply = mocks.applyStart.getMockImplementation()!;
    mocks.applyStart.mockImplementationOnce(async (...args) => { await originalApply(...args); throw new Error('network outcome unknown'); });
    render(<OrderServiceDatesPanel caseNo={CASE} onOpenArrangement={onOpenArrangement} />);
    await input('2026-09-28');
    fireEvent.click(screen.getByRole('button', { name: '儲存實際開始日' }));
    fireEvent.click(await screen.findByRole('button', { name: '讀取開始日結果並接續保存' }));
    await screen.findByText('實際開始日已儲存；服務日期尚未儲存。');
    expect(mocks.applyStart).toHaveBeenCalledOnce();
    expect(mocks.applyDates).not.toHaveBeenCalled();
    expect(onOpenArrangement).not.toHaveBeenCalled();
  });

  it('保存成功後再次人工選日，可用新的核對操作保存而不重送開始日', async () => {
    render(<OrderServiceDatesPanel caseNo={CASE} />); await input('2026-09-28'); await confirm();
    await screen.findByText('服務日期已確認並回讀版本 #1。');
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-09-30' }));
    fireEvent.click(screen.getByRole('button', { name: '下一個月' }));
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-02' }));
    await confirm(); await screen.findByText('服務日期已確認並回讀版本 #2。');
    expect(mocks.applyStart).toHaveBeenCalledTimes(1);
    expect(confirmedDates).toEqual(['2026-09-28', '2026-09-29', '2026-10-02']);
  });

  it('案件切換後較晚返回的試算不能寫入新案件的草稿', async () => {
    let resolve!: (value: ReturnType<typeof result>) => void;
    mocks.calculate.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const view = render(<OrderServiceDatesPanel caseNo={CASE} />);
    await waitFor(() => expect(screen.getByLabelText('實際開始日')).toHaveValue('2026-10-01'));
    fireEvent.change(screen.getByLabelText('實際開始日'), { target: { value: '2026-09-28' } });
    await waitFor(() => expect(mocks.calculate).toHaveBeenCalledTimes(1));
    mocks.getDates.mockResolvedValue({ ...datesQuery(), case_no: 'OTHER' });
    mocks.getStart.mockResolvedValue({ ...startQuery(), case_no: 'OTHER', planned_start_date: '2026-11-01' });
    mocks.getCalendar.mockResolvedValue({ case_no: 'OTHER', service_mode: '連續服務' });
    view.rerender(<OrderServiceDatesPanel caseNo="OTHER" />);
    await waitFor(() => expect(screen.getByLabelText('實際開始日')).toHaveValue('2026-11-01'));
    await act(async () => resolve(result('2026-09-28')));
    expect(screen.queryByLabelText('建議服務日期摘要')).not.toBeInTheDocument();
    expect(orderMutationFlowStore.getServiceDatesDraft('OTHER')?.selectedDates).toEqual([]);
  });

  it('外層投影刷新只更新已保存日期，不重新計算或清空同基準草稿', async () => {
    actual = '2026-10-01'; confirmedVersion = 1; confirmedDates = ['2026-10-01', '2026-10-03', '2026-10-05'];
    const view = render(<OrderServiceDatesPanel caseNo={CASE} projectionRevision={0} />);
    await screen.findByLabelText('已確認服務日期回讀');
    confirmedVersion = 2; confirmedDates = ['2026-10-01', '2026-10-04', '2026-10-06'];
    view.rerender(<OrderServiceDatesPanel caseNo={CASE} projectionRevision={1} />);
    await waitFor(() => expect(screen.getByLabelText('已確認服務日期回讀')).toHaveTextContent('2026-10-06'));
    expect(mocks.calculate).not.toHaveBeenCalled();
  });

  it('已有生效班表時顯示 owner 現行日期，只經開始日更正入口調整，不編輯舊確認表', async () => {
    actual = '2026-10-02'; confirmedVersion = 1; confirmedDates = days('2026-10-01', 3);
    const currentDates = days('2026-10-02', 3);
    const onOpenActualStart = vi.fn();
    render(<OrderServiceDatesPanel caseNo={CASE} onOpenActualStart={onOpenActualStart} currentAssignmentPlan={{
      case_no: CASE, order_version: 1, scheduling_version: 0, scheduling_generation: 1, client_finance_version: 1,
      payroll_version: 1, contracted_service_days: 3, service_hours_per_day: 8, service_started: false,
      assignments: [{ assignment_id: 1, candidate_key: null, staff_id: 1, sequence: 1, assigned_start_date: currentDates[0], assigned_end_date: currentDates[2], official_service_dates: currentDates, actual_hours: null, lineage_source_assignment_ids: [] }],
    }} />);
    await waitFor(() => expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('2026-10-04'));
    expect(screen.queryByLabelText('實際開始日')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '儲存服務日期' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '服務日期 2026-10-04' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '服務日期 2026-10-04' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '更正實際開始日' }));
    expect(onOpenActualStart).toHaveBeenCalledOnce();
    expect(mocks.applyStart).not.toHaveBeenCalled();
    expect(mocks.applyDates).not.toHaveBeenCalled();
  });
});
