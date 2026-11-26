import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { OrderCandidateQueryPanel } from '../../../../../../../components/OrderCandidateQueryPanel';
import type { MatchingCandidateOption } from '../../../../../../../api/scheduling/matching_candidate_workflow_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';

const mocks = vi.hoisted(() => ({ search: vi.fn(), query: vi.fn(), add: vi.fn(), command: vi.fn() }));
vi.mock('../../../../../../../api/scheduling/matching_candidate_workflow_client', async importOriginal => {
  const original = await importOriginal<typeof import('../../../../../../../api/scheduling/matching_candidate_workflow_client')>();
  return { ...original, matchingCandidateWorkflowClient: { ...original.matchingCandidateWorkflowClient, searchInquiryCandidates: mocks.search } };
});
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({
  candidateContactPoolClient: { query: mocks.query, addCandidates: mocks.add }, createCandidateAddCommand: mocks.command,
}));

const requestedDates = ['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05'];
const option = (staffId: number, name: string): MatchingCandidateOption => ({
  matching_conditions: { region: { status: 'not_matched', required_value: '新竹市', staff_values: ['桃園市'] }, preferred_service_days: { status: 'not_matched', required_value: '週休一日', staff_values: ['週休二日'] } },
  segment_index: 0, staff_id: staffId, staff_name: name, supported_day_count: 5, required_day_count: 5,
  coverage_day_count: 5, available_ranges: [{ start_date: requestedDates[0], end_date: requestedDates[4] }],
  case_period_start: requestedDates[0], case_period_end: requestedDates[4],
  required_service_dates: requestedDates, supported_service_dates: requestedDates,
  supported_ranges: [{ start_date: requestedDates[0], end_date: requestedDates[4], service_day_count: 5 }],
  source_scheduling_version: 1, filter_results: {}, full_selected_segment_coverage: true, uncovered_segment_dates: [],
  full_case_coverage: true, selected_segment_start: '2026-09-01', selected_segment_end: '2026-09-05',
});
const entry = (staffId: number, name: string, id: number, status = 'active') => ({
  id, staff_id: staffId, staff_name: name, status, service_start_date: '2026-09-01', service_end_date: '2026-09-05',
});
const pool = (candidates: ReturnType<typeof entry>[]) => ({ case_no: 'CASE-ADD', pool_id: 9, candidates });

beforeEach(() => {
  Object.values(mocks).forEach(mock => mock.mockReset());
  mocks.search.mockResolvedValue({ case_no: 'CASE-ADD', planned_start_date: '2026-09-01', planned_end_date: '2026-09-05',
    candidate_options: [option(11, '月嫂甲'), option(12, '月嫂乙')], conflicts: [] });
  mocks.command.mockImplementation((caseNo, candidates) => ({ caseNo, candidates, actor: 'operator-1', eventKey: `add-${candidates[0].staff_id}` }));
});

async function search(onPoolReadback = vi.fn(), presentation: 'workbench' | 'legacy' = 'workbench') {
  render(<OrderCandidateQueryPanel caseNo="CASE-ADD" presentation={presentation} includeMultiCaregiver={false} onPoolReadback={onPoolReadback} />);
  await screen.findByText('未設定 月嫂甲');
  return onPoolReadback;
}

it.each(['workbench', 'legacy'] as const)('shows the waiting-deposit state and keeps all candidate days available in %s', async presentation => {
  mocks.query.mockResolvedValue(pool([]));
  mocks.search.mockResolvedValueOnce({ case_no: 'CASE-ADD', planned_start_date: '2026-09-01', planned_end_date: '2026-09-05',
    candidate_options: [option(11, '月嫂甲')], conflicts: [
      { staff_id: 11, segment_index: 0, work_date: '2026-09-01', reason_code: 'active_lock', case_no: 'CASE-DEPOSIT',
        service_start_at: '2026-09-01T20:00:00+08:00', service_end_at: '2026-09-02T04:00:00+08:00' },
    ] });
  await search(vi.fn(), presentation);
  expect(screen.getByText(/空閒 5\/5 天/)).toBeVisible();
  expect(screen.queryByText('有檔期衝突，待公會協調')).not.toBeInTheDocument();
  if (presentation === 'workbench') {
    const warningGroup = screen.getByRole('region', { name: '有日期警示' });
    expect(warningGroup).toBeVisible();
    expect(warningGroup).not.toHaveTextContent(/等待訂金|CASE-DEPOSIT|查看檔期日期與原因|影響日期/);
    expect(screen.getByRole('button', { name: '加入候選池（月嫂甲）' })).toBeEnabled();
  } else {
    expect(screen.getByText('其他案件等待訂金保留，僅提醒。')).toBeVisible();
    fireEvent.click(screen.getByText('查看檔期日期與原因'));
    expect(screen.getByText(/案件 CASE-DEPOSIT，2026-09-01 20:00 至 2026-09-02 04:00/)).toBeVisible();
    const selection = screen.getByRole('checkbox', { name: '選擇正式候選 月嫂甲' });
    expect(selection).not.toBeChecked();
    fireEvent.click(selection);
    expect(screen.getByRole('button', { name: '加入候選池（1）' })).toBeEnabled();
  }
});

it('shows only the formal assignment case and date in a conflict card', async () => {
  mocks.query.mockResolvedValue(pool([]));
  mocks.search.mockResolvedValueOnce({ case_no: 'CASE-ADD', planned_start_date: '2026-09-01', planned_end_date: '2026-09-05',
    candidate_options: [{ ...option(11, '月嫂甲'), supported_day_count: 4, coverage_day_count: 4,
      available_ranges: [
        { start_date: '2026-09-01', end_date: '2026-09-01' },
        { start_date: '2026-09-03', end_date: '2026-09-05' },
      ],
      supported_service_dates: requestedDates.filter(date => date !== '2026-09-02'),
      supported_ranges: [
        { start_date: '2026-09-01', end_date: '2026-09-01', service_day_count: 1 },
        { start_date: '2026-09-03', end_date: '2026-09-05', service_day_count: 3 },
      ],
      full_case_coverage: false, full_selected_segment_coverage: false, uncovered_segment_dates: ['2026-09-02'] }], conflicts: [
      { staff_id: 11, segment_index: 0, work_date: '2026-09-01', reason_code: 'active_lock', case_no: 'CASE-DEPOSIT' },
      { staff_id: 11, segment_index: 0, work_date: '2026-09-02', reason_code: 'assignment', case_no: '115000205',
        service_start_at: '2026-09-02T09:00:00+08:00', service_end_at: '2026-09-02T17:00:00+08:00' },
      { staff_id: 11, segment_index: 0, work_date: '2026-09-02', reason_code: 'schedule', case_no: '115000205' },
    ] });
  await search();
  const conflictGroup = screen.getByRole('region', { name: '有日期衝突' });
  expect(conflictGroup).toBeVisible();
  expect(screen.getByText('已有正式排班：案件 115000205、2026-09-02')).toBeVisible();
  expect(screen.getAllByText(/^已有正式排班：/)).toHaveLength(1);
  expect(conflictGroup).not.toHaveTextContent(/等待訂金|CASE-DEPOSIT|已有服務排程|查看衝突日期與原因|影響日期|待公會協調|09:00|17:00/);
  expect(screen.getByRole('button', { name: '加入候選池（月嫂甲）' })).toBeEnabled();
});

it('groups a historical reservation as a date advisory without blocking candidate selection', async () => {
  mocks.query.mockResolvedValue(pool([]));
  mocks.search.mockResolvedValueOnce({ case_no: 'CASE-ADD', planned_start_date: '2026-09-01', planned_end_date: '2026-09-05',
    candidate_options: [option(11, '月嫂甲')], conflicts: [
      { staff_id: 11, segment_index: 0, work_date: '2026-09-01', reason_code: 'historical_reservation',
        case_no: 'CASE-HISTORY', actual_start_date: null, service_start_at: null, service_end_at: null },
    ] });
  await search();
  const warningGroup = screen.getByRole('region', { name: '有日期警示' });
  expect(warningGroup).toBeVisible();
  expect(warningGroup).not.toHaveTextContent(/歷史／暫定檔期|CASE-HISTORY|查看檔期日期與原因|影響日期/);
  expect(screen.queryByRole('region', { name: '有日期衝突' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '加入候選池（月嫂甲）' })).toBeEnabled();
});

it('reads existing membership, allows withdrawn candidates and replaces selection with row buttons', async () => {
  mocks.query.mockResolvedValue(pool([entry(11, '月嫂甲', 17), entry(12, '月嫂乙', 18, 'withdrawn')]));
  await search();
  expect(screen.getByRole('button', { name: '已加入候選池（月嫂甲）' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '加入候選池（月嫂乙）' })).toBeEnabled();
  expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  expect(screen.queryByRole('button', { name: /加入候選清單/ })).not.toBeInTheDocument();
  expect(mocks.add).not.toHaveBeenCalled();
});

it('adds one candidate at a time and marks each joined only after its exact receipt readback', async () => {
  const entries: ReturnType<typeof entry>[] = [];
  mocks.query.mockImplementation(async () => pool([...entries]));
  mocks.add.mockImplementation(async command => {
    const selected = command.candidates[0];
    const id = selected.staff_id === 11 ? 17 : 18;
    entries.push(entry(selected.staff_id, selected.staff_id === 11 ? '月嫂甲' : '月嫂乙', id));
    return { pool_id: 9, candidate_ids: [id], status: 'recorded' };
  });
  const onPoolReadback = await search();
  for (const [name, staffId] of [['月嫂甲', 11], ['月嫂乙', 12]] as const) {
    fireEvent.click(screen.getByRole('button', { name: `加入候選池（${name}）` }));
    const joined = await screen.findByRole('button', { name: `已加入候選池（${name}）` });
    expect(joined).toBeDisabled();
    expect(mocks.add).toHaveBeenLastCalledWith(expect.objectContaining({ candidates: [{ staff_id: staffId, start_date: '2026-09-01', end_date: '2026-09-05' }] }));
    fireEvent.click(joined);
  }
  expect(mocks.add).toHaveBeenCalledTimes(2);
  expect(onPoolReadback).toHaveBeenCalledTimes(2);
  expect(screen.getAllByRole('button', { name: /已加入候選池/ })).toHaveLength(2);
});

it('does not claim membership after an unknown outcome and recovers using the original command', async () => {
  let recovered = false;
  mocks.query.mockImplementation(async () => pool(recovered ? [entry(11, '月嫂甲', 17)] : []));
  mocks.add.mockRejectedValueOnce(new ApiHttpError(503, 'unavailable', '暫時無法確認寄送結果'))
    .mockImplementationOnce(async () => { recovered = true; return { pool_id: 9, candidate_ids: [17], status: 'recorded' }; });
  await search();
  fireEvent.click(screen.getByRole('button', { name: '加入候選池（月嫂甲）' }));
  const recover = await screen.findByRole('button', { name: '以原操作重新確認加入候選池' });
  expect(screen.queryByRole('button', { name: '已加入候選池（月嫂甲）' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '加入候選池（月嫂乙）' })).toBeDisabled();
  fireEvent.click(recover);
  await waitFor(() => expect(screen.getByRole('button', { name: '已加入候選池（月嫂甲）' })).toBeDisabled());
  expect(mocks.command).toHaveBeenCalledTimes(1);
  expect(mocks.add.mock.calls[0][0]).toEqual(mocks.add.mock.calls[1][0]);
});
