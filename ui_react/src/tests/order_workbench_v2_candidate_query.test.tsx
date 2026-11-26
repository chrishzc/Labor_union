import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { OrderCandidateQueryPanel } from '../components/OrderCandidateQueryPanel';
import { CandidateInquiryDialog } from '../components/CandidateInquiryDialog';
import { UnsavedChangesProvider, useUnsavedNavigation } from '../components/UnsavedChanges';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { publishStaffAvailabilityChange } from '../api/staff_availability/staff_availability_changes';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../api/shared/typed_errors';

const mocks = vi.hoisted(() => ({
  searchInquiryCandidates: vi.fn(),
  addCandidates: vi.fn(),
  queryPool: vi.fn(),
  sendInformation: vi.fn(),
  createAddCandidatesCommand: vi.fn(),
}));

vi.mock('../api/scheduling/commute_client', () => ({ commuteClient: {
  usage: vi.fn().mockResolvedValue({ billing_month: '2026-10', configured: true, free_limit: 1000,
    local_requests: 0, free_used: 0, free_remaining: 1000, uncertain_requests: 0, paid_requests: 0,
    estimated_cost_usd: '0.00', verified_count: null, verified_through: null, verified_at: null }),
  history: vi.fn((caseNo: string) => Promise.resolve({ case_no: caseNo, records: [] })),
  query: vi.fn(), reconcile: vi.fn(),
} }));

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

function CandidateDialog({ presentation, onLeave, onReadback }: {
  presentation: 'legacy' | 'workbench'; onLeave: () => void; onReadback: () => void;
}) {
  const { requestLeave } = useUnsavedNavigation();
  const [open, setOpen] = useState(true);
  const [editState, setEditState] = useState({ dirty: false, busy: false });
  return <>
    <button onClick={() => requestLeave(onLeave)}>離開案件</button>
    {open && <CandidateInquiryDialog title="新增候選月嫂" busy={editState.busy}
      onClose={() => requestLeave(() => { setOpen(false); onLeave(); })}>
      <OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} presentation={presentation}
        onEditStateChange={setEditState} onPoolReadback={onReadback} />
    </CandidateInquiryDialog>}
  </>;
}

describe('待辦看板 Beta 第 2 階正式候選查詢、候選池寫入與回讀', () => {
  beforeEach(() => {
    orderMutationFlowStore.clearAll();
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.createAddCandidatesCommand.mockImplementation((caseNo, candidates) => ({
      caseNo,
      candidates,
      actor: 'operator-1',
      eventKey: 'orders-candidate-pool-add-original-key',
    }));
  });

  it.each([
    ['candidate_contact_order_not_negotiating', '本案目前無法繼續媒合'],
    ['candidate_matching_assignment_present', '正式換人或代班'],
    ['candidate_matching_data_needs_review', '排班資料待核對'],
    ['candidate_matching_service_started', '辦理代班'],
    ['candidate_inquiry_dates_missing', '保存案件日期'],
    ['candidate_inquiry_dates_invalid', '保存正確的案件日期'],
    ['candidate_inquiry_dates_too_long', '超過 60 天'],
  ])('查詢遇到 %s 時顯示業務指引', async (code, message) => {
    mocks.searchInquiryCandidates.mockRejectedValue(new ApiHttpError(409, code, code));
    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(message);
    expect(alert).not.toHaveTextContent(code);
    expect(alert).toHaveTextContent('被既有條件阻擋');
  });

  it('新增時月嫂不具資格會提示確認名冊或改選', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability());
    mocks.addCandidates.mockRejectedValue(new ApiHttpError(409, 'candidate_staff_not_active', 'candidate_staff_not_active'));
    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} />);
    fireEvent.click(await screen.findByRole('checkbox', { name: '選擇正式候選 正式合格月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '加入候選池（1）' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('確認月嫂名冊或改選其他月嫂');
  });

  it('寫入後回讀資料待核對時保留未確認操作', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability());
    mocks.addCandidates.mockResolvedValue({ pool_id: 9, candidate_ids: [17] });
    mocks.queryPool.mockRejectedValue(new ApiHttpError(409, 'candidate_matching_data_needs_review', 'generation 42'));
    const onReadback = vi.fn();
    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} onPoolReadback={onReadback} />);
    fireEvent.click(await screen.findByRole('checkbox', { name: '選擇正式候選 正式合格月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '加入候選池（1）' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('排班資料待核對');
    expect(alert).not.toHaveTextContent('generation 42');
    expect(onReadback).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '加入候選池（1）' })).toBeDisabled();
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

  it('按日期燈號分組，同組依兩項偏好、週間、地區、編號排序', async () => {
    mocks.queryPool.mockResolvedValue({ ...candidatePool(), candidates: [] });
    const mismatch = { status: 'not_matched', required_value: '新竹市', staff_values: ['竹北市'] };
    const pending = { status: 'pending', required_value: '週休一日', staff_values: [] };
    mocks.searchInquiryCandidates.mockResolvedValue(availability({ candidate_options: [
      { ...eligible, staff_id: 1, staff_name: '只有地區', staff_union_no: 'A1', matching_conditions: {
        ...eligible.matching_conditions, preferred_service_days: pending,
      } },
      { ...eligible, staff_id: 2, staff_name: '只有週間', staff_union_no: 'A2', matching_conditions: {
        ...eligible.matching_conditions, region: mismatch,
      } },
      { ...eligible, staff_id: 10, staff_name: '兩項符合甲', staff_union_no: 'A10' },
      { ...eligible, staff_id: 3, staff_name: '兩項符合乙', staff_union_no: 'A3' },
      { ...eligible, staff_id: 11, staff_name: '兩項未符合', staff_union_no: 'A0', matching_conditions: {
        region: mismatch, preferred_service_days: pending,
      } },
      { ...eligible, staff_id: 4, staff_name: '等待訂金警示', staff_union_no: 'A4' },
      { ...eligible, staff_id: 5, staff_name: '有正式排班', staff_union_no: 'A5',
        available_ranges: [
          { start_date: '2026-09-01', end_date: '2026-09-02' },
          { start_date: '2026-09-04', end_date: '2026-09-05' },
        ],
        coverage_day_count: 4, supported_day_count: 4,
        supported_service_dates: eligible.required_service_dates.filter(day => day !== '2026-09-03'),
        supported_ranges: [
          { start_date: '2026-09-01', end_date: '2026-09-02', service_day_count: 2 },
          { start_date: '2026-09-04', end_date: '2026-09-05', service_day_count: 2 },
        ],
        full_case_coverage: false, full_selected_segment_coverage: false, uncovered_segment_dates: ['2026-09-03'],
      },
      { ...partial, staff_id: 6, staff_name: '未覆蓋服務日', staff_union_no: 'A6' },
    ], conflicts: [
      { segment_index: 0, staff_id: 4, work_date: '2026-09-01', reason_code: 'active_lock' },
      { segment_index: 0, staff_id: 5, work_date: '2026-09-02', reason_code: 'buffer' },
      { segment_index: 0, staff_id: 5, work_date: '2026-09-03', reason_code: 'schedule', case_no: '115000205' },
      { segment_index: 1, staff_id: 3, work_date: '2026-09-04', reason_code: 'assignment' },
    ] }));

    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} presentation="workbench" />);
    const list = await screen.findByLabelText('可詢問月嫂');
    const groups = within(list).getAllByRole('region');
    expect(groups.map(group => group.getAttribute('aria-label'))).toEqual(['無日期衝突', '有日期警示', '有日期衝突']);
    expect(within(groups[0]).getByRole('heading')).toHaveTextContent('無日期衝突（5）');
    const buttons = within(list).getAllByRole('button', { name: /^加入候選池/ });
    expect(buttons.map(button => button.getAttribute('aria-label'))).toEqual([
      '加入候選池（兩項符合乙）', '加入候選池（兩項符合甲）', '加入候選池（只有週間）', '加入候選池（只有地區）',
      '加入候選池（兩項未符合）', '加入候選池（等待訂金警示）', '加入候選池（有正式排班）', '加入候選池（未覆蓋服務日）',
    ]);
    expect(within(groups[2]).getByText('空閒 4/5 天')).toBeVisible();
    expect(within(groups[2]).getByText('已有正式排班：案件 115000205、2026-09-03')).toBeVisible();
    expect(within(list).getAllByText(/^已有正式排班：/)).toHaveLength(1);
    expect(list).not.toHaveTextContent(/影響日期|查看(?:衝突|檔期)日期與原因|待公會協調|尚缺可用人選|僅提醒|2026-09-0[1245]/);
    for (const button of buttons) expect(button).toBeEnabled();
  });

  it('日期未備妥不會顯示綠燈候選', async () => {
    mocks.queryPool.mockResolvedValue({ ...candidatePool(), candidates: [] });
    mocks.searchInquiryCandidates.mockRejectedValue(new ApiHttpError(409, 'candidate_inquiry_dates_missing', 'missing'));
    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} presentation="workbench" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('預計服務日期尚未完整');
    expect(screen.queryByRole('region', { name: '無日期衝突' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^加入候選池/ })).not.toBeInTheDocument();
  });

  it('automatically refreshes availability warnings after pause and restore changes', async () => {
    mocks.searchInquiryCandidates.mockResolvedValue(availability({ candidate_options: [eligible], conflicts: [] }));
    render(<OrderCandidateQueryPanel caseNo="115000204" includeMultiCaregiver={false} />);
    await screen.findByRole('checkbox', { name: '選擇正式候選 正式合格月嫂' });
    mocks.searchInquiryCandidates.mockResolvedValue(availability({ candidate_options: [partial], conflicts: [{ staff_id: partial.staff_id, work_date: '2026-09-01', reason_code: 'staff_unavailability' }] }));
    act(() => publishStaffAvailabilityChange(partial.staff_id));
    await screen.findByText(/有檔期衝突，待公會協調/);
    mocks.searchInquiryCandidates.mockResolvedValue(availability({ candidate_options: [eligible], conflicts: [] }));
    act(() => publishStaffAvailabilityChange(eligible.staff_id));
    await screen.findByRole('checkbox', { name: '選擇正式候選 正式合格月嫂' });
    expect(screen.queryByText(/有檔期衝突，待公會協調/)).not.toBeInTheDocument();
    expect(mocks.searchInquiryCandidates).toHaveBeenCalledTimes(3);
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
        { segment_index: 0, staff_id: 8893, work_date: '2026-09-03', reason_code: 'schedule' },
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
    expect(screen.getByText('七天緩衝期重疊，僅提醒')).toBeVisible();
    expect(screen.getByText('其他案件等待訂金保留，僅提醒。')).toBeVisible();
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
    expect(await screen.findByText(/已回讀 1 位本次寫入候選：未設定 正式合格月嫂。/)).toBeInTheDocument();
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

  it.each(['legacy', 'workbench'] as const)('%s：寫入與回讀中保護離開，成功回讀後正常關閉', async presentation => {
    const receipt = { pool_id: 9, candidate_ids: [17], status: 'recorded' };
    let finishAdd!: (value: typeof receipt) => void;
    let finishReadback!: (value: ReturnType<typeof candidatePool>) => void;
    mocks.searchInquiryCandidates.mockResolvedValue(availability());
    mocks.addCandidates.mockImplementationOnce(() => new Promise(resolve => { finishAdd = resolve; }));
    if (presentation === 'workbench') mocks.queryPool.mockResolvedValueOnce({ ...candidatePool(), candidates: [] });
    mocks.queryPool.mockImplementationOnce(() => new Promise(resolve => { finishReadback = resolve; }));
    const onLeave = vi.fn();
    const onReadback = vi.fn();
    render(<UnsavedChangesProvider><CandidateDialog presentation={presentation} onLeave={onLeave} onReadback={onReadback} /></UnsavedChangesProvider>);
    if (presentation === 'legacy') {
      fireEvent.click(await screen.findByRole('checkbox', { name: '選擇正式候選 正式合格月嫂' }));
      fireEvent.click(screen.getByRole('button', { name: '加入候選池（1）' }));
    } else {
      fireEvent.click(await screen.findByRole('button', { name: '加入候選池（正式合格月嫂）' }));
    }
    expect(screen.getByRole('button', { name: '關閉' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '離開案件' }));
    expect(screen.getByRole('button', { name: '捨棄變更並離開' })).toBeDisabled();
    expect(onLeave).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '繼續編輯' }));
    await act(async () => { finishAdd(receipt); });
    expect(screen.getByRole('button', { name: '關閉' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '離開案件' }));
    expect(screen.getByRole('button', { name: '捨棄變更並離開' })).toBeDisabled();
    expect(onReadback).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '繼續編輯' }));
    await act(async () => { finishReadback(candidatePool()); });
    await waitFor(() => expect(onReadback).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(onLeave).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it.each(['寫入結果未明', '回讀失敗'] as const)('%s：仍禁止捨棄離開，原操作確認成功後才解鎖', async failure => {
    const receipt = { pool_id: 9, candidate_ids: [17], status: 'recorded' };
    mocks.searchInquiryCandidates.mockResolvedValue(availability());
    mocks.queryPool.mockResolvedValueOnce({ ...candidatePool(), candidates: [] });
    if (failure === '寫入結果未明') mocks.addCandidates.mockRejectedValueOnce(new ApiTimeoutError(30000));
    else mocks.queryPool.mockRejectedValueOnce(new Error('回讀失敗'));
    mocks.addCandidates.mockResolvedValue(receipt);
    mocks.queryPool.mockResolvedValue(candidatePool());
    const onLeave = vi.fn();
    const onReadback = vi.fn();
    render(<UnsavedChangesProvider><CandidateDialog presentation="workbench" onLeave={onLeave} onReadback={onReadback} /></UnsavedChangesProvider>);
    fireEvent.click(await screen.findByRole('button', { name: '加入候選池（正式合格月嫂）' }));
    const retryLabel = failure === '寫入結果未明' ? '以原操作重新確認加入候選池' : '只重新讀取候選池結果';
    await screen.findByRole('button', { name: retryLabel });
    expect(screen.getByRole('button', { name: '關閉' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '離開案件' }));
    expect(screen.getByRole('button', { name: '捨棄變更並離開' })).toBeDisabled();
    expect(onLeave).not.toHaveBeenCalled();
    expect(onReadback).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '繼續編輯' }));
    fireEvent.click(screen.getByRole('button', { name: retryLabel }));
    await waitFor(() => expect(onReadback).toHaveBeenCalledOnce());
    expect(mocks.addCandidates).toHaveBeenCalledTimes(failure === '寫入結果未明' ? 2 : 1);
    if (failure === '寫入結果未明') expect(mocks.addCandidates.mock.calls[1][0]).toBe(mocks.addCandidates.mock.calls[0][0]);
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(onLeave).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
