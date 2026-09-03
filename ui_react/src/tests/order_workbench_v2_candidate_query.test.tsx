import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderCandidateQueryPanel } from '../components/OrderCandidateQueryPanel';

const mocks = vi.hoisted(() => ({
  searchSegmentedCaregivers: vi.fn(),
  addCandidates: vi.fn(),
  queryPool: vi.fn(),
  sendInformation: vi.fn(),
}));

vi.mock('../api/scheduling/matching_candidate_workflow_client', () => ({
  matchingCandidateWorkflowClient: {
    searchSegmentedCaregivers: mocks.searchSegmentedCaregivers,
  },
}));

vi.mock('../api/scheduling/candidate_contact_pool_client', () => ({
  candidateContactPoolClient: {
    addCandidates: mocks.addCandidates,
    query: mocks.queryPool,
    sendInformation: mocks.sendInformation,
  },
}));

const eligible = {
  segment_index: 0,
  staff_id: 8892,
  staff_name: '正式合格月嫂',
  coverage_day_count: 5,
  available_ranges: [{ start_date: '2026-09-01', end_date: '2026-09-05' }],
  case_period_start: '2026-09-01',
  case_period_end: '2026-09-05',
  required_service_dates: ['2026-09-01'],
  supported_service_dates: ['2026-09-01'],
  supported_ranges: [{ start_date: '2026-09-01', end_date: '2026-09-05', service_day_count: 1 }],
  supported_day_count: 1,
  required_day_count: 1,
  full_case_coverage: true,
  selected_segment_start: '2026-09-01',
  selected_segment_end: '2026-09-05',
  full_selected_segment_coverage: true,
  uncovered_segment_dates: [],
  source_scheduling_version: 3,
  filter_results: { schedule: true, region: true },
};

const partial = {
  ...eligible,
  staff_id: 8893,
  staff_name: '部分可用月嫂',
  coverage_day_count: 0,
  supported_service_dates: [],
  supported_ranges: [],
  supported_day_count: 0,
  full_case_coverage: false,
  full_selected_segment_coverage: false,
  uncovered_segment_dates: ['2026-09-01'],
  filter_results: { schedule: false, region: true },
};

function availability(overrides: Record<string, unknown> = {}) {
  return {
    case_no: 'CASE-CANDIDATE',
    planned_start_date: '2026-09-01',
    planned_end_date: '2026-09-05',
    feasibility: 'complete',
    complete_combinations: [[{
      segment_index: 0,
      staff_id: 8892,
      start_date: '2026-09-01',
      end_date: '2026-09-05',
    }]],
    segment_candidates: [{
      segment_index: 0,
      staff_id: 8892,
      start_date: '2026-09-01',
      end_date: '2026-09-05',
    }],
    candidate_options: [eligible, partial],
    conflicts: [{
      segment_index: 0,
      staff_id: 8893,
      work_date: '2026-09-01',
      reason_code: 'active_lock',
    }],
    ...overrides,
  };
}

function candidatePool(staffId = 8892, staffName = '正式合格月嫂') {
  return {
    pool_id: 9,
    case_no: 'CASE-CANDIDATE',
    candidates: [{
      id: 17,
      staff_id: staffId,
      service_start_date: '2026-09-01',
      service_end_date: '2026-09-05',
      status: 'active',
      created_at: '2026-09-03T00:00:00Z',
      staff_name: staffName,
      willingness: 'pending',
      reason: null,
      information: { '1': null, '2': null },
    }],
  };
}

describe('待辦看板 Beta 第 2 階正式候選查詢、候選池寫入與回讀', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
  });

  it('只顯示 server complete combination 內的正式候選，不把 partial option 冒充合格人選', async () => {
    mocks.searchSegmentedCaregivers.mockResolvedValue(availability());
    render(<OrderCandidateQueryPanel caseNo="CASE-CANDIDATE" />);

    fireEvent.click(screen.getByRole('button', { name: '查詢正式候選' }));

    await waitFor(() => expect(mocks.searchSegmentedCaregivers).toHaveBeenCalledWith('CASE-CANDIDATE', 1));
    expect(await screen.findByText('正式合格月嫂')).toBeInTheDocument();
    expect(screen.getByText(/月嫂 #8892/)).toBeInTheDocument();
    expect(screen.queryByText('部分可用月嫂')).not.toBeInTheDocument();
    expect(screen.getByText('Server 計畫期間：2026-09-01 → 2026-09-05')).toBeInTheDocument();
  });

  it('沒有 server 完整候選時顯示正式 conflict 作為阻礙', async () => {
    mocks.searchSegmentedCaregivers.mockResolvedValue(availability({
      feasibility: 'partial',
      complete_combinations: [],
      segment_candidates: [],
    }));
    render(<OrderCandidateQueryPanel caseNo="CASE-CANDIDATE" />);

    fireEvent.click(screen.getByRole('button', { name: '查詢正式候選' }));

    expect(await screen.findByText('目前沒有 server 確認的完整候選；不以瀏覽器條件推導人選。')).toBeInTheDocument();
    expect(screen.getByText(/2026-09-01 · 月嫂 #8893 · active_lock/)).toBeInTheDocument();
    expect(screen.queryByText('部分可用月嫂')).not.toBeInTheDocument();
  });

  it('寫入後以 receipt candidate id 回讀相同人選，再通知待辦投影刷新；不發送聯絡', async () => {
    mocks.searchSegmentedCaregivers.mockResolvedValue(availability());
    mocks.addCandidates.mockResolvedValue({ pool_id: 9, candidate_ids: [17], status: 'recorded' });
    mocks.queryPool.mockResolvedValue(candidatePool());
    const onPoolReadback = vi.fn();
    render(<OrderCandidateQueryPanel caseNo="CASE-CANDIDATE" onPoolReadback={onPoolReadback} />);

    fireEvent.click(screen.getByRole('button', { name: '查詢正式候選' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: '選擇正式候選 正式合格月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '加入候選池（1）' }));

    await waitFor(() => expect(mocks.addCandidates).toHaveBeenCalledWith('CASE-CANDIDATE', [{
      staff_id: 8892,
      start_date: '2026-09-01',
      end_date: '2026-09-05',
    }]));
    await waitFor(() => expect(mocks.queryPool).toHaveBeenCalledWith('CASE-CANDIDATE'));
    await waitFor(() => expect(onPoolReadback).toHaveBeenCalledTimes(1));
    expect(mocks.sendInformation).not.toHaveBeenCalled();
    expect(await screen.findByText(/Pool #9 · 已回讀 1 位本次寫入候選：正式合格月嫂 \(#8892\)。/)).toBeInTheDocument();
  });

  it('回讀 receipt candidate id 對應到不同人員時 fail closed，不刷新待辦投影', async () => {
    mocks.searchSegmentedCaregivers.mockResolvedValue(availability());
    mocks.addCandidates.mockResolvedValue({ pool_id: 9, candidate_ids: [17], status: 'recorded' });
    mocks.queryPool.mockResolvedValue(candidatePool(9999, '錯誤月嫂'));
    const onPoolReadback = vi.fn();
    render(<OrderCandidateQueryPanel caseNo="CASE-CANDIDATE" onPoolReadback={onPoolReadback} />);

    fireEvent.click(screen.getByRole('button', { name: '查詢正式候選' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: '選擇正式候選 正式合格月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '加入候選池（1）' }));

    expect(await screen.findByText('候選池回讀與本次寫入選擇不一致。')).toBeInTheDocument();
    expect(onPoolReadback).not.toHaveBeenCalled();
    expect(mocks.sendInformation).not.toHaveBeenCalled();
  });
});
