import { transport } from '../../../../../../../api/shared/transport';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { orderIntakeCompletionClient } from '../../../../../../../api/orders/order_intake_completion_client';
import { OrdersIntakeRepairCard } from '../../../../../../../components/OrdersIntakeRepairCard';
import { OrderIntakeRepairPanel } from '../../../../../../../components/OrderIntakeRepairPanel';
import { hcmResubmissionClient } from '../../../../../../../api/case_import/hcm_resubmission_client';
import { clientRegistryClient } from '../../../../../../../api/client_registry/client_registry_client';
import type { ClientRegistryDetail } from '../../../../../../../api/client_registry/client_registry_schemas';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';

const ETAG = 'a'.repeat(64);
const FP1 = '1'.repeat(64);
const FP2 = '2'.repeat(64);

const profileDetail: ClientRegistryDetail = {
  case_no: 'CASE-153',
  client: { client_id: 1, version: 2,
    values: { name: '測試客戶', gender: null, phone: null, city: null, address: null,
      residence_type: null, delivery_type: null, baby_info: null, notes: null, service_type: '無休' },
    field_capabilities: {
      phone: { owner: 'client_profile', editable: true, reason: null, options: null },
      service_type: { owner: 'client_profile', editable: true, reason: null, options: null },
    },
  },
  beclass: { status: 'unbound', record_id: null, source_kind: null, version: null, values: null, field_capabilities: {} },
  order_information: { status: 'unbound', values: null, field_issues: {} },
  finance: { status: 'not_ready', code: 'client_finance_bootstrap_required', values: null },
  order_terms: { status: 'not_ready', code: 'order_terms_incomplete', data: null, field_capabilities: {} },
};

const incompleteSummary = {
  case_no: 'CASE-153',
  client_name: '待補姓名（CASE-153）',
  order_status: '待補件',
  staff_name: null,
  identity_status: null,
  start_date: null,
  end_date: null,
  actual_start_date: null,
  actual_end_date: null,
  service_days: null,
  total_employer_self_pay_payable: null,
};

const completeSummary = {
  case_no: 'CASE-OK',
  client_name: '完整客戶',
  order_status: '洽談中',
  staff_name: null,
  identity_status: '一般',
  start_date: '2026-09-10',
  end_date: '2026-10-09',
  actual_start_date: null,
  actual_end_date: null,
  service_days: 30,
  total_employer_self_pay_payable: 100000,
};

describe('Orders intake repair entry', () => {
  beforeEach(() => {
    vi.spyOn(hcmResubmissionClient, 'current').mockResolvedValue({ items: [], next_cursor: null });
    vi.spyOn(clientRegistryClient, 'query').mockResolvedValue(profileDetail);
  });

  it.each([false, true])('名冊補齊時間後用新版本完成進件；回讀失敗時保留收據及離開限制（回讀失敗=%s）', async (failReadback) => {
    const caseNo = `REG-REPAIR-${failReadback}`;
    orderMutationFlowStore.clearAll();
    const before = { case_no: caseNo, lifecycle_version: 0, current_status: '待補件', target_status: '洽談中',
      current_start_date: '2026-11-15', current_service_days: 20, missing_fields: [], blockers: [],
      apply_allowed: true, preview_fingerprint: FP1,
      current_service_time: { service_hours_per_day: null, start_time: null, end_time: null, end_day_offset: null } };
    const time = { service_hours_per_day: 8, start_time: '09:00:00', end_time: '17:00:00', end_day_offset: 0 as const };
    const repaired = { ...before, lifecycle_version: 1, preview_fingerprint: FP2, current_service_time: time };
    const completed = { ...repaired, lifecycle_version: 2, current_status: '洽談中', apply_allowed: false, blockers: ['order_intake_completion_status_not_eligible'] };
    let saved = false;
    let advanced = false;
    let readbackUnavailable = failReadback;
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockImplementation(async () => {
      if (advanced && readbackUnavailable) throw new Error('readback interrupted');
      return advanced ? completed : saved ? repaired : before;
    });
    vi.spyOn(orderIntakeCompletionClient, 'previewTerms').mockResolvedValue({ case_no: caseNo, lifecycle_version: 0,
      before_start_date: '2026-11-15', after_start_date: '2026-11-15', before_service_days: 20, after_service_days: 20,
      before_service_time: before.current_service_time, after_service_time: time, changed_fields: ['service_time'],
      blockers: [], apply_allowed: true, preview_fingerprint: FP1 });
    const termsApply = vi.spyOn(orderIntakeCompletionClient, 'applyTerms').mockImplementation(async () => {
      saved = true;
      return { receipt_key: 'terms', case_no: caseNo, lifecycle_version: 1, start_date: '2026-11-15', service_days: 20,
        service_time: time, changed_fields: ['service_time'], preview_fingerprint: FP1, replayed: false };
    });
    const completionApply = vi.spyOn(orderIntakeCompletionClient, 'applyCompletion').mockImplementation(async () => {
      advanced = true;
      return { receipt_key: 'completion', case_no: caseNo, lifecycle_version: 2, status: '洽談中', preview_fingerprint: FP2, replayed: false };
    });
    const stateChanged = vi.fn();
    render(<OrderIntakeRepairPanel caseNo={caseNo} registry repairServiceTime focusMissing onEditStateChange={stateChanged} />);
    const start = await screen.findByLabelText('每日開始時間');
    await waitFor(() => expect(start).toHaveFocus());
    expect(screen.queryByRole('button', { name: '確認完成進件補齊' })).not.toBeInTheDocument();
    fireEvent.change(start, { target: { value: '09:00' } });
    fireEvent.change(screen.getByLabelText('每日結束時間'), { target: { value: '17:00' } });
    expect(screen.getByLabelText('每日服務時數')).toHaveValue(8);
    expect(screen.getByLabelText('備註（選填）')).toHaveValue('');
    expect(screen.getByLabelText('備註（選填）')).not.toHaveAttribute('aria-required');
    fireEvent.click(screen.getByRole('button', { name: '儲存服務資料' }));
    expect(screen.queryByRole('button', { name: '確認儲存服務資料' })).not.toBeInTheDocument();
    await waitFor(() => expect(completionApply).toHaveBeenCalledWith(caseNo, repaired, '', expect.stringContaining(`orders-intake-complete-${caseNo}-`)));
    if (failReadback) {
      await screen.findByRole('button', { name: '只重新讀取補件結果' });
      expect(stateChanged).toHaveBeenLastCalledWith(expect.objectContaining({ busy: true }));
      expect(orderMutationFlowStore.getIntakeRepair(caseNo, 'completion')?.receipt?.lifecycle_version).toBe(2);
      readbackUnavailable = false;
      fireEvent.click(screen.getByRole('button', { name: '只重新讀取補件結果' }));
    }
    await screen.findByText('進件缺件已完成，案件已回讀最新狀態。');
    await waitFor(() => expect(stateChanged).toHaveBeenLastCalledWith({ dirty: false, busy: false }));
    expect(termsApply).toHaveBeenCalledOnce();
    expect(completionApply).toHaveBeenCalledOnce();
    expect(orderMutationFlowStore.getIntakeRepair(caseNo, 'completion')).toBeUndefined();
  });

  it('案件處理缺件摘要只列出缺漏並導向名冊，不提供第二份編輯表單', async () => {
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 0, current_status: '待補件', target_status: '洽談中',
      current_start_date: '2026-11-15', current_service_days: 20, missing_fields: [], blockers: [], apply_allowed: true, preview_fingerprint: FP1,
      current_service_time: { start_time: null, end_time: null, end_day_offset: null, service_hours_per_day: null },
    });
    render(<OrderIntakeRepairPanel caseNo="CASE-153" repairServiceTime summaryHref="#clients?case=CASE-153&field=intake&from=workbench" />);
    await screen.findByText('每日服務時數');
    expect(screen.getByRole('link', { name: '前往補齊案件資料 →' })).toHaveAttribute('href', '#clients?case=CASE-153&field=intake&from=workbench');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認完成進件補齊' })).not.toBeInTheDocument();
  });

  it('基本補件已齊備時仍指出正式服務條件缺件，不顯示缺少資料為無', async () => {
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, current_status: '洽談中', target_status: '洽談中',
      current_start_date: '2026-10-15', current_service_days: 30, missing_fields: [],
      blockers: ['order_intake_completion_status_not_eligible'], apply_allowed: false, preview_fingerprint: FP1,
    });
    render(<OrderIntakeRepairPanel caseNo="CASE-153" orderStatus="洽談中" remainingServiceIssues={['缺少欄位：服務時間。']} />);
    expect(await screen.findByText('姓名、日期與天數已齊備；仍需完成上方所列的服務條件。')).toBeInTheDocument();
    expect(screen.queryByText('缺少資料：無')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認完成進件補齊' })).not.toBeInTheDocument();
  });

  it('缺時數時補齊起訖與協調時數，保留日期天數，且服務時間未正式回讀不得宣稱完成', async () => {
    const caseNo = 'CASE-TIME-REPAIR';
    const savedTime = { service_hours_per_day: 8, start_time: '08:00:00', end_time: '17:00:00', end_day_offset: 0 as const };
    const beforeTime = { service_hours_per_day: null, start_time: null, end_time: null, end_day_offset: null };
    const completion = { case_no: caseNo, lifecycle_version: 7, current_status: '洽談中', target_status: '洽談中',
      current_start_date: '2026-11-15', current_service_days: 21, current_service_time: beforeTime,
      missing_fields: [], blockers: ['order_intake_completion_status_not_eligible'], apply_allowed: false, preview_fingerprint: FP1 };
    const query = vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue(completion);
    const preview = { case_no: caseNo, lifecycle_version: 7, before_start_date: '2026-11-15', before_service_days: 21,
      after_start_date: '2026-11-15', after_service_days: 21, before_service_time: beforeTime, after_service_time: savedTime,
      changed_fields: ['service_time' as const], blockers: [], apply_allowed: true, preview_fingerprint: FP1 };
    const previewTerms = vi.spyOn(orderIntakeCompletionClient, 'previewTerms').mockResolvedValue(preview);
    const apply = vi.spyOn(orderIntakeCompletionClient, 'applyTerms').mockResolvedValue({ receipt_key: 'time-repair',
      case_no: caseNo, lifecycle_version: 8, start_date: '2026-11-15', service_days: 21,
      service_time: savedTime, changed_fields: ['service_time'], preview_fingerprint: FP1, replayed: false });
    const onChanged = vi.fn();
    render(<OrderIntakeRepairPanel caseNo={caseNo} orderStatus="洽談中" repairServiceTime
      remainingServiceIssues={['缺少欄位：服務時間。']} onChanged={onChanged} />);
    fireEvent.change(await screen.findByLabelText('每日開始時間'), { target: { value: '08:00' } });
    fireEvent.change(screen.getByLabelText('每日結束時間'), { target: { value: '17:00' } });
    expect(screen.getByLabelText('每日服務時數')).toHaveValue(9);
    fireEvent.change(screen.getByLabelText('每日服務時數'), { target: { value: '8' } });
    expect(screen.queryByLabelText('約定服務開始日')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('服務天數')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('備註（選填）'), { target: { value: '確認每日實際服務八小時' } });
    query.mockResolvedValue({ ...completion, lifecycle_version: 8 });
    fireEvent.click(screen.getByRole('button', { name: '儲存服務資料' }));
    await waitFor(() => expect(previewTerms).toHaveBeenCalledWith(caseNo, '2026-11-15', 21, expect.objectContaining({ proposedServiceTime: savedTime })));
    expect(screen.queryByRole('button', { name: '確認儲存服務資料' })).not.toBeInTheDocument();
    await screen.findByRole('button', { name: '只重新讀取補件結果' });
    expect(apply).toHaveBeenCalledOnce();
    query.mockResolvedValue({ ...completion, lifecycle_version: 8, current_service_time: savedTime });
    fireEvent.click(screen.getByRole('button', { name: '只重新讀取補件結果' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: '只重新讀取補件結果' })).not.toBeInTheDocument());
    expect(apply).toHaveBeenCalledOnce();
    expect(onChanged).toHaveBeenCalledTimes(2);
  });

  it('repairs the actual HCM fields in case processing and rereads the remaining warnings without resaving valid terms', async () => {
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, current_status: '待補件', target_status: '洽談中',
      current_start_date: '2026-10-15', current_service_days: 30,
      missing_fields: [], blockers: ['order_intake_completion_service_data_locked'],
      apply_allowed: false, preview_fingerprint: FP1,
    });
    vi.mocked(hcmResubmissionClient.current)
      .mockResolvedValueOnce({ items: [{ source_id: 30, review_identity: 'current', case_no: 'CASE-153', fields: ['行動電話'], can_correct: true }], next_cursor: null })
      .mockResolvedValue({ items: [], next_cursor: null });
    vi.spyOn(clientRegistryClient, 'preview').mockResolvedValue({
      owner: 'client_profile', aggregate_identity: 'CASE-153', current_version: 2,
      before: { phone: null }, after: { phone: '0912345678' }, preview_fingerprint: FP1,
    });
    const apply = vi.spyOn(clientRegistryClient, 'apply').mockImplementation(async (caseNo, _owner, _changes, _version, fp, _reason, key) => ({
      owner: 'client_profile', aggregate_identity: caseNo, resulting_version: 3,
      changed_fields: ['phone'], preview_fingerprint: fp, idempotency_key: key!, replayed: false,
      readback: { phone: '0912345678' },
    }));
    const applyTerms = vi.spyOn(orderIntakeCompletionClient, 'applyTerms');
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(<OrderIntakeRepairPanel caseNo="CASE-153" orderStatus="待補件" onChanged={onChanged} />);
    const phone = await screen.findByLabelText('電話（手機／市話）');
    expect(screen.queryByLabelText('服務方式')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('約定服務開始日')).not.toBeInTheDocument();
    fireEvent.change(phone, { target: { value: '0912345678' } });
    fireEvent.change(screen.getByLabelText('備註（選填）'), { target: { value: '核對並修正電話' } });
    vi.mocked(clientRegistryClient.query).mockResolvedValue({ ...profileDetail, client: {
      ...profileDetail.client, version: 3, values: { ...profileDetail.client.values, phone: '0912345678' },
    } });
    fireEvent.click(screen.getByRole('button', { name: '儲存缺件資料' }));
    expect(screen.queryByRole('button', { name: '確認儲存缺件資料' })).not.toBeInTheDocument();
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
    expect(screen.queryByLabelText('電話（手機／市話）')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('服務方式')).not.toBeInTheDocument();
    expect(apply.mock.calls[0][2]).toEqual({ phone: '0912345678' });
    expect(applyTerms).not.toHaveBeenCalled();
  });

  afterEach(() => {
    cleanup();
    orderMutationFlowStore.clearAll();
    vi.restoreAllMocks();
  });

  it('keeps complete service dates and days out of the supplementation form until staff explicitly edits them', async () => {
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, current_status: '待補件', target_status: '洽談中',
      current_start_date: '2026-10-15', current_service_days: 30,
      missing_fields: [], blockers: [], apply_allowed: true, preview_fingerprint: FP1,
    });
    const previewTerms = vi.spyOn(orderIntakeCompletionClient, 'previewTerms');
    render(<OrderIntakeRepairPanel caseNo="CASE-153" orderStatus="待補件" />);
    const edit = await screen.findByRole('button', { name: '修改服務日期／天數' });
    expect(screen.queryByLabelText('約定服務開始日')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('服務天數')).not.toBeInTheDocument();
    expect(screen.queryByText('目前不可完成補件')).not.toBeInTheDocument();
    expect(previewTerms).not.toHaveBeenCalled();
    fireEvent.click(edit);
    expect(screen.getByLabelText('約定服務開始日')).toHaveValue('2026-10-15');
    expect(screen.getByLabelText('服務天數')).toHaveValue(30);
  });

  it.each(['start_date', 'service_days'] as const)('drawer only shows missing %s and preserves the other saved term in Preview', async (missing) => {
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, current_status: '待補件', target_status: '洽談中',
      current_start_date: missing === 'start_date' ? null : '2026-10-15',
      current_service_days: missing === 'service_days' ? null : 30,
      missing_fields: [missing], blockers: [], apply_allowed: false, preview_fingerprint: FP1,
    });
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockRejectedValue(new Error('partial order detail'));
    const previewTerms = vi.spyOn(orderIntakeCompletionClient, 'previewTerms').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, before_start_date: null, before_service_days: null,
      after_start_date: '2026-10-15', after_service_days: 30, changed_fields: [missing],
      blockers: ['synthetic_terms_owner_blocker'], apply_allowed: false, preview_fingerprint: FP1,
    });
    const applyTerms = vi.spyOn(orderIntakeCompletionClient, 'applyTerms').mockRejectedValue(new Error('unexpected apply'));
    const onChanged = vi.fn();
    render(<OrderIntakeRepairPanel caseNo="CASE-153" orderStatus="待補件" onChanged={onChanged} />);
    const missingLabel = missing === 'start_date' ? '約定服務開始日' : '服務天數';
    const savedLabel = missing === 'start_date' ? '服務天數' : '約定服務開始日';
    const input = await screen.findByLabelText(missingLabel);
    expect(screen.queryByLabelText(savedLabel)).not.toBeInTheDocument();
    fireEvent.change(input, { target: { value: missing === 'start_date' ? '2026-10-15' : '30' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存日期與天數' }));
    await waitFor(() => expect(previewTerms).toHaveBeenCalledWith('CASE-153', '2026-10-15', 30, expect.any(Object)));
    await screen.findByText('synthetic_terms_owner_blocker');
    expect(applyTerms).not.toHaveBeenCalled();
    expect(onChanged).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '儲存日期與天數' })).toBeEnabled();
  });

  it.each([false, true])('姓名備註留白且日期仍缺件時，使用客戶主檔正式回讀，名稱不一致則保留保護（不一致=%s）', async (mismatched) => {
    orderMutationFlowStore.clearAll();
    let saved = false;
    const generalDetail = vi.spyOn(ordersQueryClient, 'getOrderDetail').mockRejectedValue(new Error('incomplete order projection'));
    vi.mocked(clientRegistryClient.query).mockImplementation(async () => ({ ...profileDetail,
      client: { ...profileDetail.client, values: { ...profileDetail.client.values,
        name: saved ? (mismatched ? '另一姓名' : '合成補件姓名') : null } } }));
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockImplementation(async () => ({
      case_no: 'CASE-153', lifecycle_version: 7, current_status: '待補件', target_status: '洽談中',
      current_start_date: null, current_service_days: null,
      missing_fields: saved ? ['start_date', 'service_days'] : ['client_name', 'start_date', 'service_days'],
      blockers: [], apply_allowed: false, preview_fingerprint: FP1,
    }));
    vi.spyOn(orderIntakeCompletionClient, 'previewClientName').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, before_client_name: null, after_client_name: '合成補件姓名',
      blockers: [], apply_allowed: true, preview_fingerprint: FP1,
    });
    const apply = vi.spyOn(orderIntakeCompletionClient, 'applyClientName').mockImplementation(async () => {
      saved = true;
      return { receipt_key: 'name-receipt', case_no: 'CASE-153', lifecycle_version: 7,
        client_name: '合成補件姓名', preview_fingerprint: FP1, replayed: false };
    });
    render(<OrderIntakeRepairPanel caseNo="CASE-153" registry />);
    fireEvent.change(await screen.findByLabelText('客戶姓名'), { target: { value: '合成補件姓名' } });
    expect(screen.getByLabelText('備註（選填）')).toHaveValue('');
    fireEvent.click(screen.getByRole('button', { name: '儲存姓名' }));
    expect(screen.queryByRole('button', { name: '確認儲存姓名' })).not.toBeInTheDocument();
    if (mismatched) {
      await screen.findByRole('button', { name: '只重新讀取補件結果' });
      expect(screen.getByLabelText('約定服務開始日')).toBeDisabled();
      expect(screen.queryByText('客戶姓名已補齊並完成回讀。')).not.toBeInTheDocument();
    } else {
      await screen.findByText('客戶姓名已補齊並完成回讀。');
      expect(screen.getByLabelText('約定服務開始日')).toBeEnabled();
      expect(screen.getByLabelText('服務天數')).toBeEnabled();
      expect(screen.queryByRole('button', { name: '只重新讀取補件結果' })).not.toBeInTheDocument();
    }
    expect(apply).toHaveBeenCalledWith('CASE-153', expect.any(Object), '', expect.any(String));
    expect(apply).toHaveBeenCalledOnce();
    expect(generalDetail).not.toHaveBeenCalled();
  });

  it('retains owner dates and days when a missing name causes general detail to return empty terms', async () => {
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, current_status: '待補件', target_status: '洽談中',
      current_start_date: '2026-10-15', current_service_days: 30,
      missing_fields: ['client_name'], blockers: [], apply_allowed: false, preview_fingerprint: FP1,
    });
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue({
      ...incompleteSummary, client_name: '待補姓名（CASE-153）', service_days: 0,
      client_id: 1, staff_id: null, cancel_reason: null, line_group_id: null,
      contract_identity: null, deposit_date: null, service_hours_per_day: 0,
      deposit_service_days: null, floor_fee: 0, custom_rest_dates: null,
    });
    render(<OrderIntakeRepairPanel caseNo="CASE-153" orderStatus="待補件" />);
    await screen.findByLabelText('客戶姓名');
    fireEvent.click(screen.getByRole('button', { name: '修改服務日期／天數' }));
    expect(screen.getByLabelText('約定服務開始日')).toHaveValue('2026-10-15');
    expect(screen.getByLabelText('服務天數')).toHaveValue(30);
  });

  it('card preserves the owner date while repairing days even when summary terms are empty', async () => {
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, current_status: '待補件', target_status: '洽談中',
      current_start_date: '2026-10-15', current_service_days: null,
      missing_fields: ['service_days'], blockers: [], apply_allowed: false, preview_fingerprint: FP1,
    });
    const previewTerms = vi.spyOn(orderIntakeCompletionClient, 'previewTerms').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, before_start_date: '2026-10-15', before_service_days: null,
      after_start_date: '2026-10-15', after_service_days: 30, changed_fields: ['service_days'],
      blockers: [], apply_allowed: true, preview_fingerprint: FP1,
    });
    render(<OrdersIntakeRepairCard item={{ ...incompleteSummary, client_name: '測試客戶' }} onChanged={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText('CASE-153 服務天數'), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存服務資料補件' }));
    await waitFor(() => expect(previewTerms).toHaveBeenCalledWith('CASE-153', '2026-10-15', 30));
  });

  it.each(['start_date', 'service_days'] as const)('card only shows missing %s rather than a disabled valid field', async (missing) => {
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, current_status: '待補件', target_status: '洽談中',
      missing_fields: [missing], blockers: [], apply_allowed: false, preview_fingerprint: FP1,
    });
    render(<OrdersIntakeRepairCard item={{ ...incompleteSummary, client_name: '測試客戶',
      start_date: missing === 'start_date' ? null : '2026-10-15',
      service_days: missing === 'service_days' ? null : 30,
    }} onChanged={vi.fn()} />);
    const missingLabel = missing === 'start_date' ? 'CASE-153 約定服務開始日' : 'CASE-153 服務天數';
    const savedLabel = missing === 'start_date' ? 'CASE-153 服務天數' : 'CASE-153 約定服務開始日';
    expect(await screen.findByLabelText(missingLabel)).toBeInTheDocument();
    expect(screen.queryByLabelText(savedLabel)).not.toBeInTheDocument();
  });

  it.each(['居住型態', '手機'])('顯示實際待修正欄位 %s 並區分尚未建立的案件資料', async (field) => {
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, current_status: '待補件', target_status: '洽談中',
      missing_fields: ['start_date', 'service_days'], blockers: [], apply_allowed: false, preview_fingerprint: FP1,
    });
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockRejectedValue(new Error('partial order detail'));
    vi.mocked(hcmResubmissionClient.current).mockResolvedValue({
      items: [
        { source_id: 40, review_identity: 'other', case_no: 'CASE-OTHER', fields: ['其他欄位'], can_correct: true },
        { source_id: 30, review_identity: 'current', case_no: 'CASE-153', fields: [field], can_correct: true },
      ],
      next_cursor: null,
    });
    const applyTerms = vi.spyOn(orderIntakeCompletionClient, 'applyTerms');
    const applyCompletion = vi.spyOn(orderIntakeCompletionClient, 'applyCompletion');

    render(<OrderIntakeRepairPanel caseNo="CASE-153" orderStatus="待補件" />);

    expect(await screen.findByText(`原始進件欄位待修正：${field}`)).toBeInTheDocument();
    expect(screen.getByText('尚未補齊的案件資料：約定服務開始日、服務天數')).toBeInTheDocument();
    expect(screen.queryByText('缺少資料：約定服務開始日、服務天數')).not.toBeInTheDocument();
    expect(screen.queryByText(/其他欄位/)).not.toBeInTheDocument();
    expect(applyTerms).not.toHaveBeenCalled();
    expect(applyCompletion).not.toHaveBeenCalled();
  });

  it('lists every current missing field while leaving complete orders on the existing workbench', async () => {
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({
      items: [incompleteSummary, completeSummary],
      next_cursor: null,
      etag: ETAG,
    });
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153',
      lifecycle_version: 7,
      current_status: '待補件',
      target_status: '洽談中',
      missing_fields: ['client_name', 'start_date', 'service_days'],
      blockers: ['order_intake_completion_service_data_locked'],
      apply_allowed: false,
      preview_fingerprint: FP1,
    });

    render(<OrdersIntakeRepairCard item={incompleteSummary} onChanged={vi.fn().mockResolvedValue(undefined)} />);

    expect(await screen.findByText('CASE-153')).toBeInTheDocument();
    expect(screen.getByText('客戶姓名', { selector: 'li' })).toBeInTheDocument();
    expect(screen.getByText('約定服務開始日', { selector: 'li' })).toBeInTheDocument();
    expect(screen.getByText('服務天數', { selector: 'li' })).toBeInTheDocument();
    expect(await screen.findByText('服務資料已鎖定，目前不能完成進件補齊。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '儲存服務資料補件' })).toBeDisabled();
    expect(screen.queryByText('CASE-OK')).not.toBeInTheDocument();
  });

  it('applies typed terms repair, rechecks completion, restores normal status, and refreshes the list', async () => {
    const pendingWithName = {
      ...incompleteSummary,
      client_name: '王小明',
    };
    const repaired = {
      ...pendingWithName,
      order_status: '洽談中',
      start_date: '2026-09-10',
      service_days: 30,
    };
    vi.spyOn(ordersQueryClient, 'getOrderSummaries')
      .mockResolvedValueOnce({ items: [pendingWithName], next_cursor: null, etag: ETAG })
      .mockResolvedValueOnce({ items: [repaired], next_cursor: null, etag: ETAG });
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion')
      .mockResolvedValueOnce({
        case_no: 'CASE-153',
        lifecycle_version: 7,
        current_status: '待補件',
        target_status: '洽談中',
        missing_fields: ['start_date', 'service_days'],
        blockers: [],
        apply_allowed: false,
        preview_fingerprint: FP1,
      })
      .mockResolvedValueOnce({
        case_no: 'CASE-153',
        lifecycle_version: 8,
        current_status: '待補件',
        target_status: '洽談中',
        missing_fields: [],
        blockers: [],
        apply_allowed: true,
        preview_fingerprint: FP2,
      });
    vi.spyOn(orderIntakeCompletionClient, 'previewTerms').mockResolvedValue({
      case_no: 'CASE-153',
      lifecycle_version: 7,
      before_start_date: null,
      before_service_days: null,
      after_start_date: '2026-09-10',
      after_service_days: 30,
      changed_fields: ['start_date', 'service_days'],
      blockers: [],
      apply_allowed: true,
      preview_fingerprint: FP1,
    });
    const applyTerms = vi.spyOn(orderIntakeCompletionClient, 'applyTerms').mockResolvedValue({
      receipt_key: 'terms-receipt',
      case_no: 'CASE-153',
      lifecycle_version: 8,
      start_date: '2026-09-10',
      service_days: 30,
      changed_fields: ['start_date', 'service_days'],
      preview_fingerprint: FP1,
      replayed: false,
    });
    const applyCompletion = vi.spyOn(orderIntakeCompletionClient, 'applyCompletion').mockResolvedValue({
      receipt_key: 'completion-receipt',
      case_no: 'CASE-153',
      lifecycle_version: 9,
      status: '洽談中',
      preview_fingerprint: FP2,
      replayed: false,
    });

    render(<OrdersIntakeRepairCard item={pendingWithName} onChanged={vi.fn().mockResolvedValue(undefined)} />);

    fireEvent.change(await screen.findByLabelText('CASE-153 約定服務開始日'), {
      target: { value: '2026-09-10' },
    });
    fireEvent.change(screen.getByLabelText('CASE-153 服務天數'), {
      target: { value: '30' },
    });
    fireEvent.change(screen.getByLabelText('CASE-153 備註（選填）'), {
      target: { value: '補齊原始進件缺漏' },
    });
    await waitFor(() => expect(screen.getByRole('button', { name: '儲存服務資料補件' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '儲存服務資料補件' }));
    await waitFor(() => expect(orderIntakeCompletionClient.previewTerms).toHaveBeenCalled());
    await expect(vi.mocked(orderIntakeCompletionClient.previewTerms).mock.results[0].value).resolves.toMatchObject({
      changed_fields: ['start_date', 'service_days'], before_start_date: null, before_service_days: null,
      after_start_date: '2026-09-10', after_service_days: 30,
    });
    expect(screen.queryByRole('button', { name: '確認補齊服務資料' })).not.toBeInTheDocument();

    await waitFor(() => expect(applyTerms).toHaveBeenCalledWith(
      'CASE-153',
      expect.objectContaining({ lifecycle_version: 7, preview_fingerprint: FP1 }),
      '補齊原始進件缺漏',
      expect.stringContaining('orders-intake-terms-CASE-153-'),
    ));
    await waitFor(() => expect(applyCompletion).toHaveBeenCalledWith(
      'CASE-153',
      expect.objectContaining({ lifecycle_version: 8, preview_fingerprint: FP2 }),
      '補齊原始進件缺漏',
      expect.stringContaining('orders-intake-complete-CASE-153-'),
    ));
    await waitFor(() => expect(applyCompletion).toHaveBeenCalled());
  });

  it.each([true, false])('one-click name repair preserves owner Preview facts and honors apply_allowed=%s', async (allowed) => {
    const onChanged = vi.fn().mockResolvedValue(undefined);
    vi.spyOn(orderIntakeCompletionClient, 'previewCompletion').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, current_status: '待補件', target_status: '洽談中',
      missing_fields: ['client_name'], blockers: [], apply_allowed: false, preview_fingerprint: FP1,
    });
    vi.spyOn(orderIntakeCompletionClient, 'previewClientName').mockResolvedValue({
      case_no: 'CASE-153', lifecycle_version: 7, before_client_name: null,
      after_client_name: '合成補件姓名', blockers: allowed ? [] : ['synthetic_name_owner_blocker'],
      apply_allowed: allowed, preview_fingerprint: FP1,
    });
    const applyName = vi.spyOn(orderIntakeCompletionClient, 'applyClientName').mockResolvedValue({
      receipt_key: 'name-receipt', case_no: 'CASE-153', lifecycle_version: 7,
      client_name: '合成補件姓名', preview_fingerprint: FP1, replayed: false,
    });
    render(<OrdersIntakeRepairCard item={{ ...incompleteSummary, start_date: '2026-09-10', service_days: 5 }} onChanged={onChanged} />);
    fireEvent.change(await screen.findByLabelText('CASE-153 客戶姓名'), { target: { value: '合成補件姓名' } });
    expect(applyName).not.toHaveBeenCalled();
    expect(screen.getByLabelText('CASE-153 備註（選填）')).toHaveValue('');
    fireEvent.click(screen.getByRole('button', { name: '儲存姓名補件' }));
    await waitFor(() => expect(orderIntakeCompletionClient.previewClientName).toHaveBeenCalledOnce());
    await expect(vi.mocked(orderIntakeCompletionClient.previewClientName).mock.results[0].value).resolves.toMatchObject({
      before_client_name: null, after_client_name: '合成補件姓名', apply_allowed: allowed,
    });
    expect(screen.queryByRole('button', { name: '確認補齊客戶姓名' })).not.toBeInTheDocument();
    if (!allowed) {
      expect(screen.getByLabelText('姓名補件阻擋原因')).toHaveTextContent('synthetic_name_owner_blocker');
      fireEvent.click(screen.getByRole('button', { name: '儲存姓名補件' }));
      await waitFor(() => expect(orderIntakeCompletionClient.previewClientName).toHaveBeenCalledTimes(2));
      expect(applyName).not.toHaveBeenCalled();
      expect(onChanged).not.toHaveBeenCalled();
      return;
    }
    await waitFor(() => expect(applyName).toHaveBeenCalledWith(
      'CASE-153', expect.objectContaining({ apply_allowed: true, preview_fingerprint: FP1 }),
      '', expect.stringContaining('orders-intake-client-name-CASE-153-'),
    ));
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  });

  it('allows a newly imported discussion case to correct existing date and days without Finance, Payroll, or assignment roots', async () => {
    const previewCompletion = vi.spyOn(orderIntakeCompletionClient, 'previewCompletion')
      .mockResolvedValueOnce({
        case_no: 'CASE-EARLY-CORRECTION', lifecycle_version: 7,
        current_status: '洽談中', target_status: '洽談中',
        current_start_date: '2026-09-10', current_service_days: 30,
        missing_fields: [], blockers: ['order_intake_completion_status_not_eligible'],
        apply_allowed: false, preview_fingerprint: FP1,
      })
      .mockResolvedValueOnce({
        case_no: 'CASE-EARLY-CORRECTION', lifecycle_version: 8,
        current_status: '洽談中', target_status: '洽談中',
        current_start_date: '2026-09-12', current_service_days: 28,
        missing_fields: [], blockers: ['order_intake_completion_status_not_eligible'],
        apply_allowed: false, preview_fingerprint: FP2,
      });
    const previewTerms = vi.spyOn(orderIntakeCompletionClient, 'previewTerms').mockResolvedValue({
      case_no: 'CASE-EARLY-CORRECTION', lifecycle_version: 7,
      before_start_date: '2026-09-10', before_service_days: 30,
      after_start_date: '2026-09-12', after_service_days: 28,
      changed_fields: ['start_date', 'service_days'], blockers: [],
      apply_allowed: true, preview_fingerprint: FP1,
    });
    const applyTerms = vi.spyOn(orderIntakeCompletionClient, 'applyTerms').mockResolvedValue({
      receipt_key: 'early-correction-receipt', case_no: 'CASE-EARLY-CORRECTION',
      lifecycle_version: 8, start_date: '2026-09-12', service_days: 28,
      changed_fields: ['start_date', 'service_days'], preview_fingerprint: FP1,
      replayed: false,
    });
    const detail = vi.spyOn(ordersQueryClient, 'getOrderDetail');

    render(<OrderIntakeRepairPanel caseNo="CASE-EARLY-CORRECTION" orderStatus="洽談中" />);

    fireEvent.click(await screen.findByRole('button', { name: '修改服務日期／天數' }));
    expect(await screen.findByLabelText('約定服務開始日')).toHaveValue('2026-09-10');
    expect(screen.getByLabelText('服務天數')).toHaveValue(30);
    fireEvent.change(screen.getByLabelText('約定服務開始日'), { target: { value: '2026-09-12' } });
    fireEvent.change(screen.getByLabelText('服務天數'), { target: { value: '28' } });
    fireEvent.change(screen.getByLabelText('備註（選填）'), {
      target: { value: '修正剛匯入的服務條件' },
    });
    fireEvent.click(screen.getByRole('button', { name: '儲存日期與天數' }));
    await waitFor(() => expect(previewTerms).toHaveBeenCalledWith('CASE-EARLY-CORRECTION', '2026-09-12', 28, expect.anything()));
    expect(screen.queryByRole('button', { name: '確認儲存日期與天數' })).not.toBeInTheDocument();

    await waitFor(() => expect(applyTerms).toHaveBeenCalled());
    await waitFor(() => expect(previewCompletion).toHaveBeenCalledTimes(2));
    expect(detail).not.toHaveBeenCalled();
    expect(await screen.findByText('約定服務開始日／天數已更新並完成回讀。')).toBeInTheDocument();
  });

});


describe('intake typed client optional-note serialization', () => {
  it.each(['', '   ', ' 工會補充 '])('sends all three actual Apply requests with optional note %j', async (note) => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-test-session');
    const stoppedAtTransport = new Error('serialization verified; no HTTP writes');
    const post = vi.spyOn(transport, 'post').mockRejectedValue(stoppedAtTransport);
    const terms: Parameters<typeof orderIntakeCompletionClient.applyTerms>[1] = { case_no: 'CASE-NOTE', lifecycle_version: 0, before_start_date: null, before_service_days: null,
      after_start_date: '2026-11-01', after_service_days: 26, changed_fields: ['start_date', 'service_days'],
      blockers: [], apply_allowed: true, preview_fingerprint: FP1 };
    const name = { case_no: 'CASE-NOTE', lifecycle_version: 0, before_client_name: null,
      after_client_name: '合成測試', blockers: [], apply_allowed: true, preview_fingerprint: FP1 };
    const completion = { case_no: 'CASE-NOTE', lifecycle_version: 0, current_status: '待補件', target_status: '洽談中',
      missing_fields: [], blockers: [], apply_allowed: true, preview_fingerprint: FP1 };
    const commands = [
      () => orderIntakeCompletionClient.applyTerms('CASE-NOTE', terms, note, 'note-terms'),
      () => orderIntakeCompletionClient.applyClientName('CASE-NOTE', name, note, 'note-name'),
      () => orderIntakeCompletionClient.applyCompletion('CASE-NOTE', completion, note, 'note-complete'),
    ];
    for (const command of commands) {
      await expect(command()).rejects.toBe(stoppedAtTransport);
      expect(post).toHaveBeenLastCalledWith(expect.stringMatching(/\/apply$/),
        expect.objectContaining({ reason: note.trim(), expected_lifecycle_version: 0, preview_fingerprint: FP1 }),
        expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }) }));
    }
    expect(post).toHaveBeenCalledTimes(3);
  });
});
