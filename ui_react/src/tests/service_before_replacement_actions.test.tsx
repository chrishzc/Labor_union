/**
 * File: service_before_replacement_actions.test.tsx
 * Description: 驗證 RPRE 明確情境、完整 fingerprint、Apply fresh readback、實際服務轉介與同鍵結果對帳。
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  decodeAndVerifyServiceBeforeReplacementApplyResponse,
  serviceBeforeReplacementActorBinding,
  ServiceBeforeReplacementApplyRequestSchema,
  ServiceBeforeReplacementQuerySchema,
  serviceBeforeReplacementClient,
  verifyServiceBeforeReplacementApply,
  verifyServiceBeforeReplacementPreview,
  verifyServiceBeforeReplacementQuery,
  type ServiceBeforeReplacementApplyResult,
  type ServiceBeforeReplacementPreview,
  type ServiceBeforeReplacementQuery,
} from '../api/orders/service_before_replacement_client';
import { ApiHttpError, ApiTimeoutError } from '../api/shared/typed_errors';
import { ServiceBeforeReplacementActions } from '../components/ServiceBeforeReplacementActions';

vi.mock('../api/orders/service_before_replacement_client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/orders/service_before_replacement_client')>();
  return {
    ...original,
    createServiceBeforeReplacementCommandIdentity: vi.fn(() => ({
      idempotencyKey: 'service-before-replacement:fixed-command',
      correlationId: 'service-before-replacement-fixed-correlation',
    })),
    serviceBeforeReplacementClient: {
      query: vi.fn(),
      preview: vi.fn(),
      apply: vi.fn(),
    },
  };
});

const fingerprint = 'a'.repeat(64);

type CanonicalValue = null | boolean | number | string | readonly CanonicalValue[] | { readonly [key: string]: CanonicalValue };

function canonicalJson(value: CanonicalValue): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'number' || typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  const mapping = value as { readonly [key: string]: CanonicalValue };
  return `{${Object.keys(mapping).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(mapping[key])}`).join(',')}}`;
}

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((item) => item.toString(16).padStart(2, '0')).join('');
}

async function payloadFingerprint(value: { readonly [key: string]: CanonicalValue }): Promise<string> {
  return sha256(canonicalJson(value));
}
const zeroServiceProof = {
  case_no: 'CASE-RPRE-001',
  service_dates: [],
  source_identity: 'official-schedule:CASE-RPRE-001',
  source_version: 7,
  fingerprint,
};
const supersededRoot = {
  kind: 'matching_plan' as const,
  root_id: 'matching-plan:11',
  case_no: 'CASE-RPRE-001',
  current: true,
  caregiver_bound: true,
};
const retainedRoot = {
  kind: 'recipient_confirmation' as const,
  root_id: 'recipient-confirmation:12',
  case_no: 'CASE-RPRE-001',
  current: false,
  caregiver_bound: true,
};
const createdRoot = {
  kind: 'successor_round' as const,
  root_id: 'successor-round:22',
  case_no: 'CASE-RPRE-001',
  current: true,
  caregiver_bound: false,
};

const readyQuery: ServiceBeforeReplacementQuery = {
  case_no: 'CASE-RPRE-001',
  scenario: 'R-02',
  outcome: 'ready',
  actual_service_day_count: 0,
  actual_service_dates: [],
  actual_service_proof: zeroServiceProof,
  prior_generation_identity: 'generation:7',
  prior_event_identity: 'event:7',
  prior_aggregate_identity: 'aggregate:7',
  generation_version: 7,
  event_version: 7,
  aggregate_version: 7,
  impacted_roots: [supersededRoot],
  retained_roots: [retainedRoot],
  root_delta: { retained: [retainedRoot], superseded: [supersededRoot], created: [] },
  candidate_pool_reuse_proof: null,
  successor_round: null,
  matching_zero_candidate_proof: null,
  resume_step: 'step_2',
  blockers: [],
};

const preview: ServiceBeforeReplacementPreview = {
  ...readyQuery,
  replacement_generation_identity: 'generation:8',
  replacement_event_identity: 'event:8',
  successor_round_identity: 'round:8',
  expected_generation_version: 7,
  resulting_generation_version: 8,
  expected_event_version: 7,
  resulting_event_version: 8,
  expected_aggregate_version: 7,
  resulting_aggregate_version: 8,
  root_delta: { retained: [retainedRoot], superseded: [supersededRoot], created: [createdRoot] },
  superseded_roots: [supersededRoot],
  created_roots: [createdRoot],
  preview_fingerprint: fingerprint,
  reason: '客戶要求更換月嫂',
  evidence: ['call-log:20260828', 'ticket:RPRE-1'],
  projection_kind: 'successor_matching',
};

const result: ServiceBeforeReplacementApplyResult = {
  status: 'applied',
  receipt: {
    case_no: 'CASE-RPRE-001',
    receipt_identity: 'receipt:8',
    idempotency_key: 'service-before-replacement:fixed-command',
    command_fingerprint: fingerprint,
    preview_fingerprint: fingerprint,
    replacement_generation_identity: 'generation:8',
    replacement_event_identity: 'event:8',
    successor_round_identity: 'round:8',
    resulting_generation_version: 8,
    resulting_event_version: 8,
    resulting_aggregate_version: 8,
    outbox_identity: 'outbox:8',
    retained_root_ids: [retainedRoot.root_id],
    superseded_root_ids: [supersededRoot.root_id],
    created_root_ids: [createdRoot.root_id],
    retained_root_set_digest: fingerprint,
    retained_root_count: 1,
    superseded_root_set_digest: fingerprint,
    superseded_root_count: 1,
    created_root_set_digest: fingerprint,
    created_root_count: 1,
    matching_package_lineage_id: 8,
    matching_event_id: 9,
  },
  readback: {
    case_no: 'CASE-RPRE-001',
    generation_identity: 'generation:8',
    event_identity: 'event:8',
    successor_round_identity: 'round:8',
    generation_version: 8,
    event_version: 8,
    aggregate_version: 8,
    retained_root_ids: [retainedRoot.root_id],
    superseded_root_ids: [supersededRoot.root_id],
    created_root_ids: [createdRoot.root_id],
    root_set_digests: [fingerprint, fingerprint, fingerprint],
    root_set_counts: [1, 1, 1],
    resume_step: 'step_4',
    candidate_count: 1,
    zero_candidate_disposition: null,
    outbox_identity: 'outbox:8',
    matching_package_lineage_id: 8,
    matching_event_id: 9,
    complete: true,
  },
};

describe('ServiceBeforeReplacementActions', () => {
  beforeEach(() => {
    vi.mocked(serviceBeforeReplacementClient.query).mockResolvedValue(readyQuery);
    vi.mocked(serviceBeforeReplacementClient.preview).mockResolvedValue(preview);
    vi.mocked(serviceBeforeReplacementClient.apply).mockResolvedValue(result);
  });

  it('要求明確情境、原因與證據，並只套用後端決定的 resume step', async () => {
    const onCommitted = vi.fn();
    render(<ServiceBeforeReplacementActions caseNo="CASE-RPRE-001" initialScenario="R-02" onCommitted={onCommitted} />);

    await screen.findByText('可以建立換人 successor');
    expect(serviceBeforeReplacementClient.query).toHaveBeenCalledWith('CASE-RPRE-001', 'R-02', expect.any(AbortSignal));
    expect(screen.getByText('步驟 2：重新建立候選池')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('換人原因'), { target: { value: ' 客戶要求更換月嫂 ' } });
    fireEvent.change(screen.getByLabelText('證據（每行一筆）'), { target: { value: 'ticket:RPRE-1\ncall-log:20260828\nticket:RPRE-1' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽換人影響' }));

    await screen.findByText('預覽完成，尚未寫入');
    expect(screen.getByText(`Preview fingerprint`)).toBeInTheDocument();
    expect(screen.getByText(fingerprint)).toBeInTheDocument();
    expect(screen.getByText(/generation:7.*event:7.*aggregate:7/)).toBeInTheDocument();
    expect(screen.getByText(/generation:8.*event:8/)).toBeInTheDocument();
    expect(screen.getAllByText('expected 7／resulting 8')).toHaveLength(3);
    expect(screen.getByText('successor_matching')).toBeInTheDocument();
    expect(screen.getByText(/matching_plan.*matching-plan:11.*current true.*caregiver-bound true/)).toBeInTheDocument();
    expect(screen.getByText(/recipient_confirmation.*recipient-confirmation:12.*current false.*caregiver-bound true/)).toBeInTheDocument();
    expect(screen.getByText(/successor_round.*successor-round:22.*current true.*caregiver-bound false/)).toBeInTheDocument();
    expect(screen.getByText(/Actual-service proof：official-schedule:CASE-RPRE-001，版本 7/)).toBeInTheDocument();
    expect(screen.getByText('Candidate reuse proof：無')).toBeInTheDocument();
    expect(screen.getByText('Successor proof：無')).toBeInTheDocument();
    expect(serviceBeforeReplacementClient.preview).toHaveBeenCalledWith(
      'CASE-RPRE-001',
      {
        scenario: 'R-02',
        reason: '客戶要求更換月嫂',
        evidence: ['call-log:20260828', 'ticket:RPRE-1'],
      },
      expect.any(AbortSignal),
    );
    const applyButton = screen.getByRole('button', { name: '確認建立換人 successor' });
    expect(applyButton).toBeDisabled();
    fireEvent.click(screen.getByLabelText('我已核對案件、情境、原因、證據與影響範圍'));
    fireEvent.click(applyButton);

    await screen.findByText(/已完成 owner readback/);
    expect(serviceBeforeReplacementClient.apply).toHaveBeenCalledWith(
      'CASE-RPRE-001',
      expect.objectContaining({
        scenario: 'R-02',
        expected_generation_version: 7,
        expected_event_version: 7,
        expected_aggregate_version: 7,
        preview_fingerprint: fingerprint,
      }),
      {
        idempotencyKey: 'service-before-replacement:fixed-command',
        correlationId: 'service-before-replacement-fixed-correlation',
      },
      expect.any(AbortSignal),
    );
    expect(onCommitted).toHaveBeenCalledWith(result);
    expect(serviceBeforeReplacementClient.query).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText(`digest：${fingerprint}`)).toHaveLength(3);
  });

  it('實際服務存在時只顯示請假代班轉介，不顯示 replacement 操作', async () => {
    const referral: ServiceBeforeReplacementQuery = {
      ...readyQuery,
      scenario: 'R-04',
      outcome: 'substitution_referral',
      actual_service_day_count: 1,
      actual_service_dates: ['2026-08-01'],
      actual_service_proof: { ...zeroServiceProof, service_dates: ['2026-08-01'] },
      impacted_roots: [],
      retained_roots: [],
      root_delta: null,
      blockers: ['replacement_actual_service_exists'],
    };
    const onSubstitutionReferral = vi.fn();
    vi.mocked(serviceBeforeReplacementClient.query).mockResolvedValue(referral);
    render(<ServiceBeforeReplacementActions caseNo="CASE-RPRE-001" initialScenario="R-04" onSubstitutionReferral={onSubstitutionReferral} />);

    await screen.findByText('已有實際服務，必須改走請假代班');
    expect(screen.queryByLabelText('換人原因')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '前往請假代班' }));
    expect(onSubstitutionReferral).toHaveBeenCalledWith(referral);
    expect(screen.getByText(/official-schedule:CASE-RPRE-001，版本 7/)).toBeInTheDocument();
  });

  it('沒有 typed anomaly binding 時不預設猜 R-01，必須由操作者選擇', async () => {
    render(<ServiceBeforeReplacementActions caseNo="CASE-RPRE-001" />);
    await screen.findByText(/系統不會猜測 R-01/);
    expect(serviceBeforeReplacementClient.query).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('異常情境'), { target: { value: 'R-03' } });
    await screen.findByText('可以建立換人 successor');
    expect(serviceBeforeReplacementClient.query).toHaveBeenCalledWith('CASE-RPRE-001', 'R-03', expect.any(AbortSignal));
  });

  it('Apply 結果未明時只使用原 payload 與原 key 對帳，不建立新命令', async () => {
    vi.mocked(serviceBeforeReplacementClient.apply)
      .mockRejectedValueOnce(new ApiTimeoutError(10_000))
      .mockResolvedValueOnce({ ...result, status: 'replayed' });
    render(<ServiceBeforeReplacementActions caseNo="CASE-RPRE-001" initialScenario="R-02" />);
    await screen.findByText('可以建立換人 successor');
    fireEvent.change(screen.getByLabelText('換人原因'), { target: { value: preview.reason } });
    fireEvent.change(screen.getByLabelText('證據（每行一筆）'), { target: { value: preview.evidence.join('\n') } });
    fireEvent.click(screen.getByRole('button', { name: '預覽換人影響' }));
    await screen.findByText('預覽完成，尚未寫入');
    fireEvent.click(screen.getByLabelText('我已核對案件、情境、原因、證據與影響範圍'));
    fireEvent.click(screen.getByRole('button', { name: '確認建立換人 successor' }));

    await screen.findByText(/只能用原內容與原 Idempotency-Key 對帳/);
    const firstCall = vi.mocked(serviceBeforeReplacementClient.apply).mock.calls[0];
    fireEvent.click(screen.getByRole('button', { name: '以原命令對帳 receipt／readback' }));
    await screen.findByText(/既有結果已對帳/);
    const secondCall = vi.mocked(serviceBeforeReplacementClient.apply).mock.calls[1];
    expect(secondCall[1]).toEqual(firstCall[1]);
    expect(secondCall[2]).toBe(firstCall[2]);
  });

  it('切換案件會中止舊 Query，舊回應不得覆蓋新案件', async () => {
    let resolveOld: ((value: ServiceBeforeReplacementQuery) => void) | undefined;
    const oldQuery = new Promise<ServiceBeforeReplacementQuery>((resolve) => { resolveOld = resolve; });
    vi.mocked(serviceBeforeReplacementClient.query)
      .mockReturnValueOnce(oldQuery)
      .mockResolvedValueOnce({ ...readyQuery, case_no: 'CASE-RPRE-002', resume_step: 'step_4', actual_service_proof: { ...zeroServiceProof, case_no: 'CASE-RPRE-002', source_identity: 'official-schedule:CASE-RPRE-002' }, impacted_roots: [{ ...supersededRoot, case_no: 'CASE-RPRE-002' }], retained_roots: [{ ...retainedRoot, case_no: 'CASE-RPRE-002' }], root_delta: { retained: [{ ...retainedRoot, case_no: 'CASE-RPRE-002' }], superseded: [{ ...supersededRoot, case_no: 'CASE-RPRE-002' }], created: [] } });
    const view = render(<ServiceBeforeReplacementActions caseNo="CASE-RPRE-001" initialScenario="R-02" />);
    await waitForQueryCallCount(1);
    const oldSignal = vi.mocked(serviceBeforeReplacementClient.query).mock.calls[0][2];
    view.rerender(<ServiceBeforeReplacementActions caseNo="CASE-RPRE-002" initialScenario="R-02" />);
    await screen.findByText('步驟 4：沿用已驗證接受結果');
    expect(oldSignal?.aborted).toBe(true);
    resolveOld?.(readyQuery);
    await Promise.resolve();
    expect(screen.getByText('步驟 4：沿用已驗證接受結果')).toBeInTheDocument();
    expect(screen.queryByText('步驟 2：重新建立候選池')).not.toBeInTheDocument();
  });

  it('owner refresh callback 失敗不會把已完成的 Apply 誤報為失敗', async () => {
    const onCommitted = vi.fn().mockRejectedValue(new Error('parent refresh failed'));
    render(<ServiceBeforeReplacementActions caseNo="CASE-RPRE-001" initialScenario="R-02" onCommitted={onCommitted} />);
    await screen.findByText('可以建立換人 successor');
    fireEvent.change(screen.getByLabelText('換人原因'), { target: { value: preview.reason } });
    fireEvent.change(screen.getByLabelText('證據（每行一筆）'), { target: { value: preview.evidence.join('\n') } });
    fireEvent.click(screen.getByRole('button', { name: '預覽換人影響' }));
    await screen.findByText('預覽完成，尚未寫入');
    fireEvent.click(screen.getByLabelText('我已核對案件、情境、原因、證據與影響範圍'));
    fireEvent.click(screen.getByRole('button', { name: '確認建立換人 successor' }));
    await screen.findByText(/已完成 owner readback/);
    expect(screen.queryByText('parent refresh failed')).not.toBeInTheDocument();
  });

  it('Apply 後以 response 內 complete readback 顯示結果，不重查已消耗的舊 scenario', async () => {
    render(<ServiceBeforeReplacementActions caseNo="CASE-RPRE-001" initialScenario="R-02" />);
    await screen.findByText('可以建立換人 successor');
    fireEvent.change(screen.getByLabelText('換人原因'), { target: { value: preview.reason } });
    fireEvent.change(screen.getByLabelText('證據（每行一筆）'), { target: { value: preview.evidence.join('\n') } });
    fireEvent.click(screen.getByRole('button', { name: '預覽換人影響' }));
    await screen.findByText('預覽完成，尚未寫入');
    fireEvent.click(screen.getByLabelText('我已核對案件、情境、原因、證據與影響範圍'));
    fireEvent.click(screen.getByRole('button', { name: '確認建立換人 successor' }));
    await screen.findByText(/後端完成 post-commit owner readback/);
    expect(serviceBeforeReplacementClient.query).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Apply readback 未提供 occurrence active 欄位/)).toBeInTheDocument();
    expect(screen.getByText('Readback complete：true')).toBeInTheDocument();
  });

  it('R-07 Apply readback 明確顯示停在 Step 2 且沒有候選，不誤報異常已解除', async () => {
    vi.mocked(serviceBeforeReplacementClient.query).mockResolvedValue({ ...readyQuery, scenario: 'R-07' });
    vi.mocked(serviceBeforeReplacementClient.preview).mockResolvedValue({ ...preview, scenario: 'R-07' });
    vi.mocked(serviceBeforeReplacementClient.apply).mockResolvedValue({
      ...result,
      readback: {
        ...result.readback,
        resume_step: 'step_2',
        candidate_count: 0,
        zero_candidate_disposition: 'blocked_no_candidate',
      },
    });
    render(<ServiceBeforeReplacementActions caseNo="CASE-RPRE-001" initialScenario="R-07" />);
    await screen.findByText('可以建立換人 successor');
    fireEvent.change(screen.getByLabelText('換人原因'), { target: { value: preview.reason } });
    fireEvent.change(screen.getByLabelText('證據（每行一筆）'), { target: { value: preview.evidence.join('\n') } });
    fireEvent.click(screen.getByRole('button', { name: '預覽換人影響' }));
    await screen.findByText('預覽完成，尚未寫入');
    fireEvent.click(screen.getByLabelText('我已核對案件、情境、原因、證據與影響範圍'));
    fireEvent.click(screen.getByRole('button', { name: '確認建立換人 successor' }));

    await screen.findByText(/目前仍停在 Step 2：沒有可用候選/);
    expect(screen.getByText(/blocked_no_candidate/)).toBeInTheDocument();
    expect(screen.getByText(/不代表異常已解除，也不會復活舊月嫂/)).toBeInTheDocument();
    expect(screen.getByText(/Successor 候選數：.*0/)).toBeInTheDocument();
    expect(serviceBeforeReplacementClient.query).toHaveBeenCalledTimes(1);
  });
});

async function waitForQueryCallCount(count: number): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (vi.mocked(serviceBeforeReplacementClient.query).mock.calls.length >= count) return;
    await Promise.resolve();
  }
  throw new Error(`query call count did not reach ${count}`);
}

describe('ServiceBeforeReplacementQuerySchema', () => {
  it('拒絕跨案件 roots 與 referral 混入 replacement facts', () => {
    expect(ServiceBeforeReplacementQuerySchema.safeParse({
      ...readyQuery,
      impacted_roots: [{ ...supersededRoot, case_no: 'CASE-OTHER' }],
    }).success).toBe(false);
    expect(ServiceBeforeReplacementQuerySchema.safeParse({
      ...readyQuery,
      outcome: 'substitution_referral',
      actual_service_day_count: 1,
      actual_service_dates: ['2026-08-01'],
      actual_service_proof: { ...zeroServiceProof, service_dates: ['2026-08-01'] },
    }).success).toBe(false);
  });

  it('referral 有服務日卻缺 proof 時 fail closed', () => {
    expect(ServiceBeforeReplacementQuerySchema.safeParse({
      ...readyQuery,
      outcome: 'substitution_referral',
      actual_service_day_count: 1,
      actual_service_dates: ['2026-08-01'],
      actual_service_proof: null,
      impacted_roots: [],
      retained_roots: [],
      root_delta: null,
    }).success).toBe(false);
  });
});

describe('ServiceBeforeReplacementApplyRequestSchema', () => {
  it('接受完整 Preview 綁定欄位並維持 strict contract', () => {
    const request = {
      scenario: preview.scenario,
      reason: preview.reason,
      evidence: preview.evidence,
      expected_generation_version: 7,
      expected_event_version: 7,
      expected_aggregate_version: 7,
      prior_generation_identity: 'generation:7',
      prior_event_identity: 'event:7',
      prior_aggregate_identity: 'aggregate:7',
      preview_fingerprint: fingerprint,
    };
    expect(ServiceBeforeReplacementApplyRequestSchema.safeParse(request).success).toBe(true);
    expect(ServiceBeforeReplacementApplyRequestSchema.safeParse({ ...request, extra: true }).success).toBe(false);
  });
});

describe('RPRE cryptographic response verification', () => {
  it('no-auth development principal 使用與 server 相同的 immutable actor identity', () => {
    expect(serviceBeforeReplacementActorBinding({
      id: null,
      username: 'development-bypass',
      role: 'system_admin',
    })).toEqual({
      actor: 'system:local_bypass',
      capabilities: ['orders.historical_review.remediate'],
    });
    expect(serviceBeforeReplacementActorBinding({
      id: 42,
      username: 'operator',
      role: 'system_admin',
    }).actor).toBe('admin:42');
  });

  it('Apply transport 成功後若 response 無法解碼，一律轉成同鍵 outcome_unknown', async () => {
    const request = {
      scenario: preview.scenario,
      reason: preview.reason,
      evidence: preview.evidence,
      expected_generation_version: 7,
      expected_event_version: 7,
      expected_aggregate_version: 7,
      prior_generation_identity: 'generation:7',
      prior_event_identity: 'event:7',
      prior_aggregate_identity: 'aggregate:7',
      preview_fingerprint: fingerprint,
    } as const;
    const identity = {
      idempotencyKey: 'service-before-replacement:fixed-command',
      correlationId: 'service-before-replacement-fixed-correlation',
    };
    const actor = { actor: 'admin:development', capabilities: ['orders.historical_review.remediate'] } as const;

    const decodeFailure = await decodeAndVerifyServiceBeforeReplacementApplyResponse(
      { success: true, message: 'ok', data: {}, error: null },
      preview.case_no,
      request,
      identity,
      actor,
    ).catch((error: unknown) => error);
    expect(decodeFailure).toBeInstanceOf(ApiHttpError);
    expect(decodeFailure).toMatchObject({
      status: 503,
      code: 'replacement_outcome_unknown',
      retryable: true,
    });

    const verificationFailure = await decodeAndVerifyServiceBeforeReplacementApplyResponse(
      { success: true, message: 'ok', data: result, error: null },
      preview.case_no,
      request,
      identity,
      actor,
    ).catch((error: unknown) => error);
    expect(verificationFailure).toBeInstanceOf(ApiHttpError);
    expect(verificationFailure).toMatchObject({ code: 'replacement_outcome_unknown', retryable: true });
  });

  it('重算 actual-service、reuse 與 successor canonical fingerprints，拒絕格式正確的偽造 digest', async () => {
    const proofFingerprint = await payloadFingerprint({
      kind: 'authoritative-actual-service-proof', case_no: zeroServiceProof.case_no,
      service_dates: [], source_identity: zeroServiceProof.source_identity, source_version: zeroServiceProof.source_version,
    });
    expect(proofFingerprint).toBe('f879e24d639b15776eb3acb1df640fc875f4d391f2acbfd164775191ec370d95');
    const successorBase = {
      case_no: readyQuery.case_no,
      round_identity: 'round:8', generation_identity: 'generation:8', event_identity: 'event:8',
      generation_version: 8, event_version: 8, candidate_count: 1, zero_candidate_disposition: null,
    };
    const successorFingerprint = await payloadFingerprint({ kind: 'successor-round', ...successorBase });
    expect(successorFingerprint).toBe('03952ec625aae5d84a0f07d9a4cd9d571689744a88f9a79715c2e2cb34589129');
    const successor = { ...successorBase, fingerprint: successorFingerprint };
    const reuseBase = {
      pool_identity: 'pool:8', round_identity: 'round:8', coverage_version: 3,
      availability_version: 4, willingness_version: 5, same_round: true,
      coverage_valid: true, availability_valid: true, willingness_valid: true, fresh: true,
      accepted_candidate: false, case_no: readyQuery.case_no, successor_round_identity: 'round:8',
      generation_version: 7, event_version: 7, candidate_identity: 'candidate:8',
    };
    const reuseFingerprint = await payloadFingerprint(reuseBase);
    expect(reuseFingerprint).toBe('9b31675c64ad8a90394cf056adf612da265317dd36b655394e99cbf739692612');
    const value: ServiceBeforeReplacementQuery = {
      ...readyQuery,
      actual_service_proof: { ...zeroServiceProof, fingerprint: proofFingerprint },
      successor_round: { ...successor },
      candidate_pool_reuse_proof: { ...reuseBase, fingerprint: reuseFingerprint },
    };
    await expect(verifyServiceBeforeReplacementQuery(value, value.case_no, value.scenario)).resolves.toBe(value);
    await expect(verifyServiceBeforeReplacementQuery({
      ...value,
      candidate_pool_reuse_proof: { ...value.candidate_pool_reuse_proof!, fingerprint },
    }, value.case_no, value.scenario)).rejects.toThrow(/reuse proof fingerprint mismatch/);
    await expect(verifyServiceBeforeReplacementQuery({
      ...value,
      successor_round: { ...value.successor_round!, fingerprint },
    }, value.case_no, value.scenario)).rejects.toThrow(/successor round fingerprint mismatch/);
    await expect(verifyServiceBeforeReplacementQuery({
      ...value,
      actual_service_proof: { ...value.actual_service_proof!, fingerprint },
    }, value.case_no, value.scenario)).rejects.toThrow(/actual service proof fingerprint mismatch/);
    await expect(verifyServiceBeforeReplacementQuery(value, 'CASE-OTHER', value.scenario)).rejects.toThrow(/identity mismatch/);
    await expect(verifyServiceBeforeReplacementQuery(value, value.case_no, 'R-03')).rejects.toThrow(/identity mismatch/);
    await expect(verifyServiceBeforeReplacementPreview(preview, preview.case_no, {
      scenario: preview.scenario,
      reason: '不同原因',
      evidence: preview.evidence,
    })).rejects.toThrow(/identity mismatch/);
  });

  it('完整重算 Preview canonical payload，拒絕另一個格式正確的完整 digest', async () => {
    const proofFingerprint = 'f879e24d639b15776eb3acb1df640fc875f4d391f2acbfd164775191ec370d95';
    const previewPayload = {
      family: 'service-before-replacement', case_no: preview.case_no, prior_case_no: preview.case_no,
      scenario: preview.scenario, prior_aggregate_identity: preview.prior_aggregate_identity,
      expected_aggregate_version: preview.expected_aggregate_version,
      resulting_aggregate_version: preview.resulting_aggregate_version,
      prior_generation_identity: preview.prior_generation_identity, prior_event_identity: preview.prior_event_identity,
      expected_generation_version: preview.expected_generation_version, expected_event_version: preview.expected_event_version,
      generation_identity: preview.replacement_generation_identity, event_identity: preview.replacement_event_identity,
      round_identity: preview.successor_round_identity,
      actual_service_proof: [preview.case_no, [], zeroServiceProof.source_identity, zeroServiceProof.source_version, proofFingerprint],
      actual_service_dates: [], candidate_pool_reuse: null, candidate_identity: null,
      retained: [[retainedRoot.kind, retainedRoot.root_id, retainedRoot.case_no, retainedRoot.current, retainedRoot.caregiver_bound]],
      superseded: [[supersededRoot.kind, supersededRoot.root_id, supersededRoot.case_no, supersededRoot.current, supersededRoot.caregiver_bound]],
      created: [[createdRoot.kind, createdRoot.root_id, createdRoot.case_no, createdRoot.current, createdRoot.caregiver_bound]],
      resume_step: preview.resume_step, projection_kind: preview.projection_kind,
      reason_evidence: [preview.reason, preview.evidence], blockers: [], successor_round: null,
    } as const;
    const previewFingerprint = await payloadFingerprint(previewPayload);
    expect(previewFingerprint).toBe('1401b18612a0f2f9aa001574b4a72ba86e293f53fa9edd301a5984b20c644080');
    const validPreview: ServiceBeforeReplacementPreview = {
      ...preview,
      actual_service_proof: { ...zeroServiceProof, fingerprint: proofFingerprint },
      preview_fingerprint: previewFingerprint,
    };
    const request = { scenario: preview.scenario, reason: preview.reason, evidence: preview.evidence };
    await expect(verifyServiceBeforeReplacementPreview(validPreview, preview.case_no, request)).resolves.toBe(validPreview);
    await expect(verifyServiceBeforeReplacementPreview({ ...validPreview, preview_fingerprint: fingerprint }, preview.case_no, request)).rejects.toThrow(/preview fingerprint mismatch/);
  });

  it('重算 sha256_newline_v1 並綁定 case、preview 與 idempotency identity', async () => {
    const groups = [result.receipt.retained_root_ids, result.receipt.superseded_root_ids, result.receipt.created_root_ids];
    const digests = await Promise.all(groups.map((group) => sha256([...group].sort().join('\n'))));
    expect(digests).toEqual([
      '35c7e2dc0f13098ebd10d6ad70f127ad45e5576188d9e875ab009f198d2de6a9',
      '98c8818e7cba2e18396426586ac4a94a0eff6d3da28667ae41e23c4fb75d6a5f',
      '88c453df74722ce3fca2abdf063ea39a36cfcec075f4bd9b267b9b6a51f8750f',
    ]);
    const previewFingerprint = '1401b18612a0f2f9aa001574b4a72ba86e293f53fa9edd301a5984b20c644080';
    const actorBinding = { actor: 'admin:development', capabilities: ['orders.historical_review.remediate'] } as const;
    const request = {
      scenario: preview.scenario, reason: preview.reason, evidence: preview.evidence,
      expected_generation_version: 7, expected_event_version: 7, expected_aggregate_version: 7,
      prior_generation_identity: 'generation:7', prior_event_identity: 'event:7', prior_aggregate_identity: 'aggregate:7',
      preview_fingerprint: previewFingerprint,
    } as const;
    const commandFingerprint = await payloadFingerprint({
      command_type: 'scheduling.service_before_replacement.apply', command_version: 1,
      case_no: result.receipt.case_no, scenario: request.scenario,
      expected_generation_version: request.expected_generation_version,
      expected_event_version: request.expected_event_version,
      expected_aggregate_version: request.expected_aggregate_version,
      prior_generation_identity: request.prior_generation_identity, prior_event_identity: request.prior_event_identity,
      prior_aggregate_identity: request.prior_aggregate_identity, preview_fingerprint: request.preview_fingerprint,
      actor: actorBinding.actor, capabilities: actorBinding.capabilities, reason: request.reason, evidence: request.evidence,
    });
    expect(commandFingerprint).toBe('a5288988ef135e303841a09118544cf20357e8e20656d50fd8d4e4e731eef729');
    const validResult: ServiceBeforeReplacementApplyResult = {
      ...result,
      receipt: {
        ...result.receipt,
        command_fingerprint: commandFingerprint,
        preview_fingerprint: previewFingerprint,
        retained_root_set_digest: digests[0], superseded_root_set_digest: digests[1], created_root_set_digest: digests[2],
      },
      readback: { ...result.readback, root_set_digests: [digests[0], digests[1], digests[2]] },
    };
    const identity = { idempotencyKey: result.receipt.idempotency_key, correlationId: 'correlation:8' };
    await expect(verifyServiceBeforeReplacementApply(validResult, result.receipt.case_no, request, identity, actorBinding)).resolves.toBe(validResult);
    await expect(verifyServiceBeforeReplacementApply({
      ...validResult,
      receipt: { ...validResult.receipt, created_root_set_digest: fingerprint },
    }, result.receipt.case_no, request, identity, actorBinding)).rejects.toThrow(/root set digest mismatch/);
    await expect(verifyServiceBeforeReplacementApply({
      ...validResult,
      receipt: { ...validResult.receipt, command_fingerprint: fingerprint },
    }, result.receipt.case_no, request, identity, actorBinding)).rejects.toThrow(/command fingerprint mismatch/);
    await expect(verifyServiceBeforeReplacementApply(validResult, result.receipt.case_no, request, { ...identity, idempotencyKey: 'different-key' }, actorBinding)).rejects.toThrow(/identity mismatch/);
  });
});
