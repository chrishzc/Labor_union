import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderCandidateQueryPanel } from '../components/OrderCandidateQueryPanel';
import { ApiNetworkError, ApiTimeoutError } from '../api/shared/typed_errors';

const mocks = vi.hoisted(() => ({
  searchInquiryCandidates: vi.fn(),
  addCandidates: vi.fn(),
  queryPool: vi.fn(),
  sendInformation: vi.fn(),
  createAddCandidatesCommand: vi.fn(),
}));

vi.mock('../api/scheduling/matching_candidate_workflow_client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/scheduling/matching_candidate_workflow_client')>();
  return {
    ...original,
    matchingCandidateWorkflowClient: {
      ...original.matchingCandidateWorkflowClient,
      searchInquiryCandidates: mocks.searchInquiryCandidates,
    },
  };
});

vi.mock('../api/scheduling/candidate_contact_pool_client', () => ({
  createCandidateAddCommand: mocks.createAddCandidatesCommand,
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
  required_service_dates: ['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05'],
  supported_service_dates: ['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05'],
  supported_ranges: [{ start_date: '2026-09-01', end_date: '2026-09-05', service_day_count: 5 }],
  supported_day_count: 5,
  required_day_count: 5,
  full_case_coverage: true,
  selected_segment_start: '2026-09-01',
  selected_segment_end: '2026-09-05',
  full_selected_segment_coverage: true,
  uncovered_segment_dates: [],
  source_scheduling_version: 3,
  filter_results: { region: true, preferred_service_days: true },
  matching_conditions: { region: { status: 'matched', required_value: '新竹市', staff_values: ['新竹市'] }, preferred_service_days: { status: 'matched', required_value: '週休一日', staff_values: ['週休一日'] } },
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
  uncovered_segment_dates: ['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05'],
  filter_results: { schedule: false, region: true },
};

function availability(overrides: Record<string, unknown> = {}) {
  return {
    case_no: '115000204',
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
    case_no: '115000204',
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
      latest_willingness_event_id: null,
      information: { '1': null, '2': null },
    }],
  };
}

const allFilters = {
  region: false,
  cooking: false,
  preferred_service_days: false,
  daily_service_hours: false,
};

describe('待辦看板 Beta 第 2 階正式候選查詢、候選池寫入與回讀', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.createAddCandidatesCommand.mockImplementation((caseNo, candidates) => ({
      caseNo,
      candidates,
      actor: 'operator-1',
      eventKey: 'orders-candidate-pool-add-original-key',
    }));
  });

  it('displays union number plus name and sorts candidates naturally without changing staff identity', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability({ candidate_options: [
      { ...eligible, staff_union_no: 'A10' },
      { ...eligible, staff_id: 8893, staff_name: '第二位月嫂', staff_union_no: 'A2' },
      { ...eligible, staff_id: 8894, staff_name: '未編號月嫂', staff_union_no: null },
    ] }));
    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} />);
    await screen.findByText('A2 第二位月嫂');
    const names = Array.from(document.querySelectorAll('[aria-label="可詢問月嫂"] strong')).map(node => node.textContent);
    expect(names).toEqual(['A2 第二位月嫂', 'A10 正式合格月嫂', '未設定 未編號月嫂']);
    fireEvent.click(screen.getByRole('checkbox', { name: '選擇正式候選 第二位月嫂' }));
    expect(mocks.addCandidates).not.toHaveBeenCalled();
  });

  it('查詢只有兩項提示，沒有偏好篩選勾選框', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability());
    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} />);
    expect(screen.getByRole('button', { name: '正在載入月嫂…' })).toBeDisabled();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('group', { name: '媒合篩選條件' })).not.toBeInTheDocument();
    await waitFor(() => expect(mocks.searchInquiryCandidates).toHaveBeenCalledWith('115000204', allFilters, expect.objectContaining({ signal: expect.any(AbortSignal) })));
    expect(await screen.findByText('可詢問 2 位')).toBeInTheDocument();
    expect(mocks.searchInquiryCandidates).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('尚未查詢')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新查詢' })).toBeEnabled();
    expect(mocks.addCandidates).not.toHaveBeenCalled();
  });

  it('關閉或切換案件取消查詢，延遲的舊案件結果不覆蓋新案件', async () => {
    let resolveOld!: (value: ReturnType<typeof availability>) => void;
    mocks.searchInquiryCandidates.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
      .mockResolvedValueOnce(availability({ case_no: 'NEW-CASE', candidate_options: [{ ...eligible, staff_name: '新案件月嫂' }] }));
    const { rerender, unmount } = render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} />);
    const firstSignal = mocks.searchInquiryCandidates.mock.calls[0][2].signal as AbortSignal;
    expect(screen.getByRole('button', { name: '正在載入月嫂…' })).toBeDisabled();
    rerender(<OrderCandidateQueryPanel caseNo="NEW-CASE" includeMultiCaregiver={false} />);
    expect(firstSignal.aborted).toBe(true);
    await screen.findByText('未設定 新案件月嫂');
    await act(async () => { resolveOld(availability()); });
    expect(screen.queryByText('未設定 正式合格月嫂')).not.toBeInTheDocument();
    expect(screen.getByText('未設定 新案件月嫂')).toBeInTheDocument();
    const currentSignal = mocks.searchInquiryCandidates.mock.calls[1][2].signal as AbortSignal;
    unmount();
    expect(currentSignal.aborted).toBe(true);
    expect(mocks.searchInquiryCandidates).toHaveBeenCalledTimes(2);
  });

  it('抽屜重新開啟自動重新讀取人選，空結果有明確提示', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability({ candidate_options: [] }));
    const first = render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} />);
    await screen.findByText('目前沒有可詢問月嫂');
    first.unmount();
    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} />);
    await screen.findByText('目前沒有可詢問月嫂');
    expect(mocks.searchInquiryCandidates).toHaveBeenCalledTimes(2);
    expect(mocks.addCandidates).not.toHaveBeenCalled();
  });

  it('姓名旁直接呈現不符者的原值，仍可選取及加入', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability({ candidate_options: [{ ...eligible,
      matching_conditions: {
        region: { status: 'not_matched', required_value: '新竹市', staff_values: ['桃園市', '台北市'] },
        preferred_service_days: { status: 'not_matched', required_value: '週休一日', staff_values: ['週休二日'] },
      },
    }] }));
    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} />);
    const original = await screen.findByText('週間服務：週休二日', { exact: false });
    expect(original).toHaveTextContent('不符合');
    expect(screen.getByText('區域：桃園市、台北市', { exact: false })).toHaveTextContent('不符合');
    expect(original.closest('.candidate-name-and-preferences')).toHaveTextContent('正式合格月嫂');
    fireEvent.click(screen.getByRole('checkbox', { name: '選擇正式候選 正式合格月嫂' }));
    expect(screen.getByRole('button', { name: '加入候選池（1）' })).toBeEnabled();
  });

  it('案件需求未填仍顯示月嫂原值，未知資料以待確認呈現', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability({ candidate_options: [{ ...eligible,
      matching_conditions: { region: { status: 'pending', required_value: null, staff_values: ['新竹市'] }, preferred_service_days: { status: 'pending', required_value: null, staff_values: [] } },
    }] }));
    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} />);
    expect(await screen.findByText('區域：新竹市', { exact: false })).toHaveTextContent('待確認');
    expect(screen.getByText('週間服務：尚未登錄', { exact: false })).toHaveTextContent('待確認');
  });

  it('客戶特殊週間值無人可明確符合時，同時顯示雙方原值並允許逐位加入', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability({ candidate_options: [
      { ...eligible, matching_conditions: { ...eligible.matching_conditions,
        preferred_service_days: { status: 'pending', required_value: '每月排休六天', staff_values: ['週休二日'] } } },
      { ...partial, matching_conditions: { ...eligible.matching_conditions,
        preferred_service_days: { status: 'pending', required_value: '每月排休六天', staff_values: ['其他（可協調排休）'] } } },
    ] }));
    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} presentation="workbench" />);
    expect(await screen.findByText('可詢問 2 位')).toBeInTheDocument();
    expect(screen.getByLabelText('本案需求')).toHaveTextContent('週間服務：每月排休六天');
    for (const value of ['週休二日', '其他（可協調排休）']) expect(screen.getByText(`週間服務：${value}`, { exact: false })).toHaveTextContent('待確認');
    for (const name of ['正式合格月嫂', '部分可用月嫂']) expect(screen.getByRole('button', { name: `加入候選池（${name}）` })).toBeEnabled();
  });

  it('保留衝突候選並提示公會協調', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability({
      complete_combinations: [],
      conflicts: [
        { segment_index: 0, staff_id: 8893, work_date: '2026-09-01', reason_code: 'active_lock' },
        { segment_index: 0, staff_id: 8893, work_date: '2026-09-02', reason_code: 'buffer' },
      ],
    }));
    render(<OrderCandidateQueryPanel caseNo="115000204" />);


    await waitFor(() => expect(mocks.searchInquiryCandidates).toHaveBeenCalledWith(
      '115000204',
      allFilters,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    expect(await screen.findByText('未設定 正式合格月嫂')).toBeInTheDocument();
    expect(screen.getByText('未設定 正式合格月嫂')).toBeInTheDocument();
    expect(screen.getByText('未設定 部分可用月嫂')).toBeInTheDocument();
    expect(screen.getByText(/空閒 5\/5 天/)).toBeInTheDocument();
    expect(screen.getByText(/空閒 0\/5 天/)).toBeInTheDocument();
    expect(screen.getByText(/有檔期衝突，待公會協調/)).toBeInTheDocument();
    expect(screen.getByText(/七天緩衝期重疊，僅提醒/)).toBeInTheDocument();
    expect(screen.getByText('服務期間：2026-09-01 ～ 2026-09-05')).toBeInTheDocument();
    expect(screen.queryByText(/2026-09-01 · 檔期衝突/)).not.toBeInTheDocument();
    expect(screen.queryByText(/2026-09-02 · 七天緩衝期/)).not.toBeInTheDocument();
  });

  it('只有衝突候選時仍可選取並加入候選池', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability({
      feasibility: 'partial',
      complete_combinations: [],
      segment_candidates: [],
      candidate_options: [partial],
    }));
    render(<OrderCandidateQueryPanel caseNo="115000204" />);


    expect(await screen.findByText('可詢問 1 位')).toBeInTheDocument();
    expect(screen.getByText(/有檔期衝突，待公會協調/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: '選擇正式候選 部分可用月嫂' }));
    expect(screen.getByRole('button', { name: '加入候選池（1）' })).toBeEnabled();
  });

  it.each([
    [new ApiNetworkError('Failed to fetch'), '目前無法連線，請確認網路後重新查詢。'],
    [new ApiTimeoutError(30000), '查詢逾時，請稍後重新查詢。'],
  ])('查詢連線失敗或逾時有中文提示並可重新查詢：%s', async (error, message) => {
    mocks.searchInquiryCandidates.mockRejectedValueOnce(error).mockResolvedValueOnce(availability());
    render(<OrderCandidateQueryPanel caseNo="115000204" />);


    expect(await screen.findByText('查詢失敗')).toBeInTheDocument();
    expect(screen.getByText(message)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢' }));
    await screen.findByText('可詢問 2 位');
    expect(mocks.searchInquiryCandidates).toHaveBeenCalledTimes(2);
  });

  it('寫入後以 receipt candidate id 回讀相同人選，再通知待辦投影刷新；不發送聯絡', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability());
    mocks.addCandidates.mockResolvedValue({ pool_id: 9, candidate_ids: [17], status: 'recorded' });
    mocks.queryPool.mockResolvedValue(candidatePool());
    const onPoolReadback = vi.fn();
    render(<OrderCandidateQueryPanel caseNo="115000204" onPoolReadback={onPoolReadback} />);

    fireEvent.click(await screen.findByRole('checkbox', { name: '選擇正式候選 正式合格月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '加入候選池（1）' }));

    await waitFor(() => expect(mocks.addCandidates).toHaveBeenCalledWith(expect.objectContaining({
      caseNo: '115000204',
      actor: 'operator-1',
      eventKey: 'orders-candidate-pool-add-original-key',
      candidates: [{ staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-05' }],
    })));
    await waitFor(() => expect(mocks.queryPool).toHaveBeenCalledWith('115000204'));
    await waitFor(() => expect(onPoolReadback).toHaveBeenCalledTimes(1));
    expect(mocks.sendInformation).not.toHaveBeenCalled();
    expect(await screen.findByText(/Pool #9 · 已回讀 1 位本次寫入候選：未設定 正式合格月嫂。/)).toBeInTheDocument();
  });

  it('回讀 receipt candidate id 對應到不同人員時 fail closed，不刷新待辦投影', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability());
    mocks.addCandidates.mockResolvedValue({ pool_id: 9, candidate_ids: [17], status: 'recorded' });
    mocks.queryPool.mockResolvedValue(candidatePool(9999, '錯誤月嫂'));
    const onPoolReadback = vi.fn();
    render(<OrderCandidateQueryPanel caseNo="115000204" onPoolReadback={onPoolReadback} />);

    fireEvent.click(await screen.findByRole('checkbox', { name: '選擇正式候選 正式合格月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '加入候選池（1）' }));

    expect(await screen.findByText('候選池回讀與本次寫入選擇不一致。')).toBeInTheDocument();
    expect(onPoolReadback).not.toHaveBeenCalled();
    expect(mocks.sendInformation).not.toHaveBeenCalled();
  });
});
