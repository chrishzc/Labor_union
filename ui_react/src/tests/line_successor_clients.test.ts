/**
 * File: line_successor_clients.test.ts
 * Description: 驗證 LINE successor 三組 client／adapter 的白名單、命令身分、遮罩與 fail-closed 行為。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { lineSafeConfigClient } from '../api/line_safe_config/line_safe_config_client';
import { LineSafeConfigError } from '../api/line_safe_config/line_safe_config_errors';
import { adaptLineSafeConfig } from '../adapters/line_safe_config/line_safe_config_adapter';
import { customerServiceEscalationClient } from '../api/customer_service_escalations/customer_service_escalation_client';
import { CustomerServiceEscalationError } from '../api/customer_service_escalations/customer_service_escalation_errors';
import { CustomerServiceEscalationReceiptSchema } from '../api/customer_service_escalations/customer_service_escalation_schemas';
import { adaptCustomerServiceEscalation } from '../adapters/customer_service_escalations/customer_service_escalation_adapter';
import { lineRuntimeTargetClient } from '../api/line_runtime_targets/line_runtime_target_client';
import { LineRuntimeTargetError } from '../api/line_runtime_targets/line_runtime_target_errors';
import { LineRuntimeTargetReceiptSchema } from '../api/line_runtime_targets/line_runtime_target_schemas';
import { adaptLineRuntimeTarget, adaptLineRuntimeTargetReceipt } from '../adapters/line_runtime_targets/line_runtime_target_adapter';
import {
  ESCALATION_RECEIPT_RESPONSE,
  ESCALATION_VIEW_RESPONSE,
  LINE_SAFE_CONFIG_RESPONSE,
  RUNTIME_CANDIDATES_RESPONSE,
  RUNTIME_MUTATION_RESPONSE,
  RUNTIME_TARGETS_RESPONSE,
} from './fixtures/line_successor_contract_fixtures';

function response(payload: object, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } });
}

function setSession(token = 'line-successor-token'): void {
  sessionClient.setSession(token, {
    id: 7,
    username: 'line-successor-admin',
    display_name: 'LINE 接班測試',
    role: 'operator',
    linked_line_user_id: null,
    capabilities: [],
    is_root: false,
    access_control_version: 1,
  });
}

describe('LINE safe configuration successor', () => {
  beforeEach(() => { vi.restoreAllMocks(); setSession(); });
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('六個 closed kinds 只送 authenticated GET、caller correlation 與 AbortSignal', async () => {
    const kinds = ['message_templates', 'message_schedules', 'rich_menus', 'liff', 'customer_service', 'notification_rules'] as const;
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      const kind = url.split('/').at(-2);
      return Promise.resolve(response({ ...LINE_SAFE_CONFIG_RESPONSE, data: { kind, revision: 1, state: 'configured' } }));
    });
    globalThis.fetch = fetchMock;
    const controller = new AbortController();
    for (const kind of kinds) {
      await lineSafeConfigClient.getSafe(kind, { correlationId: `safe-${kind}`, signal: controller.signal });
    }
    expect(fetchMock).toHaveBeenCalledTimes(6);
    fetchMock.mock.calls.forEach((call, index) => {
      expect(call[0]).toBe(`/api/v1/line/configurations/${kinds[index]}/safe`);
      expect(call[1]?.method).toBe('GET');
      expect(new Headers(call[1]?.headers).get('Authorization')).toBe('Bearer line-successor-token');
      expect(new Headers(call[1]?.headers).get('X-Correlation-ID')).toBe(`safe-${kinds[index]}`);
      expect(call[1]?.signal).toBeInstanceOf(AbortSignal);
    });
  });

  it('safe payload 多出 definition 或未知 enum 時 fail closed', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      ...LINE_SAFE_CONFIG_RESPONSE,
      data: { ...LINE_SAFE_CONFIG_RESPONSE.data, definition: { token: 'secret' } },
    }));
    await expect(lineSafeConfigClient.getSafe('rich_menus', { correlationId: 'safe-drift' }))
      .rejects.toMatchObject({ code: 'LINE_SAFE_CONFIG_CONTRACT' });
    expect(() => adaptLineSafeConfig({ ...LINE_SAFE_CONFIG_RESPONSE.data, state: 'unknown' } as never)).toThrow();
    const controller = new AbortController();
    controller.abort();
    await expect(lineSafeConfigClient.getSafe('rich_menus', { correlationId: 'safe-abort', signal: controller.signal }))
      .rejects.toMatchObject({ code: 'LINE_SAFE_CONFIG_ABORTED' });
    sessionClient.clearSession();
    await expect(lineSafeConfigClient.getSafe('rich_menus', { correlationId: 'safe-no-session' }))
      .rejects.toBeInstanceOf(LineSafeConfigError);
  });
});

describe('M4 customer-service escalation successor', () => {
  beforeEach(() => { vi.restoreAllMocks(); setSession(); });
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('create/detail/claim/handling/resolve 使用正式 Preview／Apply paths 與 command identity', async () => {
    const receiptFixture = CustomerServiceEscalationReceiptSchema.safeParse(ESCALATION_RECEIPT_RESPONSE.data);
    expect(receiptFixture.success, receiptFixture.error?.message).toBe(true);
    const previewFingerprint = 'c'.repeat(64);
    const previewResponse = (operation: 'create' | 'claim' | 'handling_started' | 'resolve', before: 'absent' | 'open' | 'claimed' | 'handling', after: 'open' | 'claimed' | 'handling' | 'resolved') => ({
      success: true,
      message: 'Preview 已建立',
      data: {
        operation,
        escalation_id: operation === 'create' ? null : 11,
        before_workflow_status: before,
        resulting_workflow_status: after,
        before_hold_state: operation === 'create' ? 'absent' : 'active',
        resulting_hold_state: operation === 'resolve' ? 'released' : 'active',
        current_escalation_version: operation === 'create' ? null : ({ claim: 0, handling_started: 1, resolve: 2 } as const)[operation],
        current_ticket_version: operation === 'handling_started' ? 2 : operation === 'resolve' ? 3 : null,
        preview_fingerprint: previewFingerprint,
        apply_ready: true,
      },
      error: null,
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(previewResponse('create', 'absent', 'open')))
      .mockResolvedValueOnce(response({ ...ESCALATION_RECEIPT_RESPONSE, data: { ...ESCALATION_RECEIPT_RESPONSE.data, operation: 'create', correlation_id: 'm4-correlation-1' } }))
      .mockResolvedValueOnce(response(ESCALATION_VIEW_RESPONSE))
      .mockResolvedValueOnce(response(previewResponse('claim', 'open', 'claimed')))
      .mockResolvedValueOnce(response({ ...ESCALATION_RECEIPT_RESPONSE, data: { ...ESCALATION_RECEIPT_RESPONSE.data, operation: 'claim', correlation_id: 'm4-correlation-1' } }))
      .mockResolvedValueOnce(response(previewResponse('handling_started', 'claimed', 'handling')))
      .mockResolvedValueOnce(response({ ...ESCALATION_RECEIPT_RESPONSE, data: { ...ESCALATION_RECEIPT_RESPONSE.data, operation: 'handling_started', correlation_id: 'm4-correlation-1' } }))
      .mockResolvedValueOnce(response(previewResponse('resolve', 'handling', 'resolved')))
      .mockResolvedValueOnce(response({ ...ESCALATION_RECEIPT_RESPONSE, data: { ...ESCALATION_RECEIPT_RESPONSE.data, operation: 'resolve', correlation_id: 'm4-correlation-1' } }));
    globalThis.fetch = fetchMock;
    const identity = { idempotency_key: 'm4-command-1', correlation_id: 'm4-correlation-1' };
    const createRequest = {
      source_event_identity: 'line-event:m4', source_kind: 'line_inbox', source_fingerprint: 'a'.repeat(64),
      trigger_code: 'complaint', trigger_policy_version: 'complaint.v1', ticket_category: 'other',
      masked_context: { summary_code: 'complaint_explicit', policy_version: 'complaint.v1', category: 'other', redaction_version: 'm4-mask.v1' },
      hold_scope: 'line:conversation:m4', ...identity,
    } as const;
    await customerServiceEscalationClient.previewCreate(createRequest);
    await customerServiceEscalationClient.create({ ...createRequest, preview_fingerprint: previewFingerprint });
    await customerServiceEscalationClient.getDetail(11, { correlationId: 'm4-detail-11' });
    const claimRequest = { expected_escalation_version: 0, ...identity };
    await customerServiceEscalationClient.previewClaim(11, claimRequest);
    await customerServiceEscalationClient.claim(11, { ...claimRequest, preview_fingerprint: previewFingerprint });
    const handlingRequest = { expected_escalation_version: 1, expected_ticket_version: 2, ...identity };
    await customerServiceEscalationClient.previewStartHandling(11, handlingRequest);
    await customerServiceEscalationClient.startHandling(11, { ...handlingRequest, preview_fingerprint: previewFingerprint });
    const resolveRequest = { expected_escalation_version: 2, expected_ticket_version: 3, resolution_code: 'handled', resolution_evidence_digest: 'b'.repeat(64), ...identity };
    await customerServiceEscalationClient.previewResolve(11, resolveRequest);
    await customerServiceEscalationClient.resolve(11, { ...resolveRequest, preview_fingerprint: previewFingerprint });
    expect(fetchMock.mock.calls.map((call) => [call[1]?.method, call[0]])).toEqual([
      ['POST', '/api/v1/customer-service/escalations/preview'],
      ['POST', '/api/v1/customer-service/escalations'],
      ['GET', '/api/v1/customer-service/escalations/11'],
      ['POST', '/api/v1/customer-service/escalations/11/claim/preview'],
      ['POST', '/api/v1/customer-service/escalations/11/claim'],
      ['POST', '/api/v1/customer-service/escalations/11/handling/preview'],
      ['POST', '/api/v1/customer-service/escalations/11/handling'],
      ['POST', '/api/v1/customer-service/escalations/11/resolve/preview'],
      ['POST', '/api/v1/customer-service/escalations/11/resolve'],
    ]);
    for (const index of [1, 4, 6, 8]) {
      const call = fetchMock.mock.calls[index];
      const headers = new Headers(call[1]?.headers);
      expect(headers.get('Idempotency-Key')).toBe('m4-command-1');
      expect(headers.get('X-Correlation-ID')).toBe('m4-correlation-1');
      expect(JSON.parse(String(call[1]?.body))).toMatchObject({ ...identity, preview_fingerprint: previewFingerprint });
    }
    expect(adaptCustomerServiceEscalation(ESCALATION_VIEW_RESPONSE.data)).toMatchObject({ workflowStatusLabel: '待接手', availableActionLabels: ['接手'] });
  });

  it('raw context、extra response 或 mutation network failure 皆 typed fail closed', async () => {
    globalThis.fetch = vi.fn();
    await expect(customerServiceEscalationClient.previewCreate({
      source_event_identity: 'line-event:m4', source_kind: 'line_inbox', source_fingerprint: 'a'.repeat(64),
      trigger_code: 'complaint', trigger_policy_version: 'complaint.v1', ticket_category: 'other',
      masked_context: { summary_code: 'complaint_explicit', policy_version: 'complaint.v1', category: 'other', redaction_version: 'm4-mask.v1', raw_message: 'secret' } as never,
      hold_scope: 'line:conversation:m4', idempotency_key: 'm4-create', correlation_id: 'm4-create',
    })).rejects.toBeInstanceOf(CustomerServiceEscalationError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
    globalThis.fetch = vi.fn().mockResolvedValue(response({ ...ESCALATION_VIEW_RESPONSE, data: { ...ESCALATION_VIEW_RESPONSE.data, line_user_id: 'U-secret' } }));
    await expect(customerServiceEscalationClient.getDetail(11, { correlationId: 'm4-detail' })).rejects.toMatchObject({ code: 'CUSTOMER_SERVICE_ESCALATION_CONTRACT' });
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('lost response'));
    await expect(customerServiceEscalationClient.claim(11, { expected_escalation_version: 0, idempotency_key: 'm4-claim', correlation_id: 'm4-claim', preview_fingerprint: 'd'.repeat(64) }))
      .rejects.toMatchObject({ outcomeUnknown: true, retryable: true });
  });
});

describe('LINE runtime alert target successor', () => {
  beforeEach(() => { vi.restoreAllMocks(); setSession(); });
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('list/candidates/add/reset/enable-disable 都先 Preview 再 Apply 並保留 command identity', async () => {
    const receiptFixture = LineRuntimeTargetReceiptSchema.safeParse(RUNTIME_MUTATION_RESPONSE.data);
    expect(receiptFixture.success, receiptFixture.error?.message).toBe(true);
    const fingerprint = 'f'.repeat(64);
    const previewResponse = (operation: 'admin_target_add' | 'group_reset' | 'disable', targetId: number | null, previousState: 'absent' | 'active') => ({
      success: true,
      message: 'Preview 已建立',
      data: {
        operation,
        target_id: targetId,
        previous_state: previousState,
        resulting_state: operation === 'group_reset' || operation === 'disable' ? 'disabled' : 'active',
        current_version: targetId === null ? 'absent' : `version-${targetId}`,
        preview_fingerprint: fingerprint,
        apply_ready: true,
      },
      error: null,
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(RUNTIME_TARGETS_RESPONSE))
      .mockResolvedValueOnce(response(RUNTIME_CANDIDATES_RESPONSE))
      .mockResolvedValueOnce(response(previewResponse('admin_target_add', null, 'absent')))
      .mockResolvedValueOnce(response({ ...RUNTIME_MUTATION_RESPONSE, data: { ...RUNTIME_MUTATION_RESPONSE.data, operation: 'admin_target_add', correlation_id: 'runtime-add' } }))
      .mockResolvedValueOnce(response(previewResponse('group_reset', 1, 'active')))
      .mockResolvedValueOnce(response({ ...RUNTIME_MUTATION_RESPONSE, data: { ...RUNTIME_MUTATION_RESPONSE.data, operation: 'group_reset', correlation_id: 'runtime-reset' } }))
      .mockResolvedValueOnce(response(previewResponse('disable', 3, 'active')))
      .mockResolvedValueOnce(response({ ...RUNTIME_MUTATION_RESPONSE, data: { ...RUNTIME_MUTATION_RESPONSE.data, operation: 'disable', correlation_id: 'runtime-toggle' } }));
    globalThis.fetch = fetchMock;
    await lineRuntimeTargetClient.listTargets({ correlationId: 'runtime-list' });
    await lineRuntimeTargetClient.listAdminCandidates({ correlationId: 'runtime-candidates' });
    const addRequest = { admin_user_id: 7, minimum_status: 'critical' as const, reason: '輪值', idempotency_key: 'runtime-add', correlation_id: 'runtime-add' };
    await lineRuntimeTargetClient.previewAddAdminTarget(addRequest);
    await lineRuntimeTargetClient.addAdminTarget({ ...addRequest, preview_fingerprint: fingerprint });
    const resetRequest = { expected_version: 'version-1', reason: '群組重設', idempotency_key: 'runtime-reset', correlation_id: 'runtime-reset' };
    await lineRuntimeTargetClient.previewResetGroup(resetRequest);
    await lineRuntimeTargetClient.resetGroup({ ...resetRequest, preview_fingerprint: fingerprint });
    const toggleRequest = { expected_version: 'version-2', enabled: false, reason: '停用', idempotency_key: 'runtime-toggle', correlation_id: 'runtime-toggle' };
    await lineRuntimeTargetClient.previewSetEnabled(3, toggleRequest);
    await lineRuntimeTargetClient.setEnabled(3, { ...toggleRequest, preview_fingerprint: fingerprint });
    expect(fetchMock.mock.calls.map((call) => [call[1]?.method, call[0]])).toEqual([
      ['GET', '/api/v1/runtime/line-alert-targets'],
      ['GET', '/api/v1/runtime/line-alert-targets/admin-candidates'],
      ['POST', '/api/v1/runtime/line-alert-targets/admin/preview'],
      ['POST', '/api/v1/runtime/line-alert-targets/admin'],
      ['POST', '/api/v1/runtime/line-alert-targets/group/reset/preview'],
      ['POST', '/api/v1/runtime/line-alert-targets/group/reset'],
      ['POST', '/api/v1/runtime/line-alert-targets/3/preview'],
      ['PATCH', '/api/v1/runtime/line-alert-targets/3'],
    ]);
    const toggleHeaders = new Headers(fetchMock.mock.calls[7][1]?.headers);
    expect(toggleHeaders.get('Idempotency-Key')).toBe('runtime-toggle');
    expect(toggleHeaders.get('X-Correlation-ID')).toBe('runtime-toggle');
    expect(adaptLineRuntimeTarget(RUNTIME_TARGETS_RESPONSE.data[0])).toMatchObject({ stateLabel: '啟用', minimumStatusLabel: '警告以上' });
    expect(adaptLineRuntimeTargetReceipt(RUNTIME_MUTATION_RESPONSE.data).operationLabel).toBe('停用');
  });

  it('敏感 extra field、缺 session 與 unknown outcome 一律 typed fail closed', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      ...RUNTIME_TARGETS_RESPONSE,
      data: [{ ...RUNTIME_TARGETS_RESPONSE.data[0], group_id: 'C-secret' }],
    }));
    await expect(lineRuntimeTargetClient.listTargets({ correlationId: 'runtime-drift' }))
      .rejects.toMatchObject({ code: 'LINE_RUNTIME_TARGET_CONTRACT' });
    sessionClient.clearSession();
    await expect(lineRuntimeTargetClient.listTargets({ correlationId: 'runtime-no-session' }))
      .rejects.toBeInstanceOf(LineRuntimeTargetError);
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('lost response'));
    setSession();
    await expect(lineRuntimeTargetClient.resetGroup({ expected_version: 'version-1', reason: '重設', idempotency_key: 'runtime-reset', correlation_id: 'runtime-reset', preview_fingerprint: 'e'.repeat(64) }))
      .rejects.toMatchObject({ outcomeUnknown: true, retryable: true });
  });

  it('current 409 typed error 即使沒有 current_version 仍保留 server idempotency code', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      detail: { error: {
        category: 'idempotency_mismatch',
        code: 'line_alert_target_idempotency_mismatch',
        message: '相同 key 已用於不同命令。',
        correlation_id: 'runtime-conflict',
        field_errors: [],
        domain_blockers: [],
        retryable: false,
      } },
    }, 409));
    await expect(lineRuntimeTargetClient.resetGroup({ expected_version: 'version-1', reason: '重設', idempotency_key: 'runtime-conflict', correlation_id: 'runtime-conflict', preview_fingerprint: 'e'.repeat(64) }))
      .rejects.toMatchObject({
        code: 'LINE_RUNTIME_TARGET_IDEMPOTENCY_MISMATCH',
        publicCode: 'line_alert_target_idempotency_mismatch',
        outcomeUnknown: false,
      });
  });
});
