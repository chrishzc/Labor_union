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
  await screen.findByText(`資訊${kind}：契約與服務約定`);
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
    text: ['訂單資訊－2', '初步接案意願詢問', '客戶名稱：江家綺', '聯絡電話：0988990301', '案件編號：M3-CUST-20260910-01', '服務地址：北大路22號', '飲食習慣(含是否可接受中藥)：葷食，可接受中藥調理', '可否接受蛋奶素餐食：可以', '餐飲含酒比例：半酒', '料理用油：苦茶油、麻油', '媽咪有無過敏體質：無已知過敏', '特殊照護注意事項：依客戶現場需求', '餐點喜忌：清淡少鹽', '現有烹煮工具：炒鍋、電鍋、微波爐', '洗澡水準備：一般溫水', '哺乳方式：母乳與配方奶混合', '三節計費約定：已確認', '胎數與特殊計費：單胎', '服務樓層方式：大樓電梯', '提供服務人員轎車停車位：可提供停車位', '服務時間內的其他寶寶：無'].join('\n'),
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
