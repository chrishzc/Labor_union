import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { OrderCandidateContactStatusPanel } from '../../../../../../../components/OrderCandidateContactStatusPanel';
import { OrderInformationSheets } from '../../../../../../../components/OrderInformationSheets';
import { candidateContactPoolClient as client } from '../../../../../../../api/scheduling/candidate_contact_pool_client';
import { queryOrderInformation } from '../../../../../../../api/orders/order_information_client';

const { createInformationCommand } = vi.hoisted(() => ({ createInformationCommand: vi.fn() }));
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({
  createCandidateInformationSendCommand: createInformationCommand,
  candidateContactPoolClient: { query: vi.fn(), previewInformation: vi.fn(), previewWeeklyService: vi.fn(), sendInformation: vi.fn() },
}));
vi.mock('../../../../../../../api/orders/order_information_client', () => ({
  queryOrderInformation: vi.fn(),
}));
beforeEach(() => {
  vi.resetAllMocks();
  let sentKind: 1 | 2 | null = null;
  vi.mocked(client.query).mockImplementation(async () => ({ case_no: 'CASE-1', pool_id: 1, candidates: [{
    id: 3, staff_id: 2, staff_name: '測試月嫂', status: 'active', willingness: 'pending', reason: null,
    latest_willingness_event_id: null,
    information: {
      '1': sentKind === 1 ? { status: 'queued', sent_at: '2026-10-01T00:00:00Z', event_id: 4, line_task_id: 5 } : null,
      '2': sentKind === 2 ? { status: 'queued', sent_at: '2026-10-01T00:00:00Z', event_id: 4, line_task_id: 5 } : null,
    }, service_start_date: '2026-10-01', service_end_date: '2026-10-02', created_at: '2026-09-01T00:00:00Z',
  }] } as never));
  createInformationCommand.mockImplementation((caseNo, candidateId, infoType, previewFingerprint) => ({
    caseNo, candidateId, infoType, previewFingerprint, actor: 'operator-1', eventKey: `information-${infoType}-key`,
  }));
  vi.mocked(client.previewInformation).mockImplementation(async (caseNo, candidateId, kind) => ({ case_no: caseNo, candidate_id: candidateId, info_type: kind, staff_name: '測試月嫂', text: `資訊${kind}：服務報酬待確認`, preview_fingerprint: String(kind).repeat(64) }));
  vi.mocked(client.previewWeeklyService).mockResolvedValue({ case_no: 'CASE-1', candidate_id: 3, rows: [{
    serial_number: 1, staff_name: '測試月嫂', week_start_date: '2026-09-28', week_end_date: '2026-10-04',
    service_hours_per_day: 8, weekly_work_days: 2, weekly_hours: 16,
  }] });
  vi.mocked(client.sendInformation).mockImplementation(async (command) => {
    sentKind = command.infoType;
    return { status: 'queued', event_id: 4, line_task_id: 5 };
  });
});

it.each([1, 2] as const)('previews information %i independently and sends exactly that preview', async (kind) => {
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" />);
  fireEvent.click(await screen.findByRole('button', { name: `寄送訂單資訊－${kind}` }));
  await screen.findByText(`資訊${kind}：服務報酬待確認`);
  expect(client.sendInformation).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('確認寄送'));
  await waitFor(() => expect(client.sendInformation).toHaveBeenCalledWith({
    caseNo: 'CASE-1', candidateId: 3, infoType: kind, previewFingerprint: String(kind).repeat(64),
    actor: 'operator-1', eventKey: `information-${kind}-key`,
  }));
  expect(client.sendInformation).toHaveBeenCalledTimes(1);
});

it('previews a candidate without creating or requiring an assignment', async () => {
  render(<OrderInformationSheets caseNo="CASE-1" assignments={[]} />);
  expect(await screen.findByText('資訊1：服務報酬待確認')).toBeInTheDocument();
  fireEvent.click(screen.getByText('訂單資訊－2'));
  expect(await screen.findByText('資訊2：服務報酬待確認')).toBeInTheDocument();
  expect(client.sendInformation).not.toHaveBeenCalled();
});

it('previews weekly service in the same earlier information step', async () => {
  render(<OrderInformationSheets caseNo="CASE-1" assignments={[]} />);
  await screen.findByText('資訊1：服務報酬待確認');

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
