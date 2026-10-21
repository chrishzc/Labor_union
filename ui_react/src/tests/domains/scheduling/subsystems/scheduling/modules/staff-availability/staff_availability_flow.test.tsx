/** Verify automatic full-history records and on-demand pause commands. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffAvailabilityClient } from '../../../../../../../api/staff_availability/staff_availability_client';
import { staffDirectoryClient } from '../../../../../../../api/staff_directory/staff_directory_client';
import { staffQualificationMasterClient } from '../../../../../../../api/staff/qualification_master_client';
import { staffLifecycleClient } from '../../../../../../../api/staff_lifecycle/staff_lifecycle_client';
import { StaffAvailabilityConflictError, StaffAvailabilityUnavailableError } from '../../../../../../../api/staff_availability/staff_availability_errors';
import type { StaffAvailabilityPreview, StaffUnavailabilityBlock } from '../../../../../../../api/staff_availability/staff_availability_schemas';
import { StaffPage } from '../../../../../../../pages/StaffPage';
import { STAFF_AVAILABILITY_BLOCK, STAFF_AVAILABILITY_SELECTED_PAUSE_BLOCK, STAFF_AVAILABILITY_CLOSED_PAUSE_BLOCK, STAFF_AVAILABILITY_END_PAUSE_PREVIEW_RESPONSE, STAFF_AVAILABILITY_END_PAUSE_RECEIPT_RESPONSE, STAFF_AVAILABILITY_PREVIEW_RESPONSE, STAFF_AVAILABILITY_RECEIPT_RESPONSE } from '../../../../../../fixtures/staff/staff_availability_contract_fixtures';
import { STAFF_PAGE_ONE } from '../../../../../../fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_LIFECYCLE_VIEW } from '../../../../../../fixtures/staff/staff_lifecycle_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from '../../../../../../fixtures/staff/staff_qualification_contract_fixtures';
import { staffQualificationEditingClient } from '../../../../../../../api/staff/qualification_editing_client';

const finite: StaffUnavailabilityBlock = { ...STAFF_AVAILABILITY_BLOCK, staff_id: 11, start_date: '2026-10-01', end_date: '2026-10-31' };
const pause = STAFF_AVAILABILITY_SELECTED_PAUSE_BLOCK;
const area = () => within(screen.getByRole('region', { name: '接案狀態管理' }));
async function open() {
  render(<StaffPage />);
  fireEvent.click(await screen.findByRole('button', { name: '查看 去敏人員甲 的詳情' }));
  await waitFor(() => expect(staffAvailabilityClient.getAllBlocks).toHaveBeenCalled());
}
async function add(unlimited = false) {
  fireEvent.click(area().getByRole('button', { name: '新增' }));
  if (unlimited) fireEvent.change(area().getByLabelText('新增類型'), { target: { value: 'create_pause' } });
  fireEvent.change(area().getByLabelText('開始日期'), { target: { value: '2026-10-01' } });
  if (!unlimited) fireEvent.change(area().getByLabelText('結束日期'), { target: { value: '2026-10-31' } });
}
function mutation(action: StaffAvailabilityPreview['action'], result: StaffUnavailabilityBlock, target: StaffUnavailabilityBlock | null = null) {
  vi.mocked(staffAvailabilityClient.previewChange).mockResolvedValue({ ...STAFF_AVAILABILITY_PREVIEW_RESPONSE.data!, staff_id: 11, action, target_block: target });
  vi.mocked(staffAvailabilityClient.applyChange).mockResolvedValue({ ...STAFF_AVAILABILITY_RECEIPT_RESPONSE.data!, staff_id: 11, action, block: result });
  vi.mocked(staffAvailabilityClient.getAllBlocks).mockResolvedValue([result]);
}

describe('Staff availability flow', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-22T04:00:00Z'));
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ ...STAFF_PAGE_ONE, next_cursor: null });
    vi.spyOn(staffDirectoryClient, 'resetPagination').mockImplementation(() => undefined);
    vi.spyOn(staffLifecycleClient, 'query').mockResolvedValue(STAFF_LIFECYCLE_VIEW);
    vi.spyOn(staffQualificationMasterClient, 'query').mockResolvedValue(STAFF_QUALIFICATION_MASTER);
    const facts = { special_skills: [], certifications: [], transportation: [], has_massage_cert: null, care_babies: 1 };
    vi.spyOn(staffQualificationEditingClient, 'query').mockResolvedValue({ staff_id: 11, before: facts, after: facts, snapshot_fingerprint: 'a'.repeat(64), preview_fingerprint: null });
    vi.spyOn(staffAvailabilityClient, 'getAllBlocks').mockResolvedValue([finite]);
    vi.spyOn(staffAvailabilityClient, 'previewChange').mockResolvedValue({ ...STAFF_AVAILABILITY_PREVIEW_RESPONSE.data!, staff_id: 11 });
    vi.spyOn(staffAvailabilityClient, 'applyChange').mockResolvedValue({ ...STAFF_AVAILABILITY_RECEIPT_RESPONSE.data!, staff_id: 11 });
  });
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

  it('auto-loads records, shows 無 for empty data and hides settings until 新增', async () => {
    vi.mocked(staffAvailabilityClient.getAllBlocks).mockResolvedValue([]);
    await open();
    expect(await area().findByText('無')).toBeVisible();
    expect(area().queryByLabelText('開始日期')).not.toBeInTheDocument();
    expect(area().queryByRole('button', { name: '查詢不可服務期間' })).not.toBeInTheDocument();
    expect(area().queryByText(/可供派工|可接案/)).not.toBeInTheDocument();
    fireEvent.click(area().getByRole('button', { name: '新增' }));
    const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Taipei' }).format(new Date());
    expect(area().getByLabelText('開始日期')).toHaveValue(today);
    expect(area().getByLabelText('新增類型')).toHaveDisplayValue('暫停接案');
    expect(area().getByLabelText('結束日期')).toBeVisible();
    expect(area().queryByRole('option', { name: '無指定日期' })).not.toBeInTheDocument();
    fireEvent.click(area().getByRole('button', { name: '取消新增' }));
    expect(area().queryByLabelText('開始日期')).not.toBeInTheDocument();
  });
  it('shows selected staff separately and includes both historical and future records', async () => {
    vi.mocked(staffAvailabilityClient.getAllBlocks).mockResolvedValue([{ ...finite, start_date: '2020-01-01', end_date: '2020-01-31' }, { ...finite, block_id: 100, start_date: '2030-01-01', end_date: '2030-01-31' }]);
    await open();
    fireEvent.click(await area().findByText('歷史與已取消紀錄（1）'));
    expect(area().getByText('2020-01-01 ～ 2020-01-31')).toBeVisible();
    expect(area().getByText('2030-01-01 ～ 2030-01-31')).toBeVisible();
    expect(area().getByText('A001 去敏人員甲')).toBeVisible();
    expect(area().queryByRole('columnheader', { name: '月嫂姓名' })).not.toBeInTheDocument();
  });
  it.each([false, true])('saves finite/unlimited pause (%s) once, then reloads records and hides the form', async unlimited => {
    await open();
    await add(unlimited);
    const action = unlimited ? 'create_pause' : 'create_long_leave';
    const result = unlimited ? pause : { ...finite, start_date: '2026-10-01', end_date: '2026-10-31' };
    mutation(action, result);
    fireEvent.change(area().getByLabelText('新增暫停備註（選填）'), { target: { value: '測試暫停' } });
    expect(staffAvailabilityClient.getAllBlocks).toHaveBeenCalledTimes(1);
    if (unlimited) expect(area().queryByLabelText('結束日期')).not.toBeInTheDocument();
    fireEvent.click(area().getByRole('button', { name: '儲存新增' }));
    await area().findByRole('status', { name: '不可服務期間變更結果' });
    expect(staffAvailabilityClient.previewChange).toHaveBeenCalledWith(11, { action, start_date: '2026-10-01', reason: '測試暫停', ...(unlimited ? {} : { end_date: '2026-10-31' }) }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(staffAvailabilityClient.applyChange).toHaveBeenCalledOnce();
    expect(staffAvailabilityClient.getAllBlocks).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(area().queryByLabelText('開始日期')).not.toBeInTheDocument());
  });
  it('shows cancelled history without actions or a false paused summary', async () => {
    vi.mocked(staffAvailabilityClient.getAllBlocks).mockResolvedValue([{ ...pause, status: 'cancelled' }]);
    await open();
    expect(await area().findByRole('status', { name: '目前暫停接案狀態' })).toHaveTextContent('目前：未暫停接案');
    const history = area().getByText('歷史與已取消紀錄（1）').closest('details')!;
    expect(history).not.toHaveAttribute('open');
    fireEvent.click(area().getByText('歷史與已取消紀錄（1）'));
    expect(area().getByText('已取消，不影響接案')).toBeVisible();
    expect(area().queryByRole('button', { name: '取消此期間' })).not.toBeInTheDocument();
    expect(area().queryByRole('button', { name: '恢復接案' })).not.toBeInTheDocument();
  });
  it('retries failed automatic reads without showing a false empty result', async () => {
    vi.mocked(staffAvailabilityClient.getAllBlocks).mockRejectedValueOnce(new Error('讀取暫時失敗'));
    await open();
    fireEvent.click(await area().findByRole('button', { name: '重試不可服務期間' }));
    expect(await area().findByText('2026-10-01 ～ 2026-10-31')).toBeVisible();
    expect(staffAvailabilityClient.getAllBlocks).toHaveBeenCalledTimes(2);
  });
  it('cancels the chosen record through the existing writer and observes the result', async () => {
    await open();
    mutation('cancel', { ...finite, status: 'cancelled' }, finite);
    fireEvent.click(await area().findByRole('button', { name: '取消此期間' }));
    await waitFor(() => expect(staffAvailabilityClient.applyChange).toHaveBeenCalledOnce());
    expect(staffAvailabilityClient.previewChange).toHaveBeenCalledWith(11, { action: 'cancel', block_id: finite.block_id, reason: '' }, expect.anything());
    expect(await area().findByRole('status', { name: '目前暫停接案狀態' })).toHaveTextContent('目前：未暫停接案');
    fireEvent.click(area().getByText('歷史與已取消紀錄（1）'));
    expect(area().getByText('已取消，不影響接案')).toBeVisible();
  });
  it('expands restore only for the chosen open pause and confirms the canonical closed interval', async () => {
    vi.mocked(staffAvailabilityClient.getAllBlocks).mockResolvedValue([pause]);
    await open();
    expect(area().queryByLabelText('恢復接案日期')).not.toBeInTheDocument();
    fireEvent.click(await area().findByRole('button', { name: '恢復接案' }));
    fireEvent.change(area().getByLabelText('恢復接案日期'), { target: { value: '2026-10-15' } });
    vi.mocked(staffAvailabilityClient.previewChange).mockResolvedValue(STAFF_AVAILABILITY_END_PAUSE_PREVIEW_RESPONSE.data!);
    vi.mocked(staffAvailabilityClient.applyChange).mockResolvedValue(STAFF_AVAILABILITY_END_PAUSE_RECEIPT_RESPONSE.data!);
    vi.mocked(staffAvailabilityClient.getAllBlocks).mockResolvedValue([STAFF_AVAILABILITY_CLOSED_PAUSE_BLOCK]);
    fireEvent.click(area().getByRole('button', { name: '儲存恢復接案' }));
    await area().findByRole('status', { name: '不可服務期間變更結果' });
    expect(staffAvailabilityClient.previewChange).toHaveBeenCalledWith(11, { action: 'end_pause', block_id: pause.block_id, resume_date: '2026-10-15', reason: '' }, expect.anything());
    expect(await area().findByRole('status', { name: '目前暫停接案狀態' })).toHaveTextContent('目前：未暫停接案');
    fireEvent.click(area().getByText('歷史與已取消紀錄（1）'));
    expect(area().getByText('2026-10-01 ～ 2026-10-14')).toBeVisible();
    await waitFor(() => expect(area().queryByLabelText('恢復接案日期')).not.toBeInTheDocument());
  });
  it.each([
    ['long_leave', '2026-10-22', '2026-10-22', '暫停接案中'],
    ['paused_service', '2026-10-22', null, '暫停接案中'],
    ['long_leave', '2026-10-23', '2026-10-31', '未暫停接案'],
    ['long_leave', '2026-10-01', '2026-10-21', '未暫停接案'],
  ] as const)('classifies %s %s–%s against Taipei today', async (kind, start_date, end_date, label) => {
    vi.mocked(staffAvailabilityClient.getAllBlocks).mockResolvedValue([{ ...finite, kind, start_date, end_date }]);
    await open();
    expect(await area().findByRole('status', { name: '目前暫停接案狀態' })).toHaveTextContent(`目前：${label}`);
  });
  it('does not show a clear status while loading or when the record query fails', async () => {
    vi.mocked(staffAvailabilityClient.getAllBlocks).mockRejectedValue(new Error('讀取失敗'));
    await open();
    await area().findByRole('alert');
    expect(area().queryByRole('status', { name: '目前暫停接案狀態' })).not.toBeInTheDocument();
  });
  it('rejects an end-pause preview for a different staff or missing target', async () => {
    vi.mocked(staffAvailabilityClient.getAllBlocks).mockResolvedValue([pause]);
    await open();
    fireEvent.click(await area().findByRole('button', { name: '恢復接案' }));
    vi.mocked(staffAvailabilityClient.previewChange).mockResolvedValue({ ...STAFF_AVAILABILITY_END_PAUSE_PREVIEW_RESPONSE.data!, target_block: null });
    fireEvent.click(area().getByRole('button', { name: '儲存恢復接案' }));
    expect(await area().findByText('預覽結果中沒有同一筆可結束的暫停接案期間。')).toBeVisible();
    expect(staffAvailabilityClient.applyChange).not.toHaveBeenCalled();
  });
  it('does not apply a blocked preview', async () => {
    await open(); await add();
    vi.mocked(staffAvailabilityClient.previewChange).mockResolvedValue({ ...STAFF_AVAILABILITY_PREVIEW_RESPONSE.data!, can_apply: false, blockers: ['staff_unavailability_overlap'] });
    fireEvent.click(area().getByRole('button', { name: '儲存新增' }));
    expect(await area().findByText(/staff_unavailability_overlap/)).toBeVisible();
    expect(staffAvailabilityClient.applyChange).not.toHaveBeenCalled();
  });
  it('keeps typed stale conflicts and requires a fresh record read', async () => {
    await open(); await add();
    vi.mocked(staffAvailabilityClient.previewChange).mockRejectedValue(new StaffAvailabilityConflictError({ code: 'staff_availability_stale', message: '資料版本已更新' }));
    fireEvent.click(area().getByRole('button', { name: '儲存新增' }));
    fireEvent.click(await area().findByRole('button', { name: '重新載入紀錄' }));
    await waitFor(() => expect(staffAvailabilityClient.getAllBlocks).toHaveBeenCalledTimes(2));
    expect(staffAvailabilityClient.applyChange).not.toHaveBeenCalled();
  });
  it('retries an uncertain Apply with the same payload and idempotency key', async () => {
    await open(); await add();
    mutation('create_long_leave', finite);
    vi.mocked(staffAvailabilityClient.applyChange).mockRejectedValueOnce(new StaffAvailabilityUnavailableError({ code: 'staff_availability_unavailable', message: '結果未確認' }));
    fireEvent.click(area().getByRole('button', { name: '儲存新增' }));
    fireEvent.click(await area().findByRole('button', { name: '以相同內容重試' }));
    await waitFor(() => expect(staffAvailabilityClient.applyChange).toHaveBeenCalledTimes(2));
    const calls = vi.mocked(staffAvailabilityClient.applyChange).mock.calls;
    expect(calls[1]).toEqual(calls[0]);
  });
});
