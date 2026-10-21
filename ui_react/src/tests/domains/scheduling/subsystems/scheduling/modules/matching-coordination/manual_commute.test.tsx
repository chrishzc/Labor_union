import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CaregiverCommuteQuery, CommuteHistoryPanel, CommuteUsagePanel } from '../../../../../../../components/CaregiverCommute';
import { transport } from '../../../../../../../api/shared/transport';
import { sessionClient } from '../../../../../../../api/auth/session_client';

const mocks = vi.hoisted(() => ({ usage: vi.fn(), query: vi.fn(), reconcile: vi.fn(), history: vi.fn() }));
vi.mock('../../../../../../../api/scheduling/commute_client', () => ({ commuteClient: mocks }));
const usage = { billing_month: '2026-10', configured: true, free_limit: 1000, local_requests: 312,
  free_used: 312, free_remaining: 688, uncertain_requests: 0, paid_requests: 0, estimated_cost_usd: '0.00',
  verified_count: null, verified_through: null, verified_at: null };
const result = { case_no: 'DEMO', staff_id: 7, event_key: 'test', status: 'ready', distance_meters: 8600,
  duration_seconds: 1320, queried_at: '2026-10-21T03:00:00Z', message: '' };
const history = { case_no: 'DEMO', records: [
  { record_id: 'recent', queried_at: '2026-10-21T04:00:00Z', staff_id: 8, staff_name: '月嫂乙', status: 'failed', message: '未取得可顯示的機車路線。' },
  { record_id: 'earlier', queried_at: '2026-10-21T03:00:00Z', staff_id: 7, staff_name: '月嫂甲', status: 'succeeded', message: '已取得機車路線。' },
  { record_id: 'unknown', queried_at: '2026-10-21T02:00:00Z', staff_id: 9, staff_name: null, status: 'unknown', message: '結果待確認，請勿立即重複查詢。' },
] };
let sessionToken = '';
beforeEach(() => {
  vi.restoreAllMocks();
  sessionToken = crypto.randomUUID();
  vi.spyOn(sessionClient, 'getToken').mockImplementation(() => sessionToken);
  Object.values(mocks).forEach(mock => mock.mockReset());
  mocks.usage.mockResolvedValue(usage); mocks.query.mockResolvedValue(result); mocks.history.mockResolvedValue(history);
});

it('retains the same case and person result across closing, switching cases and reopening without a request', async () => {
  const view = render(<><CommuteUsagePanel /><CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" /></>);
  await waitFor(() => expect(screen.getByRole('button', { name: '查詢機車通勤' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '查詢機車通勤' }));
  await screen.findByText(/8.6 公里 · 預估 22 分鐘/);
  view.rerender(<CaregiverCommuteQuery caseNo="OTHER" staffId={7} staffName="月嫂甲" />);
  expect(screen.queryByText(/8.6 公里/)).not.toBeInTheDocument();
  view.rerender(<CaregiverCommuteQuery caseNo="DEMO" staffId={8} staffName="月嫂乙" />);
  expect(screen.queryByText(/8.6 公里/)).not.toBeInTheDocument();
  view.rerender(<CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" />);
  expect(screen.getByText(/8.6 公里 · 預估 22 分鐘/)).toBeInTheDocument();
  view.unmount();
  render(<CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" />);
  expect(screen.getByText(/8.6 公里 · 預估 22 分鐘/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '重新查詢機車通勤（增加用量）' })).toBeInTheDocument();
  expect(mocks.query).toHaveBeenCalledTimes(1);
});

it('shares a pending request across cards and retains its result even when it completes after closing', async () => {
  let finish!: (value: typeof result) => void;
  mocks.query.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const view = render(<><CommuteUsagePanel /><CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" /><CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" /></>);
  await waitFor(() => expect(screen.getAllByRole('button', { name: '查詢機車通勤' })[0]).toBeEnabled());
  fireEvent.click(screen.getAllByRole('button', { name: '查詢機車通勤' })[0]);
  expect(screen.getAllByRole('button', { name: '查詢機車通勤中…' })).toHaveLength(2);
  view.unmount();
  const reopened = render(<CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" />);
  expect(screen.getByRole('button', { name: '查詢機車通勤中…' })).toBeDisabled();
  reopened.unmount();
  await act(async () => { finish(result); });
  render(<CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" />);
  expect(screen.getByText(/8.6 公里 · 預估 22 分鐘/)).toBeInTheDocument();
  expect(mocks.query).toHaveBeenCalledTimes(1);
});

it('clears retained results on a login change and discards an earlier session response', async () => {
  const view = render(<><CommuteUsagePanel /><CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" /></>);
  await waitFor(() => expect(screen.getByRole('button', { name: '查詢機車通勤' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '查詢機車通勤' }));
  await screen.findByText(/8.6 公里/);
  sessionToken = 'second-test-session';
  view.rerender(<CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" />);
  expect(screen.queryByText(/8.6 公里/)).not.toBeInTheDocument();
  let finish!: (value: typeof result) => void;
  mocks.query.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  fireEvent.click(screen.getByRole('button', { name: '查詢機車通勤' }));
  sessionToken = 'third-test-session';
  view.rerender(<CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" />);
  await act(async () => { finish(result); });
  expect(screen.queryByText(/8.6 公里/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '查詢機車通勤' })).toBeEnabled();
  expect(mocks.query).toHaveBeenCalledTimes(2);
});

it('reads saved case history on reopening without calling routes or changing usage', async () => {
  const view = render(<CommuteHistoryPanel caseNo="DEMO" />);
  await screen.findByText('月嫂乙');
  expect(screen.getByText('成功')).toBeInTheDocument();
  expect(screen.getByText('失敗')).toBeInTheDocument();
  expect(screen.getByText('待確認')).toBeInTheDocument();
  expect(screen.getByText(/月嫂編號 9/)).toBeInTheDocument();
  expect(screen.getByText('月嫂乙').closest('tr')?.querySelector('time')).toHaveAttribute('dateTime', '2026-10-21T04:00:00Z');
  expect(screen.queryByText(/8.6 公里/)).not.toBeInTheDocument();
  view.unmount();
  render(<CommuteHistoryPanel caseNo="DEMO" />);
  await screen.findByText('月嫂乙');
  expect(mocks.history).toHaveBeenCalledTimes(2);
  expect(mocks.history.mock.calls[0][0]).toBe('DEMO');
  expect(mocks.query).not.toHaveBeenCalled();
  expect(mocks.usage).not.toHaveBeenCalled();
});

it('refreshes saved history after one manual route query', async () => {
  mocks.history.mockResolvedValueOnce({ case_no: 'DEMO', records: [] });
  render(<><CommuteUsagePanel /><CommuteHistoryPanel caseNo="DEMO" /><CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" /></>);
  await screen.findByText('本案尚無機車通勤查詢紀錄。');
  await waitFor(() => expect(screen.getByRole('button', { name: '查詢機車通勤' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '查詢機車通勤' }));
  await screen.findByText('月嫂乙');
  expect(mocks.query).toHaveBeenCalledTimes(1);
  expect(mocks.history).toHaveBeenCalledTimes(2);
});

it('makes history failures visible and retries only reading records', async () => {
  mocks.history.mockRejectedValueOnce(new Error('unavailable'));
  render(<CommuteHistoryPanel caseNo="DEMO" />);
  await screen.findByRole('alert');
  expect(screen.queryByText('本案尚無機車通勤查詢紀錄。')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '重新讀取紀錄' }));
  await screen.findByText('月嫂乙');
  expect(mocks.query).not.toHaveBeenCalled();
});

it('does not show a late history response for another case', async () => {
  let finish!: (value: typeof history) => void;
  mocks.history.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockResolvedValueOnce({ case_no: 'OTHER', records: [] });
  const view = render(<CommuteHistoryPanel caseNo="DEMO" />);
  view.rerender(<CommuteHistoryPanel caseNo="OTHER" />);
  await screen.findByText('本案尚無機車通勤查詢紀錄。');
  finish(history);
  await waitFor(() => expect(screen.queryByText('月嫂乙')).not.toBeInTheDocument());
});

it('strictly decodes metadata and rejects another case or stored route content', async () => {
  const actual = await vi.importActual<typeof import('../../../../../../../api/scheduling/commute_client')>('../../../../../../../api/scheduling/commute_client');
  const get = vi.spyOn(transport, 'get').mockResolvedValue({ success: true, data: { case_no: 'DEMO/TEST', records: [] } });
  const signal = new AbortController().signal;
  await expect(actual.commuteClient.history('DEMO/TEST', signal)).resolves.toEqual({ case_no: 'DEMO/TEST', records: [] });
  expect(get).toHaveBeenCalledWith('/api/v1/orders/DEMO%2FTEST/commute-history', expect.objectContaining({ cache: 'no-store', signal }));
  get.mockResolvedValue({ success: true, data: history });
  await expect(actual.commuteClient.history('OTHER')).rejects.toThrow('與目前案件不一致');
  get.mockResolvedValue({ success: true, data: { ...history, records: [{ ...history.records[0], distance_meters: 8600 }] } });
  await expect(actual.commuteClient.history('DEMO')).rejects.toThrow();
});

it('only queries the manually selected person and never queries routes on mount or refresh', async () => {
  render(<><CommuteUsagePanel /><CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" /><CaregiverCommuteQuery caseNo="DEMO" staffId={8} staffName="月嫂乙" /></>);
  await screen.findByText(/312 \/ 1,000/);
  expect(mocks.query).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '重新讀取用量' }));
  expect(mocks.query).not.toHaveBeenCalled();
  const first = screen.getAllByRole('button', { name: '查詢機車通勤' })[0];
  fireEvent.click(first); fireEvent.click(first);
  await screen.findByText(/8.6 公里 · 預估 22 分鐘/);
  expect(mocks.query).toHaveBeenCalledTimes(1);
  expect(mocks.query.mock.calls[0].slice(0, 2)).toEqual(['DEMO', 7]);
  expect(screen.queryByRole('button', { name: /整批|全部/ })).not.toBeInTheDocument();
});

it('disables route calls when not configured and keeps a readable setup notice', async () => {
  mocks.usage.mockResolvedValue({ ...usage, configured: false });
  render(<><CommuteUsagePanel /><CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" /></>);
  await screen.findByText(/尚未設定 Google Routes API/);
  expect(screen.getByRole('button', { name: '查詢機車通勤' })).toBeDisabled();
  expect(mocks.query).not.toHaveBeenCalled();
});

it('displays a zero route with the address verification warning after a manual query', async () => {
  const message = 'Google 返回零距離，請核對起訖地址是否完整，或是否定位到同一地點。';
  mocks.query.mockResolvedValue({ ...result, distance_meters: 0, duration_seconds: 0, message });
  render(<><CommuteUsagePanel /><CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" /></>);
  await waitFor(() => expect(screen.getByRole('button', { name: '查詢機車通勤' })).toBeEnabled());
  expect(mocks.query).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '查詢機車通勤' }));
  await screen.findByText(/0.0 公里 · 預估 0 分鐘/);
  expect(screen.getByText(message)).toBeInTheDocument();
  expect(mocks.query).toHaveBeenCalledTimes(1);
});

it('reuses the operation identity after an unknown network result without automatic retry', async () => {
  mocks.query.mockRejectedValueOnce(new Error('連線中斷')).mockResolvedValueOnce({ ...result, status: 'already_requested', distance_meters: null, message: '已受理，不重複查詢' });
  const view = render(<><CommuteUsagePanel /><CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" /></>);
  await waitFor(() => expect(screen.getByRole('button', { name: '查詢機車通勤' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '查詢機車通勤' }));
  await screen.findByRole('button', { name: '確認原查詢操作' });
  view.unmount();
  render(<CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" />);
  const confirm = screen.getByRole('button', { name: '確認原查詢操作' });
  expect(mocks.query).toHaveBeenCalledTimes(1);
  fireEvent.click(confirm);
  await screen.findByText('已受理，不重複查詢');
  expect(mocks.query.mock.calls[0][2]).toBe(mocks.query.mock.calls[1][2]);
});

it('drops an old person response when the selected person changes', async () => {
  let finish!: (value: typeof result) => void;
  mocks.query.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const view = render(<><CommuteUsagePanel /><CaregiverCommuteQuery caseNo="DEMO" staffId={7} staffName="月嫂甲" /></>);
  await waitFor(() => expect(screen.getByRole('button', { name: '查詢機車通勤' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '查詢機車通勤' }));
  view.rerender(<><CommuteUsagePanel /><CaregiverCommuteQuery caseNo="OTHER" staffId={8} staffName="月嫂乙" /></>);
  finish(result);
  await waitFor(() => expect(screen.queryByText(/8.6 公里/)).not.toBeInTheDocument());
  expect(mocks.query).toHaveBeenCalledTimes(1);
});

it('records whole-account billing counts with the explicit Taiwan report cutoff', async () => {
  mocks.reconcile.mockResolvedValue({ ...usage, verified_count: 312, verified_through: '2026-10-21T02:00:00Z', verified_at: '2026-10-21T03:00:00Z' });
  render(<CommuteUsagePanel />);
  await screen.findByText(/312 \/ 1,000/);
  fireEvent.click(screen.getByText('用量明細與帳務核對'));
  fireEvent.change(screen.getByLabelText('Google 本月累計用量（次）'), { target: { value: '312' } });
  fireEvent.change(screen.getByLabelText('報表統計截止時間（台灣時間）'), { target: { value: '2026-10-21T10:00' } });
  fireEvent.click(screen.getByRole('button', { name: '保存核對用量' }));
  await screen.findByText('已登錄人工核對用量。');
  expect(mocks.reconcile).toHaveBeenCalledWith('2026-10', 312, '2026-10-21T02:00:00.000Z');
});
