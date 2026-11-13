import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderServiceDatesPanel } from '../../../../../../../components/OrderServiceDatesPanel';
import { ordersMutationClient } from '../../../../../../../api/orders/order_mutation_client';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { OrderOfficialDateCorrectionPanel } from '../../../../../../../components/OrderOfficialDateCorrectionPanel';
import { OrderServiceAttributionPanel } from '../../../../../../../components/OrderServiceAttributionPanel';
vi.mock('../../../../../../../api/scheduling/holiday_client', () => ({ holidayClient: { query: vi.fn(async () => ({ holidays: [] })) } }));
vi.mock('../../../../../../../components/StaffIdentityProvider', () => ({
  useStaffIdentityDirectory: () => ({ people: new Map([7, 8, 9, 10].map(id => [id, { id, name: `月嫂 ${id}` }])) }),
  useStaffIdentityLabels: () => ({ label: (id: number) => `月嫂 ${id}`, compare: (a: number, b: number) => a - b }),
}));

const mocks = vi.hoisted(() => ({ query: vi.fn(), preview: vi.fn(), apply: vi.fn(), previewAttribution: vi.fn(), applyAttribution: vi.fn() }));
vi.mock('../../../../../../../api/orders/official_service_date_correction_client', () => ({
  officialServiceDateCorrectionClient: mocks,
}));

const original = {
  case_no: 'ISSUE-346', order_version: 1, scheduling_version: 1, generation_id: 11,
  order_status: '訂單完成', service_data_locked: true, actual_end_date: '2026-09-20',
  monetary_change_blocker: false,
  monetary_blockers: [],
  assignments: [{ assignment_id: 13, staff_id: 7, staff_name: '王月嫂', service_dates: ['2026-09-19', '2026-09-20'] }],
};
const changed = {
  ...original, order_version: 2, scheduling_version: 2, generation_id: 12,
  actual_end_date: '2026-09-21',
  assignments: [{ assignment_id: 14, staff_id: 7, staff_name: '王月嫂', service_dates: ['2026-09-19', '2026-09-21'] }],
};

it('makes date changes explicit and previews only the affected days before saving', async () => {
  const serviceDates = ['2099-11-25', '2099-11-26'];
  mocks.previewAttribution.mockResolvedValue({
    proposed_assignments: [{ staff_id: 7, service_dates: ['2099-11-26', '2099-11-28'] }],
    staff_entitlements: [], funding: [], paid_obligations: [], manual_amounts: [],
  });
  render(<OrderServiceAttributionPanel caseNo="ISSUE-346" upcomingOnly onSaved={vi.fn()} onBusyChange={vi.fn()}
    segments={[{ assignment_id: 13, staff_id: 7, candidate_key: null, sequence: 1, assigned_start_date: serviceDates[0],
      assigned_end_date: serviceDates[1], official_service_dates: serviceDates, actual_hours: null, lineage_source_assignment_ids: [] }]} />);
  expect(screen.getByText(/已分配 2／2 日/)).toBeVisible();
  expect(screen.queryByLabelText('2099-11-25 改至')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('調整依據（必填）'), { target: { value: '電話確認' } });
  fireEvent.change(screen.getByLabelText('調整原因（必填）'), { target: { value: '改期' } });
  const preview = screen.getByRole('button', { name: '預覽排班與帳務' });
  expect(preview).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', { name: '調整服務日期' }));
  fireEvent.change(screen.getByLabelText('2099-11-25 改至'), { target: { value: '2099-11-28' } });
  fireEvent.click(preview);
  expect(await screen.findByRole('row', { name: /2099-11-25.*2099-11-28/ })).toBeVisible();
  expect(screen.queryByRole('row', { name: /2099-11-26/ })).not.toBeInTheDocument();
  expect(mocks.previewAttribution).toHaveBeenCalledWith('ISSUE-346', expect.objectContaining({
    moves: [{ source_assignment_id: 13, source_date: '2099-11-25', staff_id: 7,
      replacement_date: '2099-11-28', target_assignment_id: 13 }],
  }));
  expect(mocks.applyAttribution).not.toHaveBeenCalled();
});

it('adds a fourth calendar and previews transfers from multiple source blocks in one request', async () => {
  const dates = ['2099-11-25', '2099-11-26', '2099-11-27', '2099-11-28'];
  mocks.previewAttribution.mockClear().mockResolvedValue({
    proposed_assignments: [], staff_entitlements: [], funding: [], paid_obligations: [], manual_amounts: [],
  });
  render(<OrderServiceAttributionPanel caseNo="ISSUE-346" upcomingOnly onSaved={vi.fn()} onBusyChange={vi.fn()}
    segments={[7, 8, 9].map((id, index) => ({
      assignment_id: 13 + index, staff_id: id, candidate_key: null, sequence: index + 1,
      assigned_start_date: dates[index], assigned_end_date: index === 2 ? dates[3] : dates[index],
      official_service_dates: index === 2 ? dates.slice(2) : [dates[index]], actual_hours: null, lineage_source_assignment_ids: [],
    }))} />);
  fireEvent.click(screen.getByRole('button', { name: '＋ 新增月嫂' }));
  fireEvent.change(screen.getByLabelText('選擇月嫂'), { target: { value: '10' } });
  const fourth = within(screen.getByRole('region', { name: '月嫂 10' }));
  fireEvent.click(fourth.getByRole('button', { name: /2099-11-25.*目前由 月嫂 7/ }));
  fireEvent.click(fourth.getByRole('button', { name: /2099-11-26.*目前由 月嫂 8/ }));
  expect(fourth.getByText('負責 2 日')).toBeVisible();
  expect(within(screen.getByRole('region', { name: '月嫂 7' })).getByText('負責 0 日')).toBeVisible();
  expect(screen.getByRole('button', { name: '＋ 新增月嫂' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('調整依據（必填）'), { target: { value: '電話確認' } });
  fireEvent.change(screen.getByLabelText('調整原因（必填）'), { target: { value: '交接' } });
  fireEvent.click(screen.getByRole('button', { name: '預覽排班與帳務' }));
  expect(await screen.findByRole('row', { name: /2099-11-25.*月嫂 7.*月嫂 10/ })).toBeVisible();
  expect(mocks.previewAttribution).toHaveBeenCalledOnce();
  expect(mocks.previewAttribution).toHaveBeenCalledWith('ISSUE-346', {
    scope: 'upcoming', evidence: '電話確認', moves: dates.slice(0, 2).map((date, index) => ({
      source_assignment_id: 13 + index, source_date: date, staff_id: 10, replacement_date: date, target_assignment_id: null,
    })),
  });
});

describe('official date correction panel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('crypto', { randomUUID: () => 'issue346-key' });
    mocks.query.mockResolvedValueOnce(original).mockResolvedValueOnce(changed);
    mocks.preview.mockImplementation(async (_caseNo, assignments) => ({
      ...original, proposed_assignments: assignments,
      finance_impact: 'no_op', payroll_impact: 'no_op', preview_fingerprint: 'a'.repeat(64),
    }));
    mocks.apply.mockResolvedValue({
      case_no: 'ISSUE-346', order_version: 2, scheduling_version: 2, generation_id: 12,
      effective_assignments: [{ assignment_id: 14, service_dates: ['2026-09-19', '2026-09-21'] }],
      preview_fingerprint: 'a'.repeat(64),
    });
  });

  it('saves a full corrected allocation in one action and requires effective readback', async () => {
    const onObserved = vi.fn();
    render(<OrderOfficialDateCorrectionPanel caseNo="ISSUE-346" onObserved={onObserved} />);
    const second = await screen.findByRole('button', { name: '服務日期 2026-09-20' });
    fireEvent.click(second);
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-09-21' }));
    fireEvent.change(screen.getByLabelText('更正原因（選填）'), { target: { value: '原正式日期登錄錯誤' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存更正' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('ISSUE-346', [
      { assignment_id: 13, service_dates: ['2026-09-19', '2026-09-21'] },
    ]));
    await waitFor(() => expect(onObserved).toHaveBeenCalledOnce());
    expect(mocks.apply).toHaveBeenCalledWith('ISSUE-346', expect.objectContaining({
      preview_fingerprint: 'a'.repeat(64),
    }), '原正式日期登錄錯誤', 'issue346-key');
    expect(mocks.query).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('status')).toHaveTextContent('排班日期已更正');
  });

  it('preserves the saved confirmation when the case refreshes and clears it when changing cases', async () => {
    mocks.query.mockReset().mockResolvedValueOnce(original).mockResolvedValue(changed);
    function CasePage() {
      const [revision, setRevision] = useState(0);
      const [caseNo, setCaseNo] = useState('ISSUE-346');
      return <><button onClick={() => setCaseNo('OTHER-CASE')}>切換案件</button>
        <OrderOfficialDateCorrectionPanel caseNo={caseNo} revision={revision}
          onObserved={() => setRevision(value => value + 1)} /></>;
    }
    render(<CasePage />);
    fireEvent.click(await screen.findByRole('button', { name: '服務日期 2026-09-20' }));
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-09-21' }));
    fireEvent.change(screen.getByLabelText('更正原因（選填）'), { target: { value: '日期核對更正' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存更正' }));
    await waitFor(() => expect(mocks.query).toHaveBeenCalledTimes(3));
    expect(screen.getByRole('status')).toHaveTextContent('排班日期已更正');
    fireEvent.click(screen.getByRole('button', { name: '切換案件' }));
    await waitFor(() => expect(screen.queryByText(/排班日期已更正/)).not.toBeInTheDocument());
  });

  it('shows both caregivers and rejects readback that assigns a substitute date to the wrong caregiver', async () => {
    const multiOriginal = {
      ...original,
      assignments: [
        { assignment_id: 13, staff_id: 7, staff_name: '王月嫂', service_dates: ['2026-09-19'] },
        { assignment_id: 15, staff_id: 8, staff_name: '代班李月嫂', service_dates: ['2026-09-20'] },
      ],
    };
    const swappedReadback = {
      ...changed,
      assignments: [
        { assignment_id: 14, staff_id: 7, staff_name: '王月嫂', service_dates: ['2026-09-21'] },
        { assignment_id: 16, staff_id: 8, staff_name: '代班李月嫂', service_dates: ['2026-09-19'] },
      ],
    };
    mocks.query.mockReset().mockResolvedValueOnce(multiOriginal).mockResolvedValueOnce(swappedReadback);
    mocks.apply.mockResolvedValue({
      case_no: 'ISSUE-346', order_version: 2, scheduling_version: 2, generation_id: 12,
      effective_assignments: [
        { assignment_id: 14, service_dates: ['2026-09-19'] },
        { assignment_id: 16, service_dates: ['2026-09-21'] },
      ],
      preview_fingerprint: 'a'.repeat(64),
    });
    const onObserved = vi.fn();
    render(<OrderOfficialDateCorrectionPanel caseNo="ISSUE-346" onObserved={onObserved} />);
    await screen.findByRole('combobox', { name: '服務月嫂與分段' });
    expect(screen.getByRole('button', { name: '服務日期 2026-09-19' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.change(screen.getByRole('combobox', { name: '服務月嫂與分段' }), { target: { value: '15' } });
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-09-20' }));
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-09-21' }));
    fireEvent.change(screen.getByLabelText('更正原因（選填）'), { target: { value: '代班日期登錄錯誤' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存更正' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('ISSUE-346', [
      { assignment_id: 13, service_dates: ['2026-09-19'] },
      { assignment_id: 15, service_dates: ['2026-09-21'] },
    ]));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('提交後排班回讀不一致'));
    expect(onObserved).not.toHaveBeenCalled();
  });

  it('keeps rejected dates editable and can restore the formal dates without applying', async () => {
    mocks.query.mockReset().mockResolvedValue(original);
    mocks.preview.mockRejectedValue(new Error('2026-09-21 與月嫂其他案件檔期衝突，請調整服務日期後重新預覽。'));
    render(<OrderOfficialDateCorrectionPanel caseNo="ISSUE-346" />);
    const second = await screen.findByRole('button', { name: '服務日期 2026-09-20' });
    fireEvent.click(second);
    expect(screen.getByRole('button', { name: '儲存更正' })).toBeDisabled();
    expect(screen.getByText('每段服務天數必須與原紀錄相同，請在月曆取消或補選日期。')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-09-21' }));
    fireEvent.click(screen.getByRole('button', { name: '儲存更正' }));
    await screen.findByText(/其他案件檔期衝突/);
    expect(second).toBeEnabled();
    expect(second).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByRole('button', { name: '重新讀取排班日期' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '服務日期 2026-09-20' })).toHaveAttribute('aria-pressed', 'true'));
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('provides a retry entrance when the original dates cannot be loaded', async () => {
    mocks.query.mockReset().mockRejectedValueOnce(new Error('排班資料暫時無法取得')).mockResolvedValueOnce(original);
    render(<OrderOfficialDateCorrectionPanel caseNo="ISSUE-346" />);
    await screen.findByText('排班資料暫時無法取得');
    fireEvent.click(screen.getByRole('button', { name: '重新讀取排班日期' }));
    await screen.findByRole('button', { name: '服務日期 2026-09-19' });
    expect(mocks.query).toHaveBeenCalledTimes(2);
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('completed mode uses the existing calendar without querying or writing pre-service dates', async () => {
    const correctedDates = ['2026-09-19', '2026-10-01'];
    mocks.query.mockReset().mockResolvedValueOnce(original).mockResolvedValue({ ...changed,
      actual_end_date: '2026-10-01', assignments: [{ ...changed.assignments[0], service_dates: correctedDates }] });
    mocks.apply.mockResolvedValue({ case_no: 'ISSUE-346', order_version: 2, scheduling_version: 2, generation_id: 12,
      effective_assignments: [{ assignment_id: 14, service_dates: correctedDates }], preview_fingerprint: 'a'.repeat(64) });
    const queryDates = vi.spyOn(ordersMutationClient, 'getServiceDates');
    const actualStart = vi.spyOn(ordersQueryClient, 'getActualStart');
    render(<OrderServiceDatesPanel caseNo="ISSUE-346" completedCorrection />);
    await screen.findByRole('group', { name: '服務日期月曆' });
    expect(document.querySelectorAll('input[type="date"]')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-09-20' }));
    fireEvent.click(screen.getByRole('button', { name: '下一個月' }));
    fireEvent.click(screen.getByRole('button', { name: '服務日期 2026-10-01' }));
    fireEvent.click(screen.getByRole('button', { name: '儲存更正' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('ISSUE-346', [
      { assignment_id: 13, service_dates: ['2026-09-19', '2026-10-01'] },
    ]));
    await screen.findByText(/排班日期已更正/);
    expect(queryDates).not.toHaveBeenCalled();
    expect(actualStart).not.toHaveBeenCalled();
    expect(mocks.apply).toHaveBeenCalledWith('ISSUE-346', expect.objectContaining({
      proposed_assignments: [{ assignment_id: 13, service_dates: correctedDates }],
    }), '', 'issue346-key');
    queryDates.mockRestore(); actualStart.mockRestore();
  });

  it('keeps the original monetary blocker on the calendar and never previews or applies', async () => {
    mocks.query.mockReset().mockResolvedValue({ ...original, monetary_change_blocker: true,
      monetary_blockers: [{ code: 'special_pay', message: '已有特殊薪資紀錄，純日期更正尚不能處理其薪資影響。', repair_target: 'payroll' }],
    });
    render(<OrderOfficialDateCorrectionPanel caseNo="ISSUE-346" />);
    await screen.findByText('已有特殊薪資紀錄，純日期更正尚不能處理其薪資影響。');
    expect(screen.getByRole('link', { name: '核對本案月嫂應付款 →' })).toHaveAttribute('href', '#finance?tab=client-receipts&case_no=ISSUE-346&from=workbench');
    expect(screen.getByRole('button', { name: '服務日期 2026-09-20' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '儲存更正' })).toBeDisabled();
    expect(mocks.preview).not.toHaveBeenCalled();
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it.each([
    ['payroll', 'special_pay', '已有特殊薪資紀錄', '核對本案月嫂應付款 →', '#finance?tab=client-receipts&case_no=ISSUE-346&from=workbench'],
    ['subsidy', 'subsidy_return', '已有補助退還義務', '核對本案補助明細 →', '#finance?tab=subsidy-advance&case_no=ISSUE-346&from=workbench'],
    ['case_profile', 'floor_fee', '原排班已分配樓層費', '核對案件服務與費用資料 →', '#clients?case=ISSUE-346&from=workbench'],
  ])('shows a case-bound correction entrance for %s and reloads resolved blockers', async (repairTarget, code, message, label, href) => {
    mocks.query.mockReset().mockResolvedValueOnce({ ...original, monetary_change_blocker: true,
      monetary_blockers: [{ code, message, repair_target: repairTarget }],
    }).mockResolvedValue(original);
    render(<OrderOfficialDateCorrectionPanel caseNo="ISSUE-346" />);
    await screen.findByText(message);
    expect(screen.getByRole('link', { name: label })).toHaveAttribute('href', href);
    fireEvent.click(screen.getByRole('button', { name: '重新讀取排班日期' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '服務日期 2026-09-20' })).toBeEnabled());
    expect(screen.queryByText(message)).not.toBeInTheDocument();
    expect(mocks.preview).not.toHaveBeenCalled();
    expect(mocks.apply).not.toHaveBeenCalled();
  });

});
