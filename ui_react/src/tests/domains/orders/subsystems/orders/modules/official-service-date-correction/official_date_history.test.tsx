import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { OrderWorkbenchV2OwnerContext } from '../../../../../../../components/OrderWorkbenchV2OwnerContext';

const mocks = vi.hoisted(() => ({ query: vi.fn() }));
vi.mock('../../../../../../../api/orders/official_service_date_correction_client', () => ({ officialServiceDateCorrectionClient: mocks }));
vi.mock('../../../../../../../api/orders/order_card_projection_client', () => ({ orderCardProjectionClient: { getCardProjection: async () => ({}) } }));
vi.mock('../../../../../../../adapters/orders/order_card_projection_adapter', () => ({ adaptOrdersCardProjection: () => ({ rows: [] }) }));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getFormManagementContext: async (caseNo: string) => ({ case_no: caseNo, service_time: '09:00–17:00' }) } }));
vi.mock('../../../../../../../api/line/notification_timeline_client', () => ({ lineNotificationTimelineClient: { query: async () => ({ records: [] }) } }));

const reason = '將誤登的 2026-08-21 更正為 2026-08-22；保留原完工紀錄與既有帳務。';
const history = [
  { event_id: 45, event_type: 'original_completion', recorded_at: '2026-10-15T09:47:23Z', actor: 'fixture', before_dates: [], after_dates: ['2026-08-01', '2026-08-02', '2026-08-03'], reason: null, completion_instant: '2026-08-03T17:00:00+08:00' },
  { event_id: 48, event_type: 'service_date_corrected', recorded_at: '2026-10-15T11:32:23Z', actor: 'admin', before_dates: ['2026-08-01', '2026-08-02', '2026-08-21'], after_dates: ['2026-08-01', '2026-08-02', '2026-08-22'], reason, completion_instant: null },
];

beforeEach(() => { mocks.query.mockReset().mockResolvedValue({ case_no: 'CASE-A', history }); });

it('shows original completion and exact correction reason inside the existing service data section on demand', async () => {
  const view = render(<OrderWorkbenchV2OwnerContext caseNo="CASE-A" placement="header" completedService />);
  expect(mocks.query).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '查看相關資料與通知紀錄' }));
  const service = screen.getByRole('region', { name: '正式客戶服務資料' });
  await within(service).findByText('原完工紀錄 #45');
  expect(within(service).getByText('日期更正紀錄 #48')).toBeInTheDocument();
  expect(service).toHaveTextContent('原服務日期：2026-08-01 ～ 2026-08-03（3 天）');
  expect(service).toHaveTextContent('原服務完成時刻：2026/8/3 17:00:00');
  expect(service).toHaveTextContent('記錄時間：2026/10/15 17:47:23');
  expect(service).toHaveTextContent('移除日期：2026-08-21；補入日期：2026-08-22');
  expect(service).toHaveTextContent(`更正原因：${reason}`);
  expect(view.container.querySelectorAll('.order-case-related-records > section')).toHaveLength(3);
  expect(mocks.query).toHaveBeenCalledWith('CASE-A', { signal: expect.any(AbortSignal) });
});

it('keeps read failures explicit and retries through the existing toggle', async () => {
  mocks.query.mockRejectedValueOnce(new Error('暫時無法讀取紀錄'));
  render(<OrderWorkbenchV2OwnerContext caseNo="CASE-A" placement="header" completedService />);
  fireEvent.click(screen.getByRole('button', { name: '查看相關資料與通知紀錄' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('請收起後重新開啟此入口重試');
  fireEvent.click(screen.getByRole('button', { name: '收起相關資料與通知紀錄' }));
  fireEvent.click(screen.getByRole('button', { name: '查看相關資料與通知紀錄' }));
  await screen.findByText('日期更正紀錄 #48');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('does not show a previous case history after switching cases or query unfinished cases', async () => {
  let resolve!: (value: unknown) => void;
  mocks.query.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  const view = render(<OrderWorkbenchV2OwnerContext caseNo="CASE-A" placement="header" completedService />);
  fireEvent.click(screen.getByRole('button', { name: '查看相關資料與通知紀錄' }));
  await waitFor(() => expect(mocks.query).toHaveBeenCalledOnce());
  view.rerender(<OrderWorkbenchV2OwnerContext caseNo="CASE-B" placement="header" />);
  await act(async () => { resolve({ case_no: 'CASE-A', history }); });
  expect(screen.queryByText('原完工紀錄 #45')).not.toBeInTheDocument();
  expect(mocks.query).toHaveBeenCalledOnce();
});
