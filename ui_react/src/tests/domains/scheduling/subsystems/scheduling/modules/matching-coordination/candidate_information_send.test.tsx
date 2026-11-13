import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { OrderCandidateContactStatusPanel } from '../../../../../../../components/OrderCandidateContactStatusPanel';
import { OrderInformationSheets } from '../../../../../../../components/OrderInformationSheets';
import { candidateContactPoolClient as client } from '../../../../../../../api/scheduling/candidate_contact_pool_client';
import { matchingCandidateWorkflowClient, type MatchingAvailability } from '../../../../../../../api/scheduling/matching_candidate_workflow_client';
import { publishStaffAvailabilityChange } from '../../../../../../../api/staff_availability/staff_availability_changes';
import { queryOrderInformation } from '../../../../../../../api/orders/order_information_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';

const { createInformationCommand, createWillingnessCommand } = vi.hoisted(() => ({ createInformationCommand: vi.fn(), createWillingnessCommand: vi.fn() }));
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({
  createCandidateInformationSendCommand: createInformationCommand,
  createCandidateWillingnessCommand: createWillingnessCommand,
  candidateContactPoolClient: { query: vi.fn(), previewInformation: vi.fn(), previewInformationPackage: vi.fn(), previewWeeklyService: vi.fn(), previewCaseInformation: vi.fn(), previewCaseWeeklyService: vi.fn(), sendInformation: vi.fn(), recordWillingness: vi.fn() },
}));
vi.mock('../../../../../../../api/scheduling/matching_candidate_workflow_client', async importOriginal => {
  const original = await importOriginal<typeof import('../../../../../../../api/scheduling/matching_candidate_workflow_client')>();
  return { ...original, matchingCandidateWorkflowClient: { ...original.matchingCandidateWorkflowClient, searchInquiryCandidates: vi.fn() } };
});
vi.mock('../../../../../../../api/orders/order_information_client', () => ({
  queryOrderInformation: vi.fn(),
}));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: {
  getOrderTerms: vi.fn(async () => ({ case_no: 'CASE-1', order_version: 1, scheduling_version: 0, scheduling_generation: 0, assignments: [] })),
  getOrderCalendarDetail: vi.fn(async () => ({ case_no: 'CASE-1', service_mode: null, original_service_type: '休五、日' })),
} }));
vi.mock('../../../../../../../api/orders/order_mutation_client', () => ({ ordersMutationClient: {
  getServiceDates: vi.fn(async () => ({ case_no: 'CASE-1', order_version: 1, scheduling_version: 0,
    current_version: null, current_dates: [], selectable_dates: ['2026-10-01', '2026-10-02'], contracted_service_days: 2 })),
} }));
const inquiryDates = ['2026-10-01', '2026-10-02'];
const inquiryRange = { start_date: '2026-10-01', end_date: '2026-10-02' };
const unknownPreference = { status: 'pending' as const, required_value: null, staff_values: [] };
const inquiryAvailability: MatchingAvailability = {
  case_no: 'CASE-1', planned_start_date: '2026-10-01', planned_end_date: '2026-10-02',
  feasibility: 'complete', complete_combinations: [], segment_candidates: [], conflicts: [],
  candidate_options: [{
    segment_index: 0, staff_id: 2, staff_name: '測試月嫂', coverage_day_count: 2, available_ranges: [inquiryRange],
    case_period_start: inquiryRange.start_date, case_period_end: inquiryRange.end_date,
    required_service_dates: inquiryDates, supported_service_dates: inquiryDates,
    supported_ranges: [{ ...inquiryRange, service_day_count: 2 }], supported_day_count: 2, required_day_count: 2,
    full_case_coverage: true, selected_segment_start: inquiryRange.start_date, selected_segment_end: inquiryRange.end_date,
    full_selected_segment_coverage: true, uncovered_segment_dates: [], source_scheduling_version: 0, filter_results: {},
    matching_conditions: { region: { ...unknownPreference }, preferred_service_days: { ...unknownPreference } },
  }],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(matchingCandidateWorkflowClient.searchInquiryCandidates).mockReset().mockResolvedValue(inquiryAvailability);
  orderMutationFlowStore.clearAll();
  let sent = false;
  vi.mocked(client.query).mockImplementation(async () => ({ case_no: 'CASE-1', pool_id: 1, candidates: [{
    id: 3, staff_id: 2, staff_name: '測試月嫂', status: 'active', willingness: 'pending', reason: null,
    latest_willingness_event_id: null,
    information: {
      '1': null, '2': null, '3': null,
      package: sent ? { status: 'queued', sent_at: '2026-10-01T00:00:00Z', event_id: 4, line_task_id: 5 } : null,
    }, service_start_date: '2026-10-01', service_end_date: '2026-10-02', created_at: '2026-09-01T00:00:00Z',
  }] } as never));
  createInformationCommand.mockImplementation((caseNo, candidateId, previewFingerprint, resend) => ({
    caseNo, candidateId, previewFingerprint, actor: 'operator-1', eventKey: 'information-package-key', resend,
  }));
  createWillingnessCommand.mockImplementation((caseNo, candidateId, willingness, reason) => ({
    caseNo, candidateId, willingness, reason, actor: 'operator-1', eventKey: 'willingness-command-key',
  }));
  vi.mocked(client.previewInformation).mockImplementation(async (caseNo, candidateId, kind) => ({
    case_no: caseNo, candidate_id: candidateId, info_type: kind, staff_name: '測試月嫂',
    text: `資訊${kind}：契約與服務約定`,
    line_sections: kind === 1 ? [
      { title: '服務約定', rows: [['預計服務開始日', '2026-10-01']] },
      { title: '客戶付款約定', rows: [
        ['訂金金額', 'NT$ 12,000'], ['預計訂金繳款日', '2026-09-20'],
        ['第一期金額', 'NT$ 36,000'], ['預計第一期繳款日', '2026-10-01'],
      ] },
    ] : [{ title: '飲食與照護需求', rows: [['服務報酬', '待確認']] }],
    preview_fingerprint: String(kind).repeat(64),
  }));
  vi.mocked(client.previewInformationPackage).mockImplementation(async (caseNo, candidateId) => ({
    case_no: caseNo, candidate_id: candidateId, staff_name: '測試月嫂',
    documents: await Promise.all(([1, 2, 3] as const).map(kind => client.previewInformation(caseNo, candidateId, kind))),
    reply_text: ['請確認檔期與條件後回覆是否願意承接。'], reply_actions: ['可以接案', '無法接案'],
    preview_fingerprint: 'a'.repeat(64),
  }));
  vi.mocked(client.previewWeeklyService).mockResolvedValue({ case_no: 'CASE-1', candidate_id: 3,
    required_service_days: 2, projected_service_days: 2, date_basis: 'planned', warnings: [], rows: [{
    serial_number: 1, staff_name: '測試月嫂', week_start_date: '2026-09-28', week_end_date: '2026-10-04',
    service_hours_per_day: 8, weekly_work_days: 2, weekly_hours: 16,
  }] });
  vi.mocked(client.sendInformation).mockImplementation(async () => {
    sent = true;
    return { status: 'queued', event_id: 4, line_task_id: 5 };
  });
  vi.mocked(client.previewCaseInformation).mockImplementation(async (caseNo, kind) => {
    const recipient = await client.previewInformation(caseNo, 3, kind);
    return { case_no: caseNo, info_type: kind, start_date: '2026-10-01', line_sections: recipient.line_sections,
      content_fingerprint: 'a'.repeat(64), send_allowed: true };
  });
  vi.mocked(client.previewCaseWeeklyService).mockResolvedValue({ case_no: 'CASE-1', required_service_days: 2,
    projected_service_days: 2, date_basis: 'confirmed', warnings: [], rows: [{ serial_number: 1,
      week_start_date: '2026-09-28', week_end_date: '2026-10-04', service_hours_per_day: 8, weekly_work_days: 2, weekly_hours: 16 }] });
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
});

async function openSharedPreview() {
  const panel = screen.getByRole('region', { name: '預覽案件資訊' });
  const previewButton = within(panel).getByRole('button', { name: '展開案件資訊預覽' });
  await waitFor(() => expect(previewButton).toBeEnabled());
  fireEvent.click(previewButton);
  await within(panel).findByRole('button', { name: '訂單資訊一' });
  return panel;
}

it('shows current reservations before LINE inquiry or manual willingness and refreshes after a change', async () => {
  const search = vi.mocked(matchingCandidateWorkflowClient.searchInquiryCandidates);
  search.mockResolvedValueOnce({ ...inquiryAvailability, conflicts: [
    { staff_id: 2, segment_index: 0, work_date: '2026-10-01', reason_code: 'active_lock' },
    { staff_id: 8, segment_index: 0, work_date: '2026-10-02', reason_code: 'staff_unavailability' },
  ] });
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" />);

  const card = within(await screen.findByRole('article'));
  fireEvent.click(await card.findByText('查看衝突日期與原因'));
  expect(card.getByText('其他案件等待訂金保留（黃色鎖）：2026-10-01')).toBeInTheDocument();
  expect(card.queryByText(/月嫂不可服務/)).not.toBeInTheDocument();
  fireEvent.click(card.getByRole('button', { name: '手動記錄接案意願（測試月嫂）' }));
  expect(card.getByRole('radio', { name: '願意承接' })).toBeEnabled();
  expect(card.queryByText('其他案件有等待訂金保留，仍可詢問及選定推薦月嫂。')).not.toBeInTheDocument();
  await openSharedPreview();
  expect(card.getByRole('button', { name: '確認寄送（測試月嫂）' })).toBeEnabled();
  expect(client.sendInformation).not.toHaveBeenCalled();

  search.mockResolvedValueOnce({ ...inquiryAvailability, planned_start_date: '2026-10-02', planned_end_date: '2026-10-03', conflicts: [
    { staff_id: 2, segment_index: 0, work_date: '2026-10-02', reason_code: 'schedule' },
    { staff_id: 2, segment_index: 0, work_date: '2026-10-03', reason_code: 'buffer' },
  ] });
  publishStaffAvailabilityChange(2);
  expect(await card.findByText('預計服務期間：2026-10-02 ～ 2026-10-03')).toBeVisible();
  expect(card.getByText('七天緩衝期重疊，僅提醒：2026-10-03')).toBeInTheDocument();
  expect(card.queryByText('七天緩衝期重疊，僅提醒', { exact: true })).not.toBeInTheDocument();
  expect(card.getByText('有檔期衝突，待公會協調')).toBeVisible();
  expect(card.queryByText('其他案件有等待訂金保留，仍可詢問及選定推薦月嫂。')).not.toBeInTheDocument();
});

it('offers a retry when the current availability cannot be checked', async () => {
  const search = vi.mocked(matchingCandidateWorkflowClient.searchInquiryCandidates);
  search.mockRejectedValueOnce(new Error('查詢失敗'));
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" />);
  const retry = await screen.findByRole('button', { name: '重新查詢檔期' });
  fireEvent.click(retry);
  await waitFor(() => expect(screen.queryByText('正在查詢候選月嫂的檔期…')).not.toBeInTheDocument());
  expect(search).toHaveBeenCalledTimes(2);
  expect(screen.queryByText('目前無法查詢候選月嫂的檔期。')).not.toBeInTheDocument();
});

it.each([null, 'sent', 'failed', 'queued', 'pending', 'retryable_failed', 'cancelled'] as const)('再次寄送不受前次寄送狀態 %s 或未儲存日期限制', async status => {
  const initial = await client.query('CASE-1');
  const candidate = initial.candidates[0];
  vi.mocked(client.previewCaseWeeklyService).mockResolvedValue({
    case_no: 'CASE-1', required_service_days: 2, projected_service_days: 0, date_basis: 'planned', warnings: [], rows: [],
  });
  vi.mocked(client.query).mockResolvedValueOnce({ ...initial, candidates: [{
    ...candidate, information: { ...candidate.information, package: status === null ? null : {
      status, sent_at: '2026-10-01T00:00:00Z', event_id: null, line_task_id: 4,
    } },
  }] });
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" />);
  const card = within(await screen.findByRole('article'));
  fireEvent.click(card.getByRole('button', { name: '再次寄送（測試月嫂）' }));
  const preview = await card.findByRole('region', { name: '寄送預覽' });
  const shared = within(screen.getByRole('region', { name: '預覽案件資訊' }));
  fireEvent.click(shared.getByRole('button', { name: '展開案件資訊預覽' }));
  expect(shared.queryByRole('button', { name: /再次寄送/ })).not.toBeInTheDocument();
  const confirm = await within(preview).findByRole('button', { name: '確認再次寄送' });
  expect(client.sendInformation).not.toHaveBeenCalled();
  expect(client.previewInformationPackage).toHaveBeenCalledWith('CASE-1', 3, expect.objectContaining({ resend: true }));
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
  await waitFor(() => expect(client.sendInformation).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
    candidateId: 3, resend: true, previewFingerprint: 'a'.repeat(64),
  })));
  await waitFor(() => expect(screen.queryByRole('region', { name: '寄送預覽' })).not.toBeInTheDocument());
  expect(screen.getByRole('button', { name: '再次寄送（測試月嫂）' })).toBeEnabled();
});

it('shows only changed information on the candidate card without opening another preview', async () => {
  const initial = await client.query('CASE-1');
  vi.mocked(client.query).mockResolvedValueOnce({ ...initial, candidates: [{
    ...initial.candidates[0], information_changes: [
      { document: '訂單資訊－1｜月嫂薪資', section: '服務約定', field: '預計開始日', before: '2026-10-01', after: '2026-10-02' },
      { document: '訂單資訊－2', section: '飲食需求', field: '過敏體質', before: null, after: '花生' },
    ],
  }] });
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" />);
  const card = within(await screen.findByRole('article'));
  expect(card.getByText('資料已改變，請重新寄送確認意願')).toBeVisible();
  expect(card.getByText('2026-10-01 → 2026-10-02')).toBeVisible();
  expect(card.getByText('未列出 → 花生')).toBeVisible();
  expect(card.queryByRole('region', { name: '寄送預覽' })).not.toBeInTheDocument();
  expect(client.sendInformation).not.toHaveBeenCalled();
  expect(client.query).toHaveBeenCalledWith('CASE-1', expect.objectContaining({ compareSentInformation: true }));
});

it('previews all four pages before the candidate cards and sends only from the named card', async () => {
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" />);
  expect(screen.getAllByRole('heading', { level: 3 }).map(heading => heading.textContent)).toEqual([
    '1. 設定每週服務說明', '2. 預覽案件資訊', '3. 選擇月嫂',
  ]);
  const sendButton = await screen.findByRole('button', { name: '確認寄送（測試月嫂）' });
  expect(sendButton).toBeDisabled();
  const panel = await openSharedPreview();
  await within(panel).findByText('第 1 頁，共 4 頁');
  expect(client.sendInformation).not.toHaveBeenCalled();
  expect(within(panel).queryByRole('button', { name: /確認寄送/ })).not.toBeInTheDocument();
  for (const name of ['訂單資訊二', '每週服務說明', '共用回覆卡']) {
    fireEvent.click(within(panel).getByRole('button', { name }));
    expect(within(panel).getByRole('button', { name })).toHaveAttribute('aria-pressed', 'true');
  }
  expect(within(panel).getByText('可以接案')).toBeInTheDocument();
  expect(within(panel).getByText('無法接案')).toBeInTheDocument();
  expect(screen.queryByText('選為收件月嫂')).not.toBeInTheDocument();
  fireEvent.click(within(panel).getByRole('button', { name: '收起案件資訊預覽' }));
  expect(within(panel).queryByRole('button', { name: '共用回覆卡' })).not.toBeInTheDocument();
  fireEvent.click(within(panel).getByRole('button', { name: '展開案件資訊預覽' }));
  expect(within(panel).getByRole('button', { name: '共用回覆卡' })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(within(panel).getByRole('button', { name: '收起案件資訊預覽' }));
  expect(sendButton).toBeEnabled();
  fireEvent.click(sendButton);
  expect(await screen.findByText(/等待發送/)).toBeInTheDocument();
  expect(client.sendInformation).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ candidateId: 3, previewFingerprint: 'a'.repeat(64) }));
  expect(screen.queryByRole('button', { name: '確認寄送（測試月嫂）' })).not.toBeInTheDocument();
});

it('previews the case documents before any candidate has been added', async () => {
  vi.mocked(client.query).mockResolvedValue({ case_no: 'CASE-1', pool_id: null, candidates: [] });
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" />);
  expect(await screen.findByText('尚未加入候選月嫂')).toBeInTheDocument();
  const panel = await openSharedPreview();
  expect(within(panel).getByText('第 1 頁，共 3 頁')).toBeInTheDocument();
  expect(client.previewInformationPackage).not.toHaveBeenCalled();
  expect(client.sendInformation).not.toHaveBeenCalled();
});

it('blocks preview and send until service dates have been saved', async () => {
  const preview = await client.previewCaseInformation('CASE-1', 3);
  vi.mocked(client.previewCaseInformation).mockResolvedValue({ ...preview, send_allowed: false });
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" />);
  expect(await screen.findByText('請先保存每週服務說明的日期。')).toBeInTheDocument();
  expect(await screen.findByRole('button', { name: '確認寄送（測試月嫂）' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '展開案件資訊預覽' }));
  const panel = screen.getByRole('region', { name: '預覽案件資訊' });
  expect(within(panel).getByText('保存每週服務說明後，即可預覽案件資訊。')).toBeInTheDocument();
  expect(within(panel).queryByRole('button', { name: '訂單資訊一' })).not.toBeInTheDocument();
  expect(client.previewInformationPackage).not.toHaveBeenCalled();
  expect(client.sendInformation).not.toHaveBeenCalled();
});

it('sends only the clicked candidate using their own fingerprint', async () => {
  const original = await client.query('CASE-1');
  const sent = new Set<number>();
  const first = original.candidates[0]!;
  const second = { ...first, id: 4, staff_id: 9, staff_name: '另一位月嫂' };
  const preview = await client.previewInformationPackage('CASE-1', first.id);
  vi.mocked(client.previewInformationPackage).mockImplementation(async (_caseNo, id) => ({
    ...preview, candidate_id: id, preview_fingerprint: (id === first.id ? 'a' : 'b').repeat(64),
  }));
  vi.mocked(client.query).mockImplementation(async () => ({ ...original, candidates: [first, second].map(item => ({
    ...item, information: { ...item.information, package: sent.has(item.id)
      ? { status: 'queued', sent_at: '2026-10-01T00:00:00Z', event_id: item.id, line_task_id: item.id + 10 } : null },
  })) }));
  vi.mocked(client.sendInformation).mockImplementation(async command => {
    sent.add(command.candidateId);
    return { status: 'queued', event_id: command.candidateId, line_task_id: command.candidateId + 10 };
  });
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" />);
  await openSharedPreview();
  expect(screen.getAllByRole('region', { name: '預覽案件資訊' })).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: '確認寄送（另一位月嫂）' }));
  expect(await screen.findByText(/等待發送/)).toBeInTheDocument();
  expect(client.sendInformation).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ candidateId: 4, previewFingerprint: 'b'.repeat(64) }));
  const firstSend = screen.getByRole('button', { name: '確認寄送（測試月嫂）' });
  await waitFor(() => expect(firstSend).toBeEnabled());
  fireEvent.click(firstSend);
  await waitFor(() => expect(screen.getAllByText(/等待發送/)).toHaveLength(2));
  expect(client.sendInformation).toHaveBeenNthCalledWith(2, expect.objectContaining({ candidateId: 3, previewFingerprint: 'a'.repeat(64) }));
});

it('requires reopening the case preview if the recipient documents have changed', async () => {
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" />);
  await openSharedPreview();
  const preview = await client.previewInformationPackage('CASE-1', 3);
  vi.mocked(client.previewInformationPackage).mockResolvedValue({
    ...preview, documents: preview.documents.map(part => ({ ...part, line_sections: [] })),
  });
  const sendButton = screen.getByRole('button', { name: '確認寄送（測試月嫂）' });
  fireEvent.click(sendButton);
  expect(await screen.findByRole('alert')).toHaveTextContent('案件資訊已更新，請重新核對預覽後再確認寄送。');
  expect(sendButton).toBeDisabled();
  expect(client.sendInformation).not.toHaveBeenCalled();
});

it.each([
  ['caregiver_has_no_line_delivery_identity', '月嫂尚未完成 LINE 綁定，無法寄送資訊。請先完成月嫂的 LINE 綁定後，再重新寄送。'],
  ['candidate_information_preview_stale', '訂單內容或月嫂的 LINE 綁定資料已更新。請重新開啟案件預覽，再確認寄送。'],
])('shows the send failure for %s without retrying or reporting an unknown outcome', async (code, message) => {
  const serverMessage = code === 'candidate_information_preview_stale' ? '請取消本次寄送，重新開啟寄送確認後再寄送。' : message;
  vi.mocked(client.sendInformation).mockRejectedValue(new ApiHttpError(409, code, serverMessage));
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" />);
  await openSharedPreview();
  fireEvent.click(await screen.findByRole('button', { name: '確認寄送（測試月嫂）' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(message);
  expect(screen.queryByText('寄送結果尚未確認；請確認寄送結果。')).not.toBeInTheDocument();
  expect(client.sendInformation).toHaveBeenCalledTimes(1);
});

it('retains the existing willingness note and explains an unchanged confirmation', async () => {
  const original = await client.query('CASE-1');
  const candidate = original.candidates[0]!;
  vi.mocked(client.query).mockResolvedValue({ ...original, candidates: [{ ...candidate, willingness: 'willing', reason: '既有電話紀錄' }] });
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" />);
  fireEvent.click(await screen.findByRole('button', { name: '手動記錄接案意願（測試月嫂）' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.getByRole('form', { name: '手動記錄接案意願（測試月嫂）' }).closest('article')).toHaveTextContent('測試月嫂');
  expect(screen.getByRole('textbox', { name: '詢問結果備註' })).toHaveValue('既有電話紀錄');
  expect(screen.getByRole('radio', { name: '願意承接' })).toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: '儲存接案意願' }));
  expect(await screen.findByText('目前已記錄相同意願與備註。')).toBeInTheDocument();
  expect(client.recordWillingness).not.toHaveBeenCalled();
});

it.each(['willing', 'unwilling'] as const)('saves %s from the candidate card, reads back its receipt and closes the inline form', async willingness => {
  const original = await client.query('CASE-1');
  const reason = willingness === 'unwilling' ? '檔期不合' : '';
  let saved = false;
  vi.mocked(client.query).mockImplementation(async () => ({ ...original, candidates: [{ ...original.candidates[0]!,
    willingness: saved ? willingness : 'pending', reason: saved ? reason || null : null, latest_willingness_event_id: saved ? 42 : null,
  }] }));
  vi.mocked(client.recordWillingness).mockImplementation(async () => { saved = true; return { status: 'recorded', event_id: 42 }; });
  const onObserved = vi.fn();
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" presentation="workbench" onObserved={onObserved} />);
  fireEvent.click(await screen.findByRole('button', { name: '手動記錄接案意願（測試月嫂）' }));
  const form = screen.getByRole('form', { name: '手動記錄接案意願（測試月嫂）' });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  fireEvent.click(within(form).getByRole('radio', { name: willingness === 'willing' ? '願意承接' : '無意願' }));
  expect(within(form).getByRole('textbox', { name: '詢問結果備註' })).not.toBeRequired();
  if (reason) fireEvent.change(within(form).getByRole('textbox', { name: '詢問結果備註' }), { target: { value: reason } });
  fireEvent.click(screen.getByRole('button', { name: '收起月嫂選擇' }));
  expect(screen.queryByRole('form', { name: '手動記錄接案意願（測試月嫂）' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '展開月嫂選擇' }));
  expect(screen.getByRole('form', { name: '手動記錄接案意願（測試月嫂）' })).toBe(form);
  expect(within(form).getByRole('textbox', { name: '詢問結果備註' })).toHaveValue(reason);
  fireEvent.submit(form);
  await waitFor(() => expect(screen.queryByRole('form', { name: '手動記錄接案意願（測試月嫂）' })).not.toBeInTheDocument());
  expect(client.recordWillingness).toHaveBeenCalledWith(expect.objectContaining({ candidateId: 3, willingness, reason }));
  expect(client.recordWillingness).toHaveBeenCalledTimes(1);
  expect(onObserved).toHaveBeenCalledTimes(1);
  expect(screen.getByText('回覆已儲存。')).toBeInTheDocument();
});

it('previews a candidate without creating or requiring an assignment', async () => {
  render(<OrderInformationSheets caseNo="CASE-1" assignments={[]} />);
  expect(await screen.findByText('契約重點截圖')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: '客戶付款約定' })).toBeInTheDocument();
  expect(screen.getByText('NT$ 12,000')).toBeInTheDocument();
  expect(screen.getByText('2026-09-20')).toBeInTheDocument();
  expect(screen.getByText('NT$ 36,000')).toBeInTheDocument();
  expect(screen.getAllByText('2026-10-01').length).toBeGreaterThan(0);
  expect(screen.queryByText('預估 48000 元')).not.toBeInTheDocument();
  expect(screen.queryByText('預估 2026-11-15')).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('訂單資訊－2'));
  expect(await screen.findByRole('heading', { name: '訂單資訊－2' })).toBeInTheDocument();
  expect(client.sendInformation).not.toHaveBeenCalled();
});

it('groups candidate information 2 into readable sections instead of one text block', async () => {
  vi.mocked(client.previewInformation).mockResolvedValue({
    case_no: 'CASE-1', candidate_id: 3, info_type: 2, staff_name: '測試月嫂', preview_fingerprint: '2'.repeat(64),
    text: ['訂單資訊－2', '初步接案意願詢問', '客戶名稱：江家綺', '聯絡電話：0988990301', '案件編號：M3-CUST-20260910-01', '服務地址：北大路22號', '飲食習慣(含是否可接受中藥)：葷食，可接受中藥調理', '可否接受蛋奶素餐食：可以', '餐飲含酒比例：半酒', '料理用油：苦茶油、麻油', '媽咪有無過敏體質：無已知過敏', '特殊照護注意事項：依客戶現場需求', '餐點喜忌：清淡少鹽', '現有烹煮工具：炒鍋、電鍋、微波爐', '洗澡水準備：一般溫水', '哺乳方式：母乳與配方奶混合', '胎數與特殊計費：單胎', '服務樓層方式：大樓電梯', '提供服務人員轎車停車位：可提供停車位', '服務時間內的其他寶寶：無'].join('\n'),
    line_sections: [
      { title: '飲食與照護需求', rows: [['飲食習慣', '葷食，可接受中藥調理'], ['餐點喜忌', '清淡少鹽']] },
      { title: '服務環境與費用約定', rows: [['現有烹煮工具', '炒鍋、電鍋、微波爐'], ['停車位', '可提供停車位']] },
    ],
  });

  render(<OrderInformationSheets caseNo="CASE-1" assignments={[]} initialKind={2} />);

  expect(await screen.findByRole('heading', { name: '飲食與照護需求' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: '服務環境與費用約定' })).toBeInTheDocument();
  expect(screen.getByText('葷食，可接受中藥調理')).toBeInTheDocument();
  expect(screen.getByText('炒鍋、電鍋、微波爐')).toBeInTheDocument();
  expect(screen.queryByText('江家綺')).not.toBeInTheDocument();
  expect(Array.from(document.querySelectorAll('.order-information-two-sections dt')).map((node) => node.textContent)).toEqual([
    '飲食習慣', '餐點喜忌', '現有烹煮工具', '停車位',
  ]);
  expect(document.querySelector('.order-information-paper pre')).not.toBeInTheDocument();
});

it('previews weekly service in the same earlier information step', async () => {
  render(<OrderInformationSheets caseNo="CASE-1" assignments={[]} />);
  await screen.findByText('契約重點截圖');

  fireEvent.click(screen.getByText('每週服務時間說明'));

  expect(await screen.findByRole('table')).toHaveTextContent('16 小時');
  expect(client.previewWeeklyService).toHaveBeenCalledWith('CASE-1', 3, expect.objectContaining({ signal: expect.any(AbortSignal) }));
});

it('shows missing order-information values as non-blocking warnings', async () => {
  vi.mocked(queryOrderInformation).mockResolvedValue({
    template_id: 'tpl_info_01', case_no: 'CASE-1', assignment_id: 7,
    fields: [{
      field_id: 'f_108_c8', label: '服務地址', owner: 'orders', source: null,
      requiredness: 'required', status: 'missing', value: null,
    }],
    owner_fingerprints: {}, blockers: [],
    warnings: ['order_information_required_field_missing:f_108_c8'],
    preview_fingerprint: 'a'.repeat(64), can_render: true,
  });

  render(<OrderInformationSheets caseNo="CASE-1" assignments={[{
    assignment_id: 7, sequence: 1, staff_id: 2,
    assigned_start_date: '2026-09-01', assigned_end_date: '2026-09-05',
  }] as never} />);

  expect(await screen.findByText('部分資料尚未提供，已在欄位中標示；不影響目前資料的預覽。')).toBeInTheDocument();
  expect(screen.getAllByText('待確認').length).toBeGreaterThan(0);
  expect(screen.queryByText('模板或資料投影發生技術錯誤，目前無法完成預覽。')).not.toBeInTheDocument();
});

it('shows the missing information 1 service-hour and cooking fields in the contract excerpt', async () => {
  vi.mocked(queryOrderInformation).mockResolvedValue({
    template_id: 'tpl_info_01', case_no: 'CASE-1', assignment_id: 7,
    fields: [
      { field_id: 'f_106_c6', label: '每日服務時數', owner: 'orders', source: 'order.service_hours_per_day', requiredness: 'required', status: 'resolved', value: 8 },
      { field_id: 'f_109_c9', label: '服務是否需要下廚', owner: 'orders', source: 'order.requires_cooking', requiredness: 'required', status: 'resolved', value: true },
    ],
    owner_fingerprints: {}, blockers: [], warnings: [], preview_fingerprint: 'b'.repeat(64), can_render: true,
  });

  render(<OrderInformationSheets caseNo="CASE-1" assignments={[{
    assignment_id: 7, sequence: 1, staff_id: 2,
    assigned_start_date: '2026-09-01', assigned_end_date: '2026-09-05',
  }] as never} />);

  expect(await screen.findByText('契約重點截圖')).toBeInTheDocument();
  expect(screen.getByText('每日服務時數')).toBeInTheDocument();
  expect(screen.getByText('8')).toBeInTheDocument();
  expect(screen.getByText('下廚需求')).toBeInTheDocument();
  expect(screen.getByText('需要下廚')).toBeInTheDocument();
});
