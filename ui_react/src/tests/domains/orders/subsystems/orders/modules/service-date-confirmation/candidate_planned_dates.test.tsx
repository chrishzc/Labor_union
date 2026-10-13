import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CandidatePlannedServiceDates } from '../../../../../../../components/CandidatePlannedServiceDates';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { ApiNetworkError } from '../../../../../../../api/shared/typed_errors';

const mocks = vi.hoisted(() => ({ terms: vi.fn(), mode: vi.fn(), query: vi.fn(), preview: vi.fn(), apply: vi.fn(), calculate: vi.fn(), weekly: vi.fn() }));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderTerms: mocks.terms, getOrderCalendarDetail: mocks.mode } }));
vi.mock('../../../../../../../api/orders/order_mutation_client', () => ({ ordersMutationClient: { getServiceDates: mocks.query, previewServiceDates: mocks.preview, applyServiceDates: mocks.apply } }));
vi.mock('../../../../../../../api/scheduling/schedule_precision_client', () => ({ schedulePrecisionClient: { calculate: mocks.calculate } }));
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({ candidateContactPoolClient: { previewWeeklyService: mocks.weekly } }));
const CASE = 'PLANNED-UI';
const fingerprint = 'a'.repeat(64);
const chosen = ['2026-11-05', '2026-11-07', '2026-11-09'];
const range = Array.from({ length: 51 }, (_, i) => new Date(Date.UTC(2026, 10, 5 + i)).toISOString().slice(0, 10));
let saved: string[], version: number | null, orderVersion: number;
const query = () => ({ case_no: CASE, order_version: orderVersion, scheduling_version: 0, contracted_service_days: 3,
  suggested_dates: [], selectable_dates: range, current_version: version, current_dates: saved, bound_staff: [], arrangement_pending: false });
const result = (dates = chosen) => ({ actual_start_date: '2026-11-05', target_service_days: 3,
  day_by_day: dates.map(date => ({ date, is_work_day: true })) });
const onPreview = vi.fn();
const open = () => render(<CandidatePlannedServiceDates caseNo={CASE} candidateId={7} startDate="2026-11-05" onPreview={onPreview} />);
async function choose() {
  await waitFor(() => expect(screen.getByRole('checkbox', { name: '星期五' })).toBeEnabled());
  fireEvent.click(screen.getByRole('checkbox', { name: '星期五' }));
  fireEvent.click(screen.getByRole('checkbox', { name: '星期日' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '保存預計日期' })).toBeEnabled());
}
beforeEach(() => {
  Object.values(mocks).forEach(mock => mock.mockReset()); onPreview.mockReset();
  saved = []; version = null; orderVersion = 1; orderMutationFlowStore.clearAll();
  mocks.terms.mockImplementation(async () => ({ case_no: CASE, order_version: orderVersion, scheduling_version: 0, scheduling_generation: 0, assignments: [], terms: {} }));
  mocks.mode.mockResolvedValue({ case_no: CASE, service_mode: null, original_service_type: '休五、日' });
  mocks.query.mockImplementation(async () => query());
  mocks.calculate.mockImplementation(async () => result());
  mocks.weekly.mockImplementation(async (_case, _candidate, options) => ({ case_no: CASE, candidate_id: 7,
    date_basis: options?.serviceDates ? 'draft' : version ? 'confirmed' : 'planned', rows: [], warnings: [] }));
  mocks.preview.mockImplementation(async (_case, { service_dates }) => ({ case_no: CASE, order_version: orderVersion, scheduling_version: 0,
    current_version: version, service_dates, weeks: [], preview_fingerprint: fingerprint }));
  mocks.apply.mockImplementation(async (_case, payload) => {
    saved = payload.service_dates; version = (version ?? 0) + 1;
    return { case_no: CASE, confirmed_version: version, order_version: orderVersion, scheduling_version: 0, service_dates: saved, preview_fingerprint: fingerprint };
  });
});

it('即時試算零寫入，一次保存日期，無第二步確認；重開使用保存日期而不恢復星期', async () => {
  const view = open(); await choose();
  expect(screen.getByLabelText('原始匯入服務方式')).toHaveTextContent('休五、日');
  expect(mocks.calculate).toHaveBeenLastCalledWith(expect.objectContaining({ service_mode: '休五、日', custom_rest_weekdays: [4, 6] }));
  expect(mocks.weekly).toHaveBeenLastCalledWith(CASE, 7, { serviceDates: chosen });
  expect(mocks.apply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '保存預計日期' }));
  await screen.findByText('預計日期已保存，後續寄送將使用這份日期。');
  expect(mocks.apply).toHaveBeenCalledTimes(1);
  expect(mocks.apply.mock.calls[0][1].service_dates).toEqual(chosen);
  expect(mocks.apply.mock.calls[0][1]).not.toHaveProperty('custom_rest_weekdays');
  expect(screen.queryByRole('button', { name: /確認/ })).not.toBeInTheDocument();
  expect(onPreview).toHaveBeenLastCalledWith(expect.objectContaining({ date_basis: 'confirmed' }));
  view.unmount(); const count = mocks.calculate.mock.calls.length;
  open(); await screen.findByText(/預計服務日期：3 天/);
  expect(screen.getByRole('checkbox', { name: '星期五' })).not.toBeChecked();
  expect(mocks.calculate).toHaveBeenCalledTimes(count);
  expect(screen.getByRole('button', { name: '保存預計日期' })).toBeDisabled();
});

it('較晚回來的舊試算不覆蓋新日期與預覽', async () => {
  let finish!: (value: ReturnType<typeof result>) => void;
  mocks.calculate.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  open(); await choose();
  await act(async () => finish(result(['2026-11-05', '2026-11-06', '2026-11-07'])));
  expect(mocks.weekly).toHaveBeenLastCalledWith(CASE, 7, { serviceDates: chosen });
  fireEvent.click(screen.getByRole('button', { name: '保存預計日期' }));
  await screen.findByText('預計日期已保存，後續寄送將使用這份日期。');
  expect(saved).toEqual(chosen);
});

it('全部休假停止計算與保存', async () => {
  open(); await waitFor(() => expect(screen.getByRole('checkbox', { name: '星期一' })).toBeEnabled());
  for (const label of ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']) fireEvent.click(screen.getByRole('checkbox', { name: label }));
  await screen.findByText('請至少保留一天可服務的星期。');
  expect(screen.getByRole('button', { name: '保存預計日期' })).toBeDisabled();
  expect(mocks.calculate.mock.calls.every(([request]) => request.custom_rest_weekdays.length < 7)).toBe(true);
  expect(mocks.apply).not.toHaveBeenCalled();
});

it('保存前有他人更新版本時不覆寫', async () => {
  open(); await choose(); orderVersion = 2;
  fireEvent.click(screen.getByRole('button', { name: '保存預計日期' }));
  await screen.findByText('案件日期已被更新，請重新開啟後再保存。');
  expect(mocks.apply).not.toHaveBeenCalled();
});

it('保存結果未明時沿用原冪等鍵，不能重新試算覆蓋原操作', async () => {
  mocks.apply.mockRejectedValueOnce(new ApiNetworkError('連線中斷'));
  open(); await choose(); fireEvent.click(screen.getByRole('button', { name: '保存預計日期' }));
  await screen.findByRole('button', { name: '接續保存預計日期' });
  expect(screen.getByRole('checkbox', { name: '星期五' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '接續保存預計日期' }));
  await screen.findByText('預計日期已保存，後續寄送將使用這份日期。');
  expect(mocks.apply.mock.calls[0][2].idempotencyKey).toBe(mocks.apply.mock.calls[1][2].idempotencyKey);
});
