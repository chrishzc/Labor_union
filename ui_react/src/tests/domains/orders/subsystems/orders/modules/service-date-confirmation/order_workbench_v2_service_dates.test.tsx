import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderServiceDatesPanel } from '../../../../../../../components/OrderServiceDatesPanel';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import type { ServiceDateConfirmationQueryView, ServiceDateConfirmationPreviewView } from '../../../../../../../api/orders/order_mutation_schemas';
import type { ordersMutationClient } from '../../../../../../../api/orders/order_mutation_client';

const mocks = vi.hoisted(() => ({
  getActualStart: vi.fn(), getOrderCalendarDetail: vi.fn(), calculate: vi.fn(),
  getServiceDates: vi.fn(), previewServiceDates: vi.fn(), applyServiceDates: vi.fn(),
}));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: {
  getActualStart: mocks.getActualStart, getOrderCalendarDetail: mocks.getOrderCalendarDetail,
} }));
vi.mock('../../../../../../../api/orders/order_mutation_client', () => ({ ordersMutationClient: {
  getServiceDates: mocks.getServiceDates, previewServiceDates: mocks.previewServiceDates, applyServiceDates: mocks.applyServiceDates,
} }));
vi.mock('../../../../../../../api/scheduling/schedule_precision_client', () => ({ schedulePrecisionClient: { calculate: mocks.calculate } }));

const CASE = 'CASE-SERVICE-DATES';
const initialDates = ['2026-10-01', '2026-10-02', '2026-10-04'];
const revisedDates = ['2026-10-01', '2026-10-03', '2026-10-04'];
const initialQuery: ServiceDateConfirmationQueryView = {
  case_no: CASE, order_version: 11, scheduling_version: 7, contracted_service_days: 3,
  suggested_dates: initialDates, selectable_dates: ['2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'],
  current_version: null, current_dates: [], bound_staff: [], arrangement_pending: false,
};
let currentQuery: ServiceDateConfirmationQueryView;
let actualStart: string;

function previewFor(dates: string[]): ServiceDateConfirmationPreviewView {
  return {
    case_no: CASE, order_version: currentQuery.order_version, scheduling_version: currentQuery.scheduling_version,
    current_version: currentQuery.current_version, service_dates: dates, weeks: [],
    preview_fingerprint: (currentQuery.current_version === null ? 'a' : 'b').repeat(64),
  };
}
function calculation(start: string) {
  const dates = start === '2026-10-01' ? initialDates : ['2026-09-28', '2026-09-29', '2026-09-30'];
  const calendarDates = start === '2026-10-01' ? initialQuery.selectable_dates : dates;
  return {
    actual_start_date: start, actual_end_date: dates.at(-1), target_service_days: 3,
    total_calendar_days: calendarDates.length, actual_work_days_count: 3, rest_days_count: calendarDates.length - 3,
    national_holidays_found: [], total_estimated_salary: null, weekly_stats: [],
    day_by_day: calendarDates.map((date, index) => ({ date, day_num: index + 1,
      is_work_day: dates.includes(date), is_rest_day: !dates.includes(date), holiday_name: null })),
  };
}
function changeFormalStart() {
  actualStart = '2026-09-28';
  currentQuery = { ...currentQuery, order_version: 12, scheduling_version: 8,
    selectable_dates: ['2026-09-28', '2026-09-29', '2026-09-30'] };
}
async function ready() {
  await waitFor(() => expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeEnabled());
}
async function save() {
  await ready();
  fireEvent.click(screen.getByRole('button', { name: '儲存服務日期' }));
}
function changeSelection() {
  fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-02' }));
  fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-03' }));
}

// Keep the real Preview / Apply / receipt store; only owner API boundaries are simulated.
describe('服務日期自動讀取與單次儲存流程', () => {
  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset());
    orderMutationFlowStore.clearAll();
    currentQuery = structuredClone(initialQuery);
    actualStart = '2026-10-01';
    mocks.getActualStart.mockImplementation(async () => ({
      case_no: CASE, current_actual_start_date: actualStart, planned_start_date: '2026-10-01', service_data_locked: false,
      order_version: currentQuery.order_version, scheduling_version: currentQuery.scheduling_version,
      scheduling_generation: 1, client_finance_version: 3, payroll_version: 2,
    }));
    mocks.getOrderCalendarDetail.mockResolvedValue({ case_no: CASE, service_mode: '休周六' });
    mocks.getServiceDates.mockImplementation(async () => structuredClone(currentQuery));
    mocks.calculate.mockImplementation(async ({ actual_start_date }: { actual_start_date: string }) => calculation(actual_start_date));
    mocks.previewServiceDates.mockImplementation(async (_case: string, { service_dates }: { service_dates: string[] }) => previewFor(service_dates));
    mocks.applyServiceDates.mockImplementation(async (_case: string, payload: Parameters<typeof ordersMutationClient.applyServiceDates>[1]) => {
      if (payload.expected_order_version !== currentQuery.order_version || payload.expected_scheduling_version !== currentQuery.scheduling_version) {
        throw new ApiHttpError(409, 'stale_preview', '日期或案件資料已更新');
      }
      currentQuery = { ...currentQuery, order_version: currentQuery.order_version + 1,
        current_version: (currentQuery.current_version ?? 0) + 1, current_dates: payload.service_dates };
      return { case_no: CASE, confirmed_version: currentQuery.current_version, order_version: currentQuery.order_version,
        scheduling_version: currentQuery.scheduling_version, service_dates: payload.service_dates, preview_fingerprint: payload.preview_fingerprint };
    });
  });

  it('自動精算但不寫入，儲存時依序 Preview、Apply 並回讀正式日期', async () => {
    const onObserved = vi.fn();
    const onOpenActualStart = vi.fn();
    render(<OrderServiceDatesPanel caseNo={CASE} onObserved={onObserved} onOpenActualStart={onOpenActualStart} />);
    await ready();
    expect(mocks.calculate).toHaveBeenCalledWith({ case_no: CASE, actual_start_date: '2026-10-01', target_service_days: 3, service_mode: '休周六' });
    expect(mocks.previewServiceDates).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
    const calendar = screen.getByRole('group', { name: '服務日期月曆' });
    expect(within(calendar).getByRole('button', { name: '服務日期 2026-10-02' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(calendar).getByRole('button', { name: '服務日期 2026-10-03' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByRole('button', { name: '預覽服務日期' })).not.toBeInTheDocument();
    changeSelection();
    await save();
    await screen.findByText('服務日期已確認並回讀版本 #1。');
    expect(mocks.previewServiceDates).toHaveBeenCalledWith(CASE, { service_dates: revisedDates }, undefined);
    expect(mocks.applyServiceDates).toHaveBeenCalledWith(CASE, {
      service_dates: revisedDates, expected_order_version: 11, expected_scheduling_version: 7,
      preview_fingerprint: 'a'.repeat(64), reason: '確認服務日期',
    }, expect.objectContaining({ idempotencyKey: expect.any(String) }));
    expect(mocks.previewServiceDates.mock.invocationCallOrder[0]).toBeLessThan(mocks.applyServiceDates.mock.invocationCallOrder[0]);
    expect(mocks.getServiceDates.mock.invocationCallOrder.at(-1)).toBeGreaterThan(mocks.applyServiceDates.mock.invocationCallOrder[0]);
    fireEvent.click(screen.getByText('查看已保存日期與版本'));
    expect(screen.getByLabelText('已確認服務日期回讀')).toHaveTextContent(revisedDates.join('、'));
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(onOpenActualStart).not.toHaveBeenCalled();
  });

  it('實際開始日重排後顯示目前排班，保留先前確認日期供查閱', async () => {
    actualStart = '2026-10-05';
    currentQuery = { ...currentQuery, order_version: 13, scheduling_version: 9, current_version: 2, current_dates: initialDates };
    render(<OrderServiceDatesPanel caseNo={CASE} currentAssignmentPlan={{
      case_no: CASE, order_version: 13, scheduling_version: 9, scheduling_generation: 3,
      client_finance_version: 3, payroll_version: 2, contracted_service_days: 3, service_hours_per_day: 8, service_started: true,
      assignments: [
        { assignment_id: 101, candidate_key: null, staff_id: 1, sequence: 1, assigned_start_date: '2026-10-05', assigned_end_date: '2026-10-06', official_service_dates: ['2026-10-05', '2026-10-06'], actual_hours: 16, lineage_source_assignment_ids: [91] },
        { assignment_id: 102, candidate_key: null, staff_id: 2, sequence: 2, assigned_start_date: '2026-10-07', assigned_end_date: '2026-10-07', official_service_dates: ['2026-10-07'], actual_hours: 8, lineage_source_assignment_ids: [92] },
      ],
    }} />);
    await screen.findByText('現行班表已保存。');
    const calendar = screen.getByRole('group', { name: '服務日期月曆' });
    for (const date of ['2026-10-05', '2026-10-06', '2026-10-07']) {
      expect(within(calendar).getByRole('button', { name: `服務日期 ${date}` })).toHaveAttribute('aria-pressed', 'true');
      expect(within(calendar).getByRole('button', { name: `服務日期 ${date}` })).toBeDisabled();
    }
    expect(within(calendar).getByRole('button', { name: '服務日期 2026-10-01' })).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByText('查看已保存日期與版本'));
    const readback = screen.getByLabelText('先前確認日期與目前排班回讀');
    expect(readback).toHaveTextContent(initialDates.join('、'));
    expect(readback).toHaveTextContent('目前排班服務日2026-10-05、2026-10-06、2026-10-07');
    expect(screen.queryByRole('button', { name: '儲存服務日期' })).not.toBeInTheDocument();
    expect(mocks.calculate).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
  });

  it('任一 owner 回讀案件編號不一致時 fail closed，不執行精算或 Preview', async () => {
    mocks.getActualStart.mockResolvedValue({ case_no: 'OTHER-CASE' });
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('服務日期精算回讀案件編號不一致。');
    expect(mocks.calculate).not.toHaveBeenCalled();
    expect(mocks.previewServiceDates).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '儲存服務日期' })).not.toBeInTheDocument();
  });

  it('精算失敗時不保留上一輪可操作狀態，也不保存日期', async () => {
    mocks.calculate.mockRejectedValueOnce(new Error('正式精算暫時無法使用'));
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('正式精算暫時無法使用');
    expect(screen.queryByLabelText('建議服務日期摘要')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '儲存服務日期' })).not.toBeInTheDocument();
    expect(mocks.previewServiceDates).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
  });

  it('保存後修改日期會清除舊 Preview，下一次儲存重新核對新選日與版本', async () => {
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    await save();
    await screen.findByText('服務日期已確認並回讀版本 #1。');
    changeSelection();
    expect(orderMutationFlowStore.getServiceDatesDraft(CASE)?.previewView).toBeNull();
    expect(mocks.applyServiceDates).toHaveBeenCalledTimes(1);
    await save();
    await screen.findByText('服務日期已確認並回讀版本 #2。');
    expect(mocks.previewServiceDates).toHaveBeenCalledTimes(2);
    expect(mocks.previewServiceDates.mock.calls.map(call => call[1].service_dates)).toEqual([initialDates, revisedDates]);
    expect(mocks.applyServiceDates.mock.calls[1][1]).toMatchObject({ service_dates: revisedDates,
      expected_order_version: 12, expected_scheduling_version: 7, preview_fingerprint: 'b'.repeat(64) });
    expect(mocks.previewServiceDates.mock.invocationCallOrder[1]).toBeLessThan(mocks.applyServiceDates.mock.invocationCallOrder[1]);
  });

  it('歷史重啟後顯示既定服務人員且不要求重新挑選候選', async () => {
    currentQuery.bound_staff = [{ staff_id: 12, staff_name: '王月嫂' }];
    render(<OrderServiceDatesPanel caseNo={CASE} />);
    expect(await screen.findByText(/既定服務人員：/)).toBeInTheDocument();
    expect(screen.getByText(/未設定 王月嫂/)).toBeInTheDocument();
    expect(screen.getByText(/不需重新挑選候選或再次推薦/)).toBeInTheDocument();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
  });

  it('歷史日期已確認但未排班時顯示獨立建立正式安排入口', async () => {
    currentQuery = { ...currentQuery, current_version: 2, current_dates: initialDates,
      bound_staff: [{ staff_id: 12, staff_name: '王月嫂' }], arrangement_pending: true };
    render(<OrderServiceDatesPanel caseNo={CASE} view="arrangement" />);
    expect(await screen.findByRole('region', { name: '歷史訂單建立正式安排' })).toBeInTheDocument();
    expect(screen.getByText(/排班與費率快照尚未建立/)).toBeInTheDocument();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
  });

  it('正式實際開始日變更後自動重算，人工選日須明確採用新建議', async () => {
    const { rerender } = render(<OrderServiceDatesPanel caseNo={CASE} calculationRevision={0} />);
    await ready();
    changeSelection();
    changeFormalStart();
    rerender(<OrderServiceDatesPanel caseNo={CASE} calculationRevision={1} />);
    await screen.findByRole('button', { name: '採用新建議' });
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeDisabled();
    expect(orderMutationFlowStore.getServiceDatesDraft(CASE)?.selectedDates).toEqual(revisedDates);
    expect(mocks.previewServiceDates).not.toHaveBeenCalled();
    expect(mocks.applyServiceDates).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '採用新建議' }));
    await ready();
    expect(mocks.calculate).toHaveBeenLastCalledWith({ case_no: CASE, actual_start_date: '2026-09-28', target_service_days: 3, service_mode: '休周六' });
    expect(orderMutationFlowStore.getServiceDatesDraft(CASE)?.selectedDates).toEqual(['2026-09-28', '2026-09-29', '2026-09-30']);
  });

  it('日期基準改變時，延遲舊 Preview 不能通過版本檢查或保存舊日期', async () => {
    let resolveLatePreview!: (value: ServiceDateConfirmationPreviewView) => void;
    mocks.previewServiceDates.mockImplementationOnce(() => new Promise(resolve => { resolveLatePreview = resolve; }));
    const onObserved = vi.fn();
    const { rerender } = render(<OrderServiceDatesPanel caseNo={CASE} calculationRevision={0} onObserved={onObserved} />);
    await ready();
    const oldPreview = previewFor(initialDates);
    await save();
    await waitFor(() => expect(mocks.previewServiceDates).toHaveBeenCalledTimes(1));
    changeFormalStart();
    rerender(<OrderServiceDatesPanel caseNo={CASE} calculationRevision={1} onObserved={onObserved} />);
    expect(await screen.findByText('日期基準已變更；待目前操作結果確認後，會接續更新。')).toBeInTheDocument();
    await act(async () => resolveLatePreview(oldPreview));
    await waitFor(() => expect(mocks.calculate).toHaveBeenLastCalledWith(expect.objectContaining({ actual_start_date: '2026-09-28' })));
    await screen.findByRole('button', { name: '採用新建議' });
    expect(screen.getByRole('button', { name: '儲存服務日期' })).toBeDisabled();
    expect(mocks.applyServiceDates).toHaveBeenCalledTimes(1);
    expect(mocks.applyServiceDates.mock.calls[0][1].expected_order_version).toBe(11);
    expect(currentQuery.current_dates).toEqual([]);
    expect(currentQuery.current_version).toBeNull();
    expect(onObserved).not.toHaveBeenCalled();
    expect(screen.queryByText(/服務日期已確認並回讀版本/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '採用新建議' }));
    await ready();
    expect(orderMutationFlowStore.getServiceDatesDraft(CASE)?.selectedDates).toEqual(['2026-09-28', '2026-09-29', '2026-09-30']);
    expect(mocks.applyServiceDates).toHaveBeenCalledTimes(1);
  });

  it('Apply 後正式回讀失敗保留收據，不能通知成功或重送 Apply', async () => {
    const onObserved = vi.fn();
    mocks.getServiceDates.mockImplementation(async () => {
      if (mocks.applyServiceDates.mock.calls.length > 0) throw new Error('正式日期回讀失敗');
      return structuredClone(currentQuery);
    });
    render(<OrderServiceDatesPanel caseNo={CASE} onObserved={onObserved} />);
    await save();
    await screen.findByRole('button', { name: '只重新讀取服務日期結果' });
    expect(screen.getByRole('alert')).toHaveTextContent('正式日期回讀失敗');
    expect(orderMutationFlowStore.getServiceDatesDraft(CASE)).toMatchObject({ status: 'observation_failed', receiptView: { confirmed_version: 1 } });
    expect(mocks.applyServiceDates).toHaveBeenCalledTimes(1);
    expect(onObserved).not.toHaveBeenCalled();
    expect(screen.queryByText(/服務日期已確認並回讀版本/)).not.toBeInTheDocument();
  });
});
