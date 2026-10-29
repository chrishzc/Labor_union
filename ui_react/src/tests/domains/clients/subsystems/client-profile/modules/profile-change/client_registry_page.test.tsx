import { UnsavedChangesProvider } from '../../../../../../../components/UnsavedChanges';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { StrictMode, useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientRegistryPage } from '../../../../../../../pages/ClientRegistryPage';
import { ClientRegistryDetailEditor } from '../../../../../../../components/ClientRegistryDetailEditor';
import { ClientRegistryDetailSchema } from '../../../../../../../api/client_registry/client_registry_schemas';
import { ApiTimeoutError, ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { historicalAdoptionEvidenceClient } from '../../../../../../../api/orders/historical_adoption_evidence_client';

vi.mock('../../../../../../../components/CaseArchitectureBootstrapRepairPanel', () => ({
  CaseArchitectureBootstrapRepairPanel: ({ caseNo }: { caseNo: string }) => <div aria-label="案件初始資料修復">{caseNo}</div>,
}));

const mocks = vi.hoisted(() => ({ list: vi.fn(), query: vi.fn(), history: vi.fn(), preview: vi.fn(), apply: vi.fn() }));
const completionMocks = vi.hoisted(() => ({ previewCompletion: vi.fn() }));
vi.mock('../../../../../../../api/orders/order_intake_completion_client', async (original) => ({
  ...await original<typeof import('../../../../../../../api/orders/order_intake_completion_client')>(), orderIntakeCompletionClient: completionMocks,
}));
vi.mock('../../../../../../../api/client_registry/client_registry_client', () => ({ clientRegistryClient: mocks }));
vi.mock('../../../../../../../api/case_import/hcm_resubmission_client', async (original) => ({
  ...await original<typeof import('../../../../../../../api/case_import/hcm_resubmission_client')>(),
  loadCurrentHcmReviewsForCases: vi.fn(async () => []),
}));
vi.mock('../../../../../../../api/client_finance/case_virtual_account_client', () => ({
  caseVirtualAccountClient: { query: async (caseNo: string) => ({ case_no: caseNo, imported_virtual_accounts: [], built_in_virtual_account: null, mapping_ids: [] }) },
}));
vi.mock('../../../../../../../components/OrderTermsMutationPanel', async (original) => ({
  ...await original<typeof import('../../../../../../../components/OrderTermsMutationPanel')>(), OrderTermsMutationPanel: () => <div>訂單條款 owner</div>,
}));
const staffMocks = vi.hoisted(() => ({ assignment: vi.fn(), directory: vi.fn(), query: vi.fn(), preview: vi.fn(), apply: vi.fn(), orderDetail: vi.fn() }));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getAssignmentPlan: staffMocks.assignment, getOrderDetail: staffMocks.orderDetail } }));
vi.mock('../../../../../../../api/staff_directory/staff_directory_client', () => ({ loadActiveStaffIds: vi.fn().mockResolvedValue(new Set([9, 10, 22])), createStaffDirectoryClient: () => ({ queryPage: staffMocks.directory }) }));
vi.mock('../../../../../../../api/orders/service_before_replacement_client', async (original) => ({
  ...await original<typeof import('../../../../../../../api/orders/service_before_replacement_client')>(),
  serviceBeforeReplacementClient: { query: staffMocks.query, preview: staffMocks.preview, apply: staffMocks.apply },
}));
const candidateMocks = vi.hoisted(() => ({ search: vi.fn(), pool: vi.fn(), add: vi.fn(), willingness: vi.fn(), createPlan: vi.fn(), activePlan: vi.fn(), contact: vi.fn(), decision: vi.fn(), confirmationPreview: vi.fn() }));
vi.mock('../../../../../../../api/scheduling/matching_candidate_workflow_client', async (original) => ({
  ...await original<typeof import('../../../../../../../api/scheduling/matching_candidate_workflow_client')>(),
  matchingCandidateWorkflowClient: { searchInquiryCandidates: candidateMocks.search, createSingleCaregiverPlan: candidateMocks.createPlan },
}));
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', async (original) => ({
  ...await original<typeof import('../../../../../../../api/scheduling/candidate_contact_pool_client')>(),
  candidateContactPoolClient: { query: candidateMocks.pool, addCandidates: candidateMocks.add, recordWillingness: candidateMocks.willingness },
}));
vi.mock('../../../../../../../api/scheduling/waiting_deposit_lock_client', () => ({ waitingDepositLockClient: { queryPlan: candidateMocks.activePlan } }));
vi.mock('../../../../../../../api/scheduling/matching_plan_communication_client', () => ({ matchingPlanCommunicationClient: { queryContactState: candidateMocks.contact, recordCustomerDecision: candidateMocks.decision, previewCustomerConfirmation: candidateMocks.confirmationPreview } }));

const assignmentPlan = {
  case_no: 'CASE-001', order_version: 1, scheduling_version: 2, scheduling_generation: 2,
  client_finance_version: 1, payroll_version: 1, contracted_service_days: 2, service_hours_per_day: 8, service_started: false,
  assignments: [
    { assignment_id: 81, candidate_key: null, staff_id: 9, sequence: 1, assigned_start_date: '2026-11-01', assigned_end_date: '2026-11-01', official_service_dates: ['2026-11-01'], actual_hours: 8, lineage_source_assignment_ids: [] },
    { assignment_id: 82, candidate_key: null, staff_id: 10, sequence: 2, assigned_start_date: '2026-11-02', assigned_end_date: '2026-11-02', official_service_dates: ['2026-11-02'], actual_hours: 8, lineage_source_assignment_ids: [] },
  ],
};
const replacementQuery = {
  case_no: 'CASE-001', scenario: 'R-04', outcome: 'ready', actual_service_day_count: 0, actual_service_dates: [],
  prior_generation_identity: 'generation:2', prior_event_identity: 'event:2', prior_aggregate_identity: 'aggregate:2',
  generation_version: 2, event_version: 2, aggregate_version: 2, resume_step: 'step_2', blockers: [],
};
const replacementPreview = {
  ...replacementQuery, reason: '客戶要求換人', evidence: ['電話確認紀錄'],
  expected_generation_version: 2, expected_event_version: 2, expected_aggregate_version: 2, preview_fingerprint: 'b'.repeat(64),
};

const detail = {
  case_no: 'CASE-001',
  client: {
    client_id: 7, version: 2,
    values: { name: '王小明', gender: null, phone: '0911111111', email: 'hcm@example.com', city: '新竹市', address: null, residence_type: null, delivery_type: null, baby_info: null, notes: null },
    field_capabilities: {
      name: { owner: 'client_profile', editable: true, reason: null, options: null },
      gender: { owner: 'client_profile', editable: true, reason: null, options: ['女', '男'] },
      phone: { owner: 'client_profile', editable: true, reason: null, options: null },
      email: { owner: 'client_profile', editable: true, reason: null, options: null },
      city: { owner: 'client_profile', editable: true, reason: null, options: null },
      address: { owner: 'client_profile', editable: true, reason: null, options: null },
      residence_type: { owner: 'client_profile', editable: true, reason: null, options: ['電梯大樓', '公寓', '透天', '其他'] },
      delivery_type: { owner: 'client_profile', editable: true, reason: null, options: ['自然產', '剖腹產', '未定'] },
      baby_info: { owner: 'client_profile', editable: true, reason: null, options: null },
      notes: { owner: 'client_profile', editable: true, reason: null, options: null },
    },
  },
  beclass: {
    status: 'ready' as const, record_id: 12, source_kind: 'imported' as const, version: 3,
    values: { name: '王小明', email: 'beclass@example.com', phone: '0922222222', tel: null, ext: null, city: '新竹市', zip_code: null, address: null, admin_notes: null, multi_birth_count: '雙胞胎' },
    field_capabilities: {
      name: { owner: 'client_beclass', editable: true, reason: null, options: null },
      email: { owner: 'client_beclass', editable: true, reason: null, options: null },
      phone: { owner: 'client_beclass', editable: true, reason: null, options: null },
      tel: { owner: 'client_beclass', editable: true, reason: null, options: null },
      ext: { owner: 'client_beclass', editable: true, reason: null, options: null },
      city: { owner: 'client_beclass', editable: true, reason: null, options: null },
      zip_code: { owner: 'client_beclass', editable: true, reason: null, options: null },
      address: { owner: 'client_beclass', editable: true, reason: null, options: null },
      admin_notes: { owner: 'client_beclass', editable: true, reason: null, options: null },
      multi_birth_count: { owner: 'client_beclass', editable: true, reason: null, options: ['單胞胎', '雙胞胎'] },
    },
  },
  order_information: {
    status: 'ready' as const,
    values: {
      dietary_habits: '不吃牛肉', vegetarian_preference: null, alcohol_ratio: null,
      cooking_oil_type: null, maternal_allergy: null, special_care_notes: null,
      meal_preferences: null, cooking_tools: null, bath_water_prep: null,
      breastfeeding_method: null, holiday_pricing_terms: null, multi_birth_count: '雙胞胎',
      stair_floor_fee_mode: null, parking_space_provided: null, other_babies_present: null,
    },
    field_issues: {},
  },
  finance: { status: 'not_ready' as const, code: 'client_finance_bootstrap_required', values: null },
  order_terms: { status: 'not_ready' as const, code: 'order_terms_incomplete', data: null, field_capabilities: {} },
};

describe('Client registry owner editing', () => {
  beforeEach(() => {
    window.location.hash = '';
    Object.values(mocks).forEach((mock) => mock.mockReset());
    completionMocks.previewCompletion.mockReset().mockResolvedValue({ case_no: 'CASE-001', lifecycle_version: 0, current_status: '待補件', target_status: '洽談中', current_start_date: null, current_service_days: null, missing_fields: ['start_date', 'service_days'], blockers: [], apply_allowed: false, preview_fingerprint: 'a'.repeat(64) });
    mocks.list.mockResolvedValue({ items: [{ client_id: 7, case_no: 'CASE-001', imported_virtual_accounts: [], built_in_virtual_account: null, name: '王小明', phone: '0911111111', city: '新竹市', planned_start_date: null, order_status: 'matching' }], next_cursor: null });
    mocks.query.mockResolvedValue(detail);
    mocks.history.mockResolvedValue([]);
    Object.values(staffMocks).forEach((mock) => mock.mockReset());
    Object.values(candidateMocks).forEach((mock) => mock.mockReset());
    orderMutationFlowStore.clearAll();
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'registry-operator' } as never);
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-test-session');
    vi.spyOn(sessionClient, 'fetchCurrentUser').mockResolvedValue({ id: 1, username: 'registry-operator', display_name: 'Operator', role: 'system_admin', is_root: false, capabilities: [], access_control_version: 1 });
    candidateMocks.confirmationPreview.mockRejectedValue(new ApiHttpError(503, 'confirmation_preview_unavailable', '測試情境只驗證已人工送達後的客戶決定。'));
    candidateMocks.pool.mockResolvedValue({ pool_id: null, case_no: 'CASE-001', candidates: [] });
    candidateMocks.activePlan.mockRejectedValue(new ApiHttpError(404, 'not_found', 'no active plan'));
    staffMocks.orderDetail.mockImplementation(async (caseNo: string) => ({ case_no: caseNo, order_status: '訂單成立' }));
    staffMocks.assignment.mockResolvedValue({ ...assignmentPlan, assignments: [] });
    staffMocks.directory.mockImplementation(async ({ staffId }: { staffId: number }) => ({ items: [{ id: staffId, name: `合成月嫂 ${staffId}`, union_no: `U-${staffId}` }], next_cursor: null }));
    staffMocks.query.mockResolvedValue(replacementQuery);
    staffMocks.preview.mockResolvedValue(replacementPreview);
    staffMocks.apply.mockResolvedValue({ status: 'applied', readback: { resume_step: 'step_2', candidate_count: 0, zero_candidate_disposition: 'blocked_no_candidate' } });
    let stored = structuredClone(detail);
    mocks.query.mockImplementation(async () => structuredClone(stored));
    mocks.preview.mockImplementation(async (caseNo, target, changes, version) => ({
      owner: target === 'profile' ? 'client_profile' : 'client_beclass', aggregate_identity: caseNo,
      current_version: version, before: Object.fromEntries(Object.keys(changes).map(key => [key,
        (target === 'profile' ? stored.client.values : stored.beclass.values as Record<string, unknown>)[key as keyof typeof stored.client.values] ?? null])),
      after: changes, preview_fingerprint: 'a'.repeat(64),
    }));
    mocks.apply.mockImplementation(async (caseNo, target, changes, version, fp, _reason, key) => {
      if (target === 'profile') stored = { ...stored, client: { ...stored.client, version: version + 1, values: { ...stored.client.values, ...changes } } };
      else stored = { ...stored, beclass: { ...stored.beclass, version: version + 1, values: { ...stored.beclass.values, ...changes } },
        order_information: { ...stored.order_information, values: { ...stored.order_information.values, ...changes } } };
      return { owner: target === 'profile' ? 'client_profile' : 'client_beclass', aggregate_identity: caseNo,
        resulting_version: version + 1, changed_fields: Object.keys(changes), preview_fingerprint: fp,
        idempotency_key: key, replayed: false, readback: changes };
    });
  });

  it('reads historical staff through the canonical assignment query without a parallel source lookup', async () => {
    staffMocks.orderDetail.mockResolvedValue({ case_no: 'CASE-001', order_status: '歷史訂單－服務完成' });
    const evidence = vi.spyOn(historicalAdoptionEvidenceClient, 'queryByCase').mockRejectedValue(new Error('名冊不得另讀來源配對'));
    staffMocks.assignment.mockResolvedValue({ ...assignmentPlan, scheduling_generation: 0, assignments: [{
      assignment_id: 91, candidate_key: null, staff_id: 9, sequence: 1,
      assigned_start_date: '2026-08-01', assigned_end_date: '2026-08-30', official_service_dates: [],
      actual_hours: null, lineage_source_assignment_ids: [],
    }] });
    window.location.hash = '#clients?case=CASE-001';
    render(<ClientRegistryPage />);
    const staff = await screen.findByRole('region', { name: '服務安排與月嫂' });
    expect(await within(staff).findByText('U-9 合成月嫂 9')).toBeInTheDocument();
    expect(within(staff).getByText('2026-08-01 ～ 2026-08-30')).toBeInTheDocument();
    expect(staffMocks.assignment).toHaveBeenCalledWith('CASE-001', expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(evidence).not.toHaveBeenCalled();
    expect(within(staff).queryByText('尚未建立正式指派。')).not.toBeInTheDocument();
    expect(within(staff).queryByRole('button', { name: '選擇接任月嫂' })).not.toBeInTheDocument();
    expect(within(staff).getByText('未建立逐日排班')).toBeInTheDocument();
    expect(within(staff).queryByText('0 天')).not.toBeInTheDocument();
    evidence.mockRestore();
  });

  it('shows every effective caregiver with directory names, union numbers and service periods', async () => {
    staffMocks.assignment.mockResolvedValue(assignmentPlan);
    window.location.hash = '#clients?case=CASE-001';
    render(<ClientRegistryPage />);
    const staff = await screen.findByRole('region', { name: '服務安排與月嫂' });
    expect(await within(staff).findByText('U-9 合成月嫂 9')).toBeInTheDocument();
    expect(within(staff).getByText('U-10 合成月嫂 10')).toBeInTheDocument();
    expect(within(staff).getByText('U-9')).toBeInTheDocument();
    expect(within(staff).getByText('2026-11-02 ～ 2026-11-02')).toBeInTheDocument();
    expect(staffMocks.directory).toHaveBeenCalledTimes(2);
    expect(staffMocks.query).not.toHaveBeenCalled();
    expect(staff.nextElementSibling).toHaveAttribute('aria-label', '變更歷程');
  });

  it('keeps formal assignments visible if a staff label fails and allows a focused retry', async () => {
    staffMocks.assignment.mockResolvedValue(assignmentPlan);
    staffMocks.directory.mockRejectedValueOnce(new Error('名冊暫時無法讀取'));
    window.location.hash = '#clients?case=CASE-001';
    render(<ClientRegistryPage />);
    const staff = await screen.findByRole('region', { name: '服務安排與月嫂' });
    expect(await within(staff).findByText(/部分月嫂姓名/)).toBeInTheDocument();
    expect(within(staff).getByText('月嫂資料待確認')).toBeInTheDocument();
    expect(within(staff).getByText('U-10 合成月嫂 10')).toBeInTheDocument();
    fireEvent.click(within(staff).getByRole('button', { name: '重新讀取服務月嫂' }));
    expect(await within(staff).findByText('U-9 合成月嫂 9')).toBeInTheDocument();
  });

  it('discards late caregiver labels when switching to another case', async () => {
    let finish: ((value: unknown) => void) | undefined;
    staffMocks.assignment.mockResolvedValueOnce(assignmentPlan).mockResolvedValue({ ...assignmentPlan, case_no: 'CASE-002', assignments: [] });
    staffMocks.directory.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const first = ClientRegistryDetailSchema.parse(detail);
    const { rerender } = render(<ClientRegistryDetailEditor detail={first} onRefresh={async () => first} onStateChange={() => undefined} />);
    await waitFor(() => expect(staffMocks.directory).toHaveBeenCalledTimes(2));
    rerender(<ClientRegistryDetailEditor detail={{ ...first, case_no: 'CASE-002' }} onRefresh={async () => first} onStateChange={() => undefined} />);
    await screen.findByText('尚未建立正式指派。');
    await act(async () => { finish?.({ items: [{ id: 10, name: '上一案的晚回應', union_no: 'OLD' }], next_cursor: null }); });
    expect(screen.queryByText('上一案的晚回應')).not.toBeInTheDocument();
    expect(screen.queryByText('月嫂 #9')).not.toBeInTheDocument();
  });

  it('does not mistake an assignment query failure for no caregiver', async () => {
    staffMocks.assignment.mockRejectedValue(new Error('排班查詢失敗'));
    window.location.hash = '#clients?case=CASE-001';
    render(<ClientRegistryPage />);
    expect(await screen.findByText(/服務月嫂資料暫時無法讀取/)).toBeInTheDocument();
    expect(screen.queryByText('尚未建立正式指派。')).not.toBeInTheDocument();
  });

  it('removes the registry replacement action while retaining successor selection and service navigation', async () => {
    window.location.hash = '#clients?case=CASE-001';
    render(<ClientRegistryPage />);
    const region = await screen.findByRole('region', { name: '服務安排與月嫂' });
    expect(await within(region).findByRole('button', { name: '選擇接任月嫂' })).toBeInTheDocument();
    expect(within(region).queryByRole('button', { name: '換人' })).not.toBeInTheDocument();
    expect(within(region).getByRole('link', { name: '前往本案服務安排確認 →' })).toBeInTheDocument();
    expect(staffMocks.query).not.toHaveBeenCalled();
    expect(staffMocks.preview).not.toHaveBeenCalled();
    expect(staffMocks.apply).not.toHaveBeenCalled();
  });

  it('lets an operator select a real successor candidate, record willingness, and save the formal recommendation in the drawer', async () => {
    let added = false;
    let willing = false;
    let planExists = false;
    let accepted = false;
    const candidate = { id: 51, staff_id: 22, staff_name: '接任月嫂', status: 'active', service_start_date: '2026-11-01', service_end_date: '2026-11-02', created_at: '2026-10-13T00:00:00Z', reason: null, information: { '1': null, '2': null } };
    candidateMocks.search.mockResolvedValue({ case_no: 'CASE-001', planned_start_date: '2026-11-01', planned_end_date: '2026-11-02', conflicts: [], candidate_options: [{ segment_index: 0, staff_id: 22, staff_name: '接任月嫂', supported_day_count: 2, required_day_count: 2, matching_conditions: { region: { status: 'matched', required_value: '新竹市', staff_values: ['新竹市'] }, preferred_service_days: { status: 'matched', required_value: '週一至週五', staff_values: ['週一至週五'] } }, full_case_coverage: true, selected_segment_start: '2026-11-01', selected_segment_end: '2026-11-02' }] });
    candidateMocks.pool.mockImplementation(async () => ({ pool_id: added ? 41 : null, case_no: 'CASE-001', candidates: added ? [{ ...candidate, willingness: willing ? 'willing' : 'pending', latest_willingness_event_id: willing ? 71 : null }] : [] }));
    candidateMocks.add.mockImplementation(async () => { added = true; return { pool_id: 41, candidate_ids: [51], status: 'recorded' }; });
    candidateMocks.willingness.mockImplementation(async () => { willing = true; return { event_id: 71, status: 'recorded' }; });
    candidateMocks.activePlan.mockImplementation(async () => {
      if (!planExists) throw new ApiHttpError(404, 'not_found', 'no active plan');
      return { planId: 61, planVersion: 1, status: 'proposed', activeLockId: null, segments: [{ segmentId: 62, sequence: 1, staffId: 22, assignedStartDate: '2026-11-01', assignedEndDate: '2026-11-02' }] };
    });
    candidateMocks.contact.mockImplementation(async () => ({ plan: { id: 61, case_no: 'CASE-001', status: 'proposed', communication_version: accepted ? 2 : 1, is_active: 1 }, segments: [{ segment_id: 62, willingness: 'willing' }], all_willing: true, customer_decision: accepted ? 'accepted' : 'pending', customer_profiles_status: 'manually_confirmed' }));
    candidateMocks.createPlan.mockImplementation(async (command) => {
      planExists = true;
      return { plan_id: 61, case_no: command.caseNo, version: 1, status: 'proposed', actor: command.actor, as_of: command.asOf, event_key: command.key, segments: [{ segment_order: 1, staff_id: 22, assigned_start_date: '2026-11-01', assigned_end_date: '2026-11-02' }] };
    });
    candidateMocks.decision.mockImplementation(async () => { accepted = true; return { case_no: 'CASE-001', plan_id: 61, communication_version: 2, customer_decision: 'accepted' }; });
    mocks.query.mockImplementation(async () => structuredClone(detail));
    window.location.hash = '#clients?case=CASE-001';
    render(<ClientRegistryPage />);
    fireEvent.click(await screen.findByRole('button', { name: '選擇接任月嫂' }));
    await waitFor(() => expect(candidateMocks.search).toHaveBeenCalledOnce());
    fireEvent.click(await screen.findByRole('checkbox', { name: '選擇正式候選 接任月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '加入候選池（1）' }));
    const willingness = await screen.findByRole('button', { name: '記錄 接任月嫂 願意' });
    await waitFor(() => expect(willingness).toBeEnabled());
    fireEvent.click(willingness);
    await screen.findByText('回覆已儲存。');
    const next = screen.getByRole('button', { name: '下一步：選定推薦月嫂' });
    await waitFor(() => expect(next).toBeEnabled());
    fireEvent.click(next);
    const choose = await screen.findByRole('button', { name: '以 接任月嫂 建立正式媒合方案' });
    await waitFor(() => expect(choose).toBeEnabled());
    await act(async () => { fireEvent.click(choose); });
    fireEvent.click(await screen.findByRole('button', { name: '手動記錄客戶決定' }));
    expect(candidateMocks.createPlan).toHaveBeenCalledWith(expect.objectContaining({ caseNo: 'CASE-001', segments: [{ staff_id: 22, start_date: '2026-11-01', end_date: '2026-11-02' }] }));
    fireEvent.change(screen.getByLabelText('方案 61 客戶決策依據'), { target: { value: '電話確認客戶同意接任人選' } });
    const accept = screen.getByRole('button', { name: '記錄方案 61 客戶接受' });
    await waitFor(() => expect(accept).toBeEnabled());
    fireEvent.click(accept);
    await screen.findByText('客戶決定已完成正式回讀。');
    expect(candidateMocks.decision).toHaveBeenCalledWith('CASE-001', 61, 1, 'accepted', '電話確認客戶同意接任人選', expect.any(String), 'registry-operator');
    expect(await screen.findByText('尚未建立正式指派。')).toBeInTheDocument();
    expect(screen.getByText(/推薦方案仍須完成客戶確認、契約與排班，才會列入上方正式指派。/)).toBeInTheDocument();
    expect(window.location.hash).toBe('#clients?case=CASE-001');
  });

  it('protects the drawer and original candidate selection when adding a successor has an unknown outcome', async () => {
    candidateMocks.search.mockResolvedValue({ case_no: 'CASE-001', planned_start_date: '2026-11-01', planned_end_date: '2026-11-02', conflicts: [], candidate_options: [{ segment_index: 0, staff_id: 22, staff_name: '接任月嫂', supported_day_count: 2, required_day_count: 2, matching_conditions: { region: { status: 'matched', required_value: '新竹市', staff_values: ['新竹市'] }, preferred_service_days: { status: 'matched', required_value: '週一至週五', staff_values: ['週一至週五'] } }, full_case_coverage: true, selected_segment_start: '2026-11-01', selected_segment_end: '2026-11-02' }] });
    candidateMocks.add.mockRejectedValue(new ApiTimeoutError(10000));
    window.location.hash = '#clients?case=CASE-001';
    render(<ClientRegistryPage />);
    fireEvent.click(await screen.findByRole('button', { name: '選擇接任月嫂' }));
    await waitFor(() => expect(candidateMocks.search).toHaveBeenCalledOnce());
    fireEvent.click(await screen.findByRole('checkbox', { name: '選擇正式候選 接任月嫂' }));
    fireEvent.click(screen.getByRole('button', { name: '加入候選池（1）' }));
    const retry = await screen.findByRole('button', { name: '以原操作重新確認加入候選池' });
    expect(screen.getByRole('button', { name: '關閉案件詳細資料' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '3. 選定與確認推薦' })).toBeDisabled();
    fireEvent.click(retry);
    await waitFor(() => expect(candidateMocks.add).toHaveBeenCalledTimes(2));
    expect(candidateMocks.add.mock.calls[1][0]).toEqual(candidateMocks.add.mock.calls[0][0]);
  });

  it('keeps unknown willingness protected even if the visible candidate list later fails to reload', async () => {
    candidateMocks.pool.mockResolvedValue({ pool_id: 41, case_no: 'CASE-001', candidates: [{ id: 51, staff_id: 22, staff_name: '接任月嫂', status: 'active', willingness: 'pending', service_start_date: '2026-11-01', service_end_date: '2026-11-02', latest_willingness_event_id: null, information: { '1': null, '2': null } }] });
    candidateMocks.willingness.mockRejectedValue(new ApiTimeoutError(10000));
    window.location.hash = '#clients?case=CASE-001';
    render(<ClientRegistryPage />);
    fireEvent.click(await screen.findByRole('button', { name: '選擇接任月嫂' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '2. 確認接案意願' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '2. 確認接案意願' }));
    fireEvent.click(await screen.findByRole('button', { name: '記錄 接任月嫂 願意' }));
    await screen.findByRole('button', { name: '確認目前回覆' });
    expect(screen.getByRole('button', { name: '關閉案件詳細資料' })).toBeDisabled();
    candidateMocks.pool.mockRejectedValue(new Error('候選查詢暫時失敗'));
    fireEvent.click(screen.getByRole('button', { name: '重新讀取候選清單' }));
    await screen.findByText('候選聯絡狀態不可用');
    expect(screen.getByRole('button', { name: '關閉案件詳細資料' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '3. 選定與確認推薦' })).toBeDisabled();
  });

  it('shows separate email sources and sends each edit to its own writer', async () => {
    window.location.hash = '#clients?case=CASE-001';
    render(<ClientRegistryPage />);
    const hcm = await screen.findByLabelText('HCM Email');
    const beclass = screen.getByLabelText('BeClass Email');
    expect(hcm).toHaveValue('hcm@example.com');
    expect(beclass).toHaveValue('beclass@example.com');
    expect(hcm).toHaveAttribute('type', 'email');
    fireEvent.change(hcm, { target: { value: 'hcm-updated@example.com' } });
    fireEvent.click(within(hcm.closest('section')!).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('CASE-001', 'profile', { email: 'hcm-updated@example.com' }, 2));
    expect(beclass).toHaveValue('beclass@example.com');
    fireEvent.change(beclass, { target: { value: 'beclass-updated@example.com' } });
    fireEvent.click(within(beclass.closest('section')!).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('CASE-001', 'beclass', { email: 'beclass-updated@example.com' }, 3));
    expect(hcm).toHaveValue('hcm-updated@example.com');
  });

  it('opens an anomaly case and saves its due date and rejection reason through profile Preview/Apply', async () => {
    window.location.hash = '#clients?case=CASE-001&field=due_month';
    render(<ClientRegistryPage />);
    const due = await screen.findByLabelText('預產期／預計服務開始月份');
    expect(screen.getByRole('tab', { name: '客戶清單' })).toHaveAttribute('aria-selected', 'true');
    expect(mocks.query).toHaveBeenCalledWith('CASE-001');
    await waitFor(() => expect(due).toHaveFocus());
    fireEvent.change(due, { target: { value: '2026-10-15' } });
    fireEvent.change(screen.getByLabelText('不符合原因'), { target: { value: '服務地區不符' } });
    const profile = due.closest('section') as HTMLElement;
    fireEvent.click(within(profile).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('CASE-001', 'profile', {
      due_month: '2026-10-15', reject_reason: '服務地區不符',
    }, 2));
    expect(within(profile).queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledTimes(1));
    expect(mocks.apply.mock.calls[0][2]).toEqual({ due_month: '2026-10-15', reject_reason: '服務地區不符' });
  });

  it('ignores an older detail response after the user edits and previews the newer loaded case', async () => {
    window.location.hash = '#clients?case=CASE-001&field=reject_reason';
    const deferred: { resolve?: (value: typeof detail) => void } = {};
    mocks.query.mockImplementationOnce(() => new Promise<typeof detail>((resolve) => { deferred.resolve = resolve; }))
      .mockResolvedValueOnce(detail).mockResolvedValue({ ...detail, client: { ...detail.client, version: 3, values: { ...detail.client.values, reject_reason: '服務地區不符' } } });
    render(<StrictMode><ClientRegistryPage /></StrictMode>);
    const reason = await screen.findByLabelText('不符合原因');
    expect(mocks.query).toHaveBeenCalledTimes(2);
    fireEvent.change(reason, { target: { value: '服務地區不符' } });
    const profile = reason.closest('section') as HTMLElement;
    fireEvent.click(within(profile).getByRole('button', { name: '儲存' }));
    await screen.findByText('客戶主檔已儲存。');
    await act(async () => { deferred.resolve?.(detail); });
    expect(screen.getByLabelText('不符合原因')).toHaveValue('服務地區不符');
    expect(screen.getByText('客戶主檔已儲存。')).toBeInTheDocument();
    expect(within(profile).queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledTimes(1));
    expect(mocks.apply.mock.calls[0][2]).toEqual({ reject_reason: '服務地區不符' });
  });

  it.each(['order_terms_start_date_required', 'order_terms_service_days_required', 'order_terms_floor_fee_required'])(
    'saves only the edited profile field despite unavailable finance and incomplete terms (%s)', async (code) => {
      const incomplete = { ...detail,
        client: { ...detail.client, values: { ...detail.client.values, name: null, city: null } },
        finance: { status: 'not_ready' as const, code: 'client_finance_bootstrap_required', values: null },
        order_terms: { status: 'not_ready' as const, code, data: null, field_capabilities: {} },
      };
      mocks.query.mockResolvedValueOnce(incomplete).mockResolvedValue({ ...incomplete,
        client: { ...incomplete.client, version: 3, values: { ...incomplete.client.values, phone: '0933333333' } },
      });
      render(<ClientRegistryPage />);
        fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
      const profile = (await screen.findByRole('heading', { name: '客戶主檔' })).closest('section') as HTMLElement;
      fireEvent.change(within(profile).getByLabelText('電話（手機／市話）'), { target: { value: '0933333333' } });
      fireEvent.click(within(profile).getByRole('button', { name: '儲存' }));
      await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('CASE-001', 'profile', { phone: '0933333333' }, 2));
      expect(within(profile).queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
      await screen.findByText('客戶主檔已儲存。');
      expect(mocks.apply).toHaveBeenCalledTimes(1);
      expect(mocks.apply.mock.calls[0][2]).toEqual({ phone: '0933333333' });
      expect(within(profile).getByLabelText('電話（手機／市話）')).toHaveValue('0933333333');
    },
  );

  it('preserves and saves free-text service type through the profile editor', async () => {
    const saved = '週休1日';
    const requested = '每週依需求排班，含週末服務';
    const original = { ...detail, client: { ...detail.client,
      values: { ...detail.client.values, service_type: saved },
      field_capabilities: { ...detail.client.field_capabilities,
        service_type: { owner: 'client_profile', editable: true, reason: null, options: null } },
    } };
    mocks.query.mockResolvedValueOnce(original).mockResolvedValue({ ...original,
      client: { ...original.client, version: 3, values: { ...original.client.values, service_type: requested } },
    });
    mocks.preview.mockResolvedValue({ owner: 'client_profile', aggregate_identity: 'CASE-001', current_version: 2,
      before: { service_type: saved }, after: { service_type: requested }, preview_fingerprint: 'a'.repeat(64) });
    render(<ClientRegistryPage />);
    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
    const input = await screen.findByRole('textbox', { name: '服務方式（排班參考）' });
    expect(input).toHaveValue(saved);
    expect(input).toHaveAttribute('maxlength', '100');
    expect(screen.queryByRole('combobox', { name: '服務方式（排班參考）' })).not.toBeInTheDocument();
    const profile = input.closest('section') as HTMLElement;
    fireEvent.change(input, { target: { value: requested } });
    fireEvent.click(within(profile).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('CASE-001', 'profile', { service_type: requested }, 2));
    expect(within(profile).queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    await screen.findByText('客戶主檔已儲存。');
    expect(mocks.apply.mock.calls[0][2]).toEqual({ service_type: requested });
    expect(screen.getByRole('textbox', { name: '服務方式（排班參考）' })).toHaveValue(requested);
  });

  it.each(['週休2日', '每週依需求排班，含週末服務', null])('shows saved service type even when order terms are unavailable (%s)', async (serviceType) => {
    mocks.query.mockResolvedValue({ ...detail, service_type: serviceType });
    render(<ClientRegistryPage />);
    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
    const terms = (await screen.findByRole('heading', { name: '目前訂單條件' })).closest('section') as HTMLElement;
    expect(terms).toHaveTextContent('服務方式');
    expect(terms).toHaveTextContent(serviceType ?? '尚未登錄');
    expect(within(terms).queryByRole('combobox', { name: '服務方式（排班參考）' })).not.toBeInTheDocument();
  });

  it.each(['order_terms_start_date_required', 'order_terms_service_days_required'])(
    'offers the existing repair entry for missing terms (%s)', async (code) => {
      mocks.query.mockResolvedValue({
        ...detail,
        finance: { status: 'not_ready', code: 'unavailable', values: null },
        order_terms: { status: 'not_ready', code, data: null, field_capabilities: {} },
      });
      render(<ClientRegistryPage />);
        fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
      expect(await screen.findByRole('region', { name: '訂單缺件' })).toHaveTextContent('補齊案件資料');
      expect(screen.queryByLabelText('案件初始資料修復')).not.toBeInTheDocument();
      expect(mocks.apply).not.toHaveBeenCalled();
    },
  );

  it('lists only actual missing fields instead of treating the first error code as all missing terms', async () => {
    window.location.hash = '#clients?case=CASE-001';
    mocks.query.mockResolvedValue({ ...detail, order_terms: { ...detail.order_terms, code: 'order_terms_service_days_required' } });
    completionMocks.previewCompletion.mockResolvedValue({ case_no: 'CASE-001', lifecycle_version: 0, current_status: '待補件', target_status: '洽談中', current_start_date: '2026-11-01', current_service_days: null, missing_fields: ['service_days'], blockers: [], apply_allowed: false, preview_fingerprint: 'a'.repeat(64) });
    render(<ClientRegistryPage />);
    expect(await screen.findByText('缺少資料：服務天數')).toBeInTheDocument();
    expect(screen.getByLabelText('服務天數')).toBeInTheDocument();
    expect(screen.queryByLabelText('約定服務開始日')).not.toBeInTheDocument();
    expect(screen.queryByText('缺少欄位：約定服務開始日、服務天數。')).not.toBeInTheDocument();
    expect(mocks.apply).not.toHaveBeenCalled();
    expect(completionMocks.previewCompletion).toHaveBeenCalledWith('CASE-001', expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it('requests workbench navigation without saving or clearing the draft before the shell decides', async () => {
    window.location.hash = '#clients?case=CASE-001&from=workbench';
    render(<ClientRegistryPage />);
    const phone = await screen.findByLabelText('電話（手機／市話）');
    fireEvent.change(phone, { target: { value: '0933333333' } });
    fireEvent.click(screen.getByRole('button', { name: '返回案件處理 →' }));
    await waitFor(() => expect(window.location.hash).toBe('#order-workbench-v2?case=CASE-001'));
    expect(phone).toHaveValue('0933333333');
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('cancels without writing and applies a preview with one stable idempotency key', async () => {
    render(<ClientRegistryPage />);
    expect(screen.getByRole('tab', { name: '客戶清單' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('heading', { name: '客戶主檔' })).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '客戶清單' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
    const profile = (await screen.findByRole('heading', { name: '客戶主檔' })).closest('section') as HTMLElement;
    const phone = within(profile).getByLabelText('電話（手機／市話）');

    fireEvent.change(phone, { target: { value: '0933333333' } });
    fireEvent.click(within(profile).getByRole('button', { name: '取消變更' }));
    expect(phone).toHaveValue('0911111111');
    expect(mocks.preview).not.toHaveBeenCalled();
    expect(mocks.apply).not.toHaveBeenCalled();

    fireEvent.change(phone, { target: { value: '0933333333' } });
    fireEvent.click(within(profile).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('CASE-001', 'profile', { phone: '0933333333' }, 2));
    expect(within(profile).queryByLabelText('異動原因')).not.toBeInTheDocument();
    expect(within(profile).queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledTimes(1));
    expect(mocks.apply.mock.calls[0][5]).toBe('');
    expect(mocks.apply.mock.calls[0][6]).toMatch(/^client-profile-/);
    await screen.findByText('客戶主檔已儲存。');
  });

  it('edits a district as free-text city and saves it through profile Preview/Apply', async () => {
    mocks.query.mockResolvedValueOnce({
      ...detail, client: { ...detail.client, values: { ...detail.client.values, city: '東區' } },
    });
    mocks.preview.mockResolvedValue({
      owner: 'client_profile', aggregate_identity: 'CASE-001', current_version: 2,
      before: { city: '東區' }, after: { city: '北區' }, preview_fingerprint: 'a'.repeat(64),
    });
    mocks.query.mockResolvedValue({
      ...detail, client: { ...detail.client, version: 3, values: { ...detail.client.values, city: '北區' } },
    });
    render(<ClientRegistryPage />);
    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
    const profile = (await screen.findByRole('heading', { name: '客戶主檔' })).closest('section') as HTMLElement;
    const city = within(profile).getByRole('textbox', { name: '縣市' });
    expect(city).toHaveValue('東區');
    fireEvent.change(city, { target: { value: '北區' } });
    fireEvent.click(within(profile).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('CASE-001', 'profile', { city: '北區' }, 2));
    expect(within(profile).queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledWith(
      'CASE-001', 'profile', { city: '北區' }, 2, 'a'.repeat(64),
      '', expect.any(String),
    ));
    await screen.findByText('客戶主檔已儲存。');
    const savedProfile = screen.getByRole('heading', { name: '客戶主檔' }).closest('section') as HTMLElement;
    expect(within(savedProfile).getByRole('textbox', { name: '縣市' })).toHaveValue('北區');
  });

  it('uses selects for enum fields and keeps free-text fields as inputs', async () => {
    render(<ClientRegistryPage />);
    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));

    const profile = (await screen.findByRole('heading', { name: '客戶主檔' })).closest('section') as HTMLElement;
    expect(within(profile).getByRole('combobox', { name: '性別' })).toHaveValue('');
    expect(within(profile).getByRole('textbox', { name: '縣市' })).toHaveValue('新竹市');
    expect(within(profile).getByRole('combobox', { name: '住宅型態' })).toBeInTheDocument();
    expect(within(profile).getByRole('combobox', { name: '生產方式' })).toBeInTheDocument();
    expect(within(profile).getByRole('textbox', { name: '電話（手機／市話）' })).toBeInTheDocument();
    const beclass = (await screen.findByRole('heading', { name: '報名問卷資料（BeClass）' })).closest('section') as HTMLElement;
    const birthCount = within(beclass).getByRole('combobox', { name: '胎數（單胞胎／雙胞胎）' });
    expect(birthCount).toHaveValue('雙胞胎');
    fireEvent.change(birthCount, { target: { value: '單胞胎' } });
    fireEvent.click(within(beclass).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('CASE-001', 'beclass', { multi_birth_count: '單胞胎' }, 3));
    const information = (await screen.findByRole('heading', { name: 'BeClass 照護與特殊計費' })).closest('section') as HTMLElement;
    expect(within(information).getByText('飲食習慣與中藥接受度')).toBeInTheDocument();
    expect(within(information).getByLabelText('飲食習慣與中藥接受度')).toHaveValue('不吃牛肉');
    expect(information).not.toHaveTextContent('survey_details');
  });

  it('disables a financially locked BeClass field before it can produce a 409 preview', async () => {
    mocks.query.mockResolvedValue({
      ...detail,
      beclass: {
        ...detail.beclass,
        field_capabilities: {
          ...detail.beclass.field_capabilities,
          multi_birth_count: {
            owner: 'client_beclass', editable: false,
            reason: 'multi_birth_count_locked_after_service_start',
            options: ['單胞胎', '雙胞胎'],
          },
        },
      },
    });
    render(<ClientRegistryPage />);
    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));

    const beclass = (await screen.findByRole('heading', { name: '報名問卷資料（BeClass）' })).closest('section') as HTMLElement;
    expect(within(beclass).getByRole('combobox', { name: /胎數（單胞胎／雙胞胎）/ })).toBeDisabled();
    expect(within(beclass).getByText('服務已開始，胎數會影響費率，不能在此直接修改。')).toBeInTheDocument();
    expect(mocks.preview).not.toHaveBeenCalled();
  });

  it('shows editable blank fields for any case without imported BeClass data', async () => {
    mocks.query.mockResolvedValue({
      ...detail,
      beclass: {
        ...detail.beclass,
        record_id: null,
        source_kind: 'admin_manual',
        version: 0,
        values: Object.fromEntries(Object.keys(detail.beclass.values).map((field) => [field, null])),
      },
      order_information: {
        ...detail.order_information,
        values: Object.fromEntries(Object.keys(detail.order_information.values).map((field) => [field, null])),
      },
    });
    render(<ClientRegistryPage />);
    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));

    const beclass = (await screen.findByRole('heading', { name: '報名問卷資料（BeClass）' })).closest('section') as HTMLElement;
    expect(within(beclass).getByText('資料來源：後台人工補登（無 BeClass 匯入紀錄）')).toBeInTheDocument();
    expect(within(beclass).getByRole('textbox', { name: '報名姓名' })).toHaveValue('');
    expect(within(beclass).getByRole('combobox', { name: '胎數（單胞胎／雙胞胎）' })).toHaveValue('');
    expect(screen.queryByText(/尚未綁定 BeClass/)).not.toBeInTheDocument();
  });

  it('opens a linked case even when it is not on the current roster page', async () => {
    window.location.hash = '#clients?case=CASE-108';
    mocks.list.mockResolvedValue({ items: [], next_cursor: null, next_offset: null });
    mocks.query.mockResolvedValue({ ...detail, case_no: 'CASE-108' });
    render(<ClientRegistryPage />);
    expect(await screen.findByRole('dialog', { name: '案件 CASE-108 詳細資料' })).toBeInTheDocument();
    expect(await screen.findByLabelText('HCM Email')).toHaveValue('hcm@example.com');
    expect(mocks.query).toHaveBeenCalledWith('CASE-108');
    expect(screen.queryByRole('tab', { name: '名冊資料' })).not.toBeInTheDocument();
  });

  it('keeps virtual-account import alongside the merged client roster', () => {
    render(<ClientRegistryPage />);

    fireEvent.click(screen.getByRole('tab', { name: '虛擬帳號匯入' }));

    expect(screen.getByRole('tabpanel', { name: '虛擬帳號匯入' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '匯入舊流程虛擬帳號' })).toBeInTheDocument();
  });

  it('shows saved change reasons in chronological step order', async () => {
    mocks.history.mockResolvedValue([
      { sequence: 1, event_type: 'order_terms', label: '訂單條件變更', reason: '調整服務地址', actor: 'admin-1', occurred_at: '2026-09-20T08:00:00Z' },
      { sequence: 2, event_type: 'actual_start', label: '實際開始日確認', reason: '確認實際開始日：2026-09-22', actor: 'admin-2', occurred_at: '2026-09-22T09:30:00Z' },
    ]);
    render(<ClientRegistryPage />);

    fireEvent.click(await screen.findByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
    expect(screen.queryByRole('tab', { name: '變更歷程' })).not.toBeInTheDocument();

    await waitFor(() => expect(mocks.history).toHaveBeenCalledWith('CASE-001'));
    const historyPanel = screen.getByRole('region', { name: '變更歷程' });
    const expandable = historyPanel.querySelector('details')!;
    expect(expandable.open).toBe(false);
    fireEvent.click(historyPanel.querySelector('summary')!);
    const steps = await screen.findAllByRole('listitem');
    expect(steps[0]).toHaveTextContent('1. 訂單條件變更');
    expect(steps[0]).toHaveTextContent('調整服務地址');
    expect(steps[1]).toHaveTextContent('2. 實際開始日確認');
    expect(steps[1]).toHaveTextContent('確認實際開始日：2026-09-22');
    const history = screen.getByRole('region', { name: '變更歷程' });
    expect(history.parentElement?.lastElementChild).toBe(history);
    expect(screen.queryByLabelText('變更歷程案件編號')).not.toBeInTheDocument();
  });

  it('saves only edited care and bonus text while preserving other drafts and invalidating the shared BeClass preview', async () => {
    window.location.hash = '#clients?case=CASE-001';
    mocks.preview.mockImplementation(async (_case, _owner, changes, version) => ({ owner: 'client_beclass', aggregate_identity: 'CASE-001', current_version: version, before: {}, after: changes, preview_fingerprint: 'b'.repeat(64) }));
    render(<ClientRegistryPage />);
    const hcm = await screen.findByLabelText('HCM Email');
    fireEvent.change(hcm, { target: { value: 'unsaved@example.com' } });
    const beclass = screen.getByRole('region', { name: '報名問卷資料（BeClass）' });
    fireEvent.change(within(beclass).getByLabelText('BeClass Email'), { target: { value: 'beclass-draft@example.com' } });
    expect(within(beclass).getByRole('button', { name: '儲存' })).toBeEnabled();
    expect(mocks.preview).not.toHaveBeenCalled();
    expect(mocks.apply).not.toHaveBeenCalled();
    const care = screen.getByRole('region', { name: 'BeClass 照護與特殊計費' });
    fireEvent.change(within(care).getByLabelText('飲食習慣與中藥接受度'), { target: { value: '不吃花生' } });
    fireEvent.change(within(care).getByLabelText('三節獎金協調結果'), { target: { value: '客戶另給獎金，金額與月嫂協調' } });
    const changes = { dietary_habits: '不吃花生', holiday_pricing_terms: '客戶另給獎金，金額與月嫂協調' };
    mocks.query.mockResolvedValue({ ...detail, beclass: { ...detail.beclass, version: 4 }, order_information: { ...detail.order_information, values: { ...detail.order_information.values, ...changes } } });
    fireEvent.click(within(care).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenLastCalledWith('CASE-001', 'beclass', changes, 3));
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledOnce());
    expect(within(care).queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    await screen.findByText('BeClass 照護與特殊計費已儲存。');
    await waitFor(() => expect(mocks.history).toHaveBeenCalledTimes(2));
    expect(mocks.apply.mock.calls[0].slice(0, 4)).toEqual(['CASE-001', 'beclass', changes, 3]);
    expect(hcm).toHaveValue('unsaved@example.com');
    expect(within(beclass).getByLabelText('BeClass Email')).toHaveValue('beclass-draft@example.com');
    expect(within(beclass).getByRole('button', { name: '儲存' })).toBeEnabled();
    fireEvent.click(within(beclass).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenLastCalledWith('CASE-001', 'beclass', { email: 'beclass-draft@example.com' }, 4));
  });

  it('shows changes before discarding drafts from the drawer or tabs', async () => {
    window.location.hash = '#clients?case=CASE-001';
    render(<UnsavedChangesProvider><ClientRegistryPage /></UnsavedChangesProvider>);
    fireEvent.change(await screen.findByLabelText('行政註記'), { target: { value: '尚未儲存' } });
    fireEvent.click(screen.getByRole('button', { name: '關閉案件詳細資料' }));
    const warning = () => screen.getByRole('dialog', { name: '尚有未儲存的變更' });
    expect(within(warning()).getByRole('cell', { name: '尚未儲存' })).toBeInTheDocument();
    fireEvent.click(within(warning()).getByRole('button', { name: '繼續編輯' }));
    fireEvent.click(screen.getByRole('tab', { name: '虛擬帳號匯入' }));
    expect(warning()).toBeInTheDocument();
    fireEvent.click(within(warning()).getByRole('button', { name: '繼續編輯' }));
    expect(screen.getByLabelText('行政註記')).toHaveValue('尚未儲存');
    fireEvent.click(screen.getByRole('button', { name: '關閉案件詳細資料' }));
    fireEvent.click(within(warning()).getByRole('button', { name: '捨棄變更並離開' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it.each([false, true])('saves a client change from the warning (previous check rejected: %s)', async (previewed) => {
    let acknowledge!: () => void;
    let finishReadback!: () => void;
    const receipt = new Promise<void>(resolve => { acknowledge = resolve; });
    const readback = new Promise<void>(resolve => { finishReadback = resolve; });
    const savedDetail = { ...detail, client: { ...detail.client, version: 3,
      values: { ...detail.client.values, phone: '0933333333' } } };
    mocks.query.mockResolvedValueOnce(detail).mockImplementation(async () => { await readback; return savedDetail; });
    mocks.apply.mockReturnValue(receipt);
    window.location.hash = '#clients?case=CASE-001';
    render(<UnsavedChangesProvider><ClientRegistryPage /></UnsavedChangesProvider>);
    const phone = await screen.findByLabelText('電話（手機／市話）');
    fireEvent.change(phone, { target: { value: '0933333333' } });
    if (previewed) {
      mocks.preview.mockRejectedValueOnce(new ApiHttpError(409, 'registry_version_stale', '先前資料版本已更新'));
      fireEvent.click(within(phone.closest('section')!).getByRole('button', { name: '儲存' }));
      await screen.findByText(/先前資料版本已更新（registry_version_stale）/);
      expect(mocks.apply).not.toHaveBeenCalled();
    }
    fireEvent.click(screen.getByRole('button', { name: '關閉案件詳細資料' }));
    const warning = () => screen.getByRole('dialog', { name: '尚有未儲存的變更' });
    fireEvent.click(within(warning()).getByRole('button', { name: '儲存變更並離開' }));
    expect(phone).toBeInTheDocument();
    expect(mocks.query).toHaveBeenCalledOnce();
    await act(async () => { acknowledge(); await receipt; });
    await waitFor(() => expect(mocks.query).toHaveBeenCalledTimes(2));
    expect(phone).toBeInTheDocument();
    expect(within(warning()).getByRole('button', { name: '捨棄變更並離開' })).toBeDisabled();
    await act(async () => { finishReadback(); await readback; });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(mocks.apply).toHaveBeenCalledOnce();
    expect(mocks.preview).toHaveBeenCalledTimes(previewed ? 2 : 1);
    expect(mocks.apply.mock.calls[0].slice(0, 5)).toEqual(['CASE-001', 'profile', { phone: '0933333333' }, 2, 'a'.repeat(64)]);
    fireEvent.click(screen.getByRole('row', { name: '開啟案件 CASE-001 詳細資料' }));
    expect(await screen.findByLabelText('電話（手機／市話）')).toHaveValue('0933333333');
  });

  it('does not apply or leave when the warning-triggered backend preview rejects the changes', async () => {
    mocks.preview.mockRejectedValue(new ApiHttpError(422, 'invalid_phone', '電話格式不符'));
    window.location.hash = '#clients?case=CASE-001';
    render(<UnsavedChangesProvider><ClientRegistryPage /></UnsavedChangesProvider>);
    const phone = await screen.findByLabelText('電話（手機／市話）');
    fireEvent.change(phone, { target: { value: '0933333333' } });
    fireEvent.click(screen.getByRole('button', { name: '關閉案件詳細資料' }));
    const warning = screen.getByRole('dialog', { name: '尚有未儲存的變更' });
    fireEvent.click(within(warning).getByRole('button', { name: '儲存變更並離開' }));
    await screen.findByText(/電話格式不符/);
    expect(mocks.apply).not.toHaveBeenCalled();
    expect(phone).toHaveValue('0933333333');
    expect(warning).toBeInTheDocument();
  });

  it('saves questionnaire and care changes using the fresh shared owner version between writes', async () => {
    let stored = structuredClone(detail);
    mocks.query.mockImplementation(async () => structuredClone(stored));
    mocks.preview.mockImplementation(async (_caseNo, _owner, changes, version) => ({
      owner: 'client_beclass', aggregate_identity: 'CASE-001', current_version: version,
      before: {}, after: changes, preview_fingerprint: 'b'.repeat(64),
    }));
    mocks.apply.mockImplementation(async (_caseNo, _owner, changes) => {
      stored.beclass.version += 1;
      if ('email' in changes) Object.assign(stored.beclass.values, changes);
      else Object.assign(stored.order_information.values, changes);
      return {};
    });
    window.location.hash = '#clients?case=CASE-001';
    render(<UnsavedChangesProvider><ClientRegistryPage /></UnsavedChangesProvider>);
    fireEvent.change(await screen.findByLabelText('BeClass Email'), { target: { value: 'synthetic@example.test' } });
    fireEvent.change(screen.getByLabelText('飲食習慣與中藥接受度'), { target: { value: '合成測試變更' } });
    fireEvent.click(screen.getByRole('button', { name: '關閉案件詳細資料' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: '尚有未儲存的變更' })).getByRole('button', { name: '儲存變更並離開' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(mocks.apply).toHaveBeenCalledTimes(2);
    expect(mocks.preview.mock.calls.map(call => call[3])).toEqual([3, 4]);
    expect(mocks.apply.mock.calls.map(call => call[3])).toEqual([3, 4]);
    expect(stored.beclass.values.email).toBe('synthetic@example.test');
    expect(stored.order_information.values.dietary_habits).toBe('合成測試變更');
  });

  it('locks closing during Apply and retries only readback after confirmed commit', async () => {
    window.location.hash = '#clients?case=CASE-001';
    let finish: (() => void) | undefined;
    mocks.apply.mockImplementation(() => new Promise<void>((resolve) => { finish = resolve; }));
    render(<ClientRegistryPage />);
    const phone = await screen.findByLabelText('電話（手機／市話）');
    fireEvent.change(phone, { target: { value: '0933333333' } });
    const profile = phone.closest('section')!;
    fireEvent.click(within(profile).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledOnce());
    expect(within(profile).getByRole('button', { name: '儲存' })).toBeDisabled();
    mocks.query.mockRejectedValueOnce(new Error('讀取暫時失敗'));
    expect(within(profile).queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '關閉案件詳細資料' })).toBeDisabled();
    await act(async () => { finish?.(); });
    expect(await screen.findByText(/已儲存，但最新資料讀取失敗/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '關閉案件詳細資料' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '重新讀取已儲存資料' }));
    await screen.findByText('客戶主檔已儲存。');
    expect(mocks.apply).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByRole('button', { name: '關閉案件詳細資料' })).toBeEnabled());
  });

  it('keeps an unknown Apply outcome open and confirms it with the same idempotency key', async () => {
    window.location.hash = '#clients?case=CASE-001';
    mocks.apply.mockRejectedValueOnce(new Error('連線中斷'));
    render(<ClientRegistryPage />);
    const phone = await screen.findByLabelText('電話（手機／市話）');
    fireEvent.change(phone, { target: { value: '0933333333' } });
    const profile = phone.closest('section')!;
    fireEvent.click(within(profile).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledOnce());
    expect(within(profile).getByRole('button', { name: '儲存' })).toBeDisabled();
    expect(within(profile).queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    await screen.findByRole('button', { name: '確認同一筆儲存結果' });
    expect(screen.getByRole('button', { name: '關閉案件詳細資料' })).toBeDisabled();
    mocks.query.mockRejectedValueOnce(new Error('回讀中斷'));
    fireEvent.click(screen.getByRole('button', { name: '確認同一筆儲存結果' }));
    await screen.findByRole('button', { name: '重新讀取已儲存資料' });
    expect(screen.queryByRole('button', { name: '確認同一筆儲存結果' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新讀取已儲存資料' }));
    await screen.findByText('客戶主檔已儲存。');
    expect(mocks.apply.mock.calls[0]).toEqual(mocks.apply.mock.calls[1]);
    expect(mocks.preview).toHaveBeenCalledTimes(1);
  });

  it('keeps the operation busy when a new owner version renders before readback finishes', async () => {
    let finish: (() => void) | undefined;
    const editState = vi.fn();
    function Harness() {
      const [current, setCurrent] = useState(() => ClientRegistryDetailSchema.parse(detail));
      const refresh = async () => {
        const updated = { ...current, client: { ...current.client, version: 3, values: { ...current.client.values, phone: '0933333333' } } };
        setCurrent(updated);
        await new Promise<void>((resolve) => { finish = resolve; });
        return updated;
      };
      return <ClientRegistryDetailEditor detail={current} onRefresh={refresh} onStateChange={editState} />;
    }
    render(<Harness />);
    const phone = screen.getByLabelText('電話（手機／市話）');
    const profile = phone.closest('section')!;
    fireEvent.change(phone, { target: { value: '0933333333' } });
    fireEvent.click(within(profile).getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledOnce());
    expect(within(profile).getByRole('button', { name: '儲存' })).toBeDisabled();
    expect(within(profile).queryByRole('button', { name: '確認儲存' })).not.toBeInTheDocument();
    await waitFor(() => expect(finish).toBeDefined());
    expect(editState).toHaveBeenLastCalledWith(expect.objectContaining({ busy: true }));
    await act(async () => { finish?.(); });
    await screen.findByText('客戶主檔已儲存。');
    await waitFor(() => expect(editState).toHaveBeenLastCalledWith({ dirty: false, busy: false }));
    expect(phone).toHaveValue('0933333333');
  });

  it('retries drawer history independently while preserving the profile draft', async () => {
    window.location.hash = '#clients?case=CASE-001';
    mocks.history.mockRejectedValueOnce(new Error('歷程暫時無法讀取')).mockResolvedValue([
      { sequence: 1, event_type: 'client_profile', label: '客戶資料修正', reason: '已核對電話', actor: 'admin-1', occurred_at: '2026-10-13T08:00:00Z' },
    ]);
    render(<ClientRegistryPage />);
    const notes = await screen.findByLabelText('行政註記');
    fireEvent.change(notes, { target: { value: '尚未儲存的草稿' } });
    fireEvent.click(screen.getByRole('region', { name: '變更歷程' }).querySelector('summary')!);
    const retryHistory = await screen.findByRole('button', { name: '重新讀取變更歷程' });
    await waitFor(() => expect(retryHistory).toBeEnabled());
    fireEvent.click(retryHistory);
    await screen.findByText('已核對電話');
    expect(notes).toHaveValue('尚未儲存的草稿');
    expect(mocks.history.mock.calls).toEqual([['CASE-001'], ['CASE-001']]);
    expect(mocks.apply).not.toHaveBeenCalled();
    expect(mocks.preview).not.toHaveBeenCalled();
  });

  it('keeps a previous case history response out of the newly selected case', async () => {
    let finish: ((value: unknown[]) => void) | undefined;
    mocks.history.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; })).mockResolvedValue([
      { sequence: 1, event_type: 'client_profile', label: '客戶資料修正', reason: '第二案紀錄', actor: 'admin-2', occurred_at: '2026-10-13T08:00:00Z' },
    ]);
    const first = ClientRegistryDetailSchema.parse(detail);
    const second = { ...first, case_no: 'CASE-002' };
    const { rerender } = render(<ClientRegistryDetailEditor key="CASE-001" detail={first} onRefresh={async () => first} onStateChange={() => undefined} />);
    await waitFor(() => expect(mocks.history).toHaveBeenCalledWith('CASE-001'));
    expect(screen.getByText('正在載入變更歷程…')).toBeInTheDocument();
    rerender(<ClientRegistryDetailEditor key="CASE-002" detail={second} onRefresh={async () => second} onStateChange={() => undefined} />);
    await screen.findByText('第二案紀錄');
    await act(async () => { finish?.([{ sequence: 1, event_type: 'client_profile', label: '客戶資料修正', reason: '第一案晚回應', actor: 'admin-1', occurred_at: '2026-10-13T08:00:00Z' }]); });
    expect(screen.queryByText('第一案晚回應')).not.toBeInTheDocument();
    expect(screen.getByText('第二案紀錄')).toBeInTheDocument();
  });
});
