/**
 * File: LineIdentityMaintenanceActions.tsx
 * Description: 提供 LINE 身分對象更正與解除失敗維護操作，強制 Preview、確認與安全錯誤呈現。
 */
import { useEffect, useRef, useState } from 'react';
import {
  adaptLineIdentityMaintenanceResult,
  adaptLineIdentityReplacementPreview,
  adaptLineIdentityReplacementResult,
  type LineIdentityMaintenanceResultViewModel,
  type LineIdentityReplacementPreviewViewModel,
} from '../adapters/line_identity/line_identity_adapter';
import {
  lineIdentityClient,
  type LineIdentityClient,
} from '../api/line_identity/line_identity_client';
import { sessionClient } from '../api/auth/session_client';
import { LineIdentityClientError } from '../api/line_identity/line_identity_errors';
import type {
  LineIdentityBindingView,
  LineIdentityRevocationRequestView,
} from '../api/line_identity/line_identity_schemas';

type MaintenanceClient = Pick<
  LineIdentityClient,
  | 'previewReplacement'
  | 'applyReplacement'
  | 'retryRevocation'
  | 'manualCompleteRevocation'
>;

interface LineIdentityMaintenanceActionsProps {
  lineUserId: string;
  binding: Pick<
    LineIdentityBindingView,
    'status' | 'revocation_request_id' | 'revocation_status'
  >;
  client?: MaintenanceClient;
  canManualComplete?: boolean;
  onBindingChanged?: (binding: LineIdentityBindingView) => void;
  onRevocationChanged?: (request: LineIdentityRevocationRequestView) => void;
}

type OperationState = 'idle' | 'loading' | 'success' | 'error';

function operationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function safeError(error: unknown, fallback: string): string {
  return error instanceof LineIdentityClientError
    ? `${error.code}：${error.message}`
    : fallback;
}

export function LineIdentityMaintenanceActions({
  lineUserId,
  binding,
  client = lineIdentityClient,
  canManualComplete,
  onBindingChanged,
  onRevocationChanged,
}: LineIdentityMaintenanceActionsProps) {
  const currentUser = sessionClient.getUser();
  const manualCompleteAllowed = canManualComplete ?? Boolean(
    currentUser?.role === 'system_admin'
      || currentUser?.capabilities.includes('line.identity.binding.override')
  );
  const controller = useRef<AbortController | null>(null);
  const replacementIntent = useRef<{
    idempotencyKey: string;
    correlationId: string;
  } | null>(null);
  const [targetReference, setTargetReference] = useState('');
  const [replacementReason, setReplacementReason] = useState('');
  const [replacementConfirmed, setReplacementConfirmed] = useState(false);
  const [replacementPreview, setReplacementPreview] = useState<LineIdentityReplacementPreviewViewModel | null>(null);
  const [replacementState, setReplacementState] = useState<OperationState>('idle');
  const [replacementError, setReplacementError] = useState<string | null>(null);
  const [replacementResult, setReplacementResult] = useState<string | null>(null);
  const [maintenanceReason, setMaintenanceReason] = useState('');
  const [failureConfirmed, setFailureConfirmed] = useState(false);
  const [overrideConfirmed, setOverrideConfirmed] = useState(false);
  const [maintenanceState, setMaintenanceState] = useState<OperationState>('idle');
  const [maintenanceError, setMaintenanceError] = useState<string | null>(null);
  const [maintenanceResult, setMaintenanceResult] = useState<LineIdentityMaintenanceResultViewModel | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  const resetReplacementPreview = () => {
    controller.current?.abort();
    controller.current = null;
    replacementIntent.current = null;
    setReplacementPreview(null);
    setReplacementConfirmed(false);
    setReplacementState('idle');
    setReplacementError(null);
    setReplacementResult(null);
  };

  const previewReplacement = async () => {
    const target = targetReference.trim();
    if (!target || binding.status !== 'bound') return;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    replacementIntent.current = {
      idempotencyKey: operationIdentity('line-identity-replacement-apply'),
      correlationId: operationIdentity('line-identity-replacement'),
    };
    setReplacementState('loading');
    setReplacementError(null);
    setReplacementResult(null);
    setReplacementConfirmed(false);
    try {
      const preview = await client.previewReplacement(lineUserId, target, {
        signal: nextController.signal,
      });
      if (nextController.signal.aborted) return;
      setReplacementPreview(adaptLineIdentityReplacementPreview(preview));
      setReplacementState('idle');
    } catch (error: unknown) {
      if (nextController.signal.aborted) return;
      replacementIntent.current = null;
      setReplacementPreview(null);
      setReplacementState('error');
      setReplacementError(safeError(error, 'LINE 身分更正預覽失敗。'));
    }
  };

  const applyReplacement = async () => {
    const preview = replacementPreview;
    const intent = replacementIntent.current;
    const target = targetReference.trim();
    const reason = replacementReason.trim();
    if (!preview || preview.hasBlockers || !intent || !target || !reason || !replacementConfirmed) return;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setReplacementState('loading');
    setReplacementError(null);
    try {
      const result = await client.applyReplacement(
        lineUserId,
        {
          expected_version: preview.binding.version,
          target_subject_reference: target,
          reason,
          idempotency_key: intent.idempotencyKey,
          correlation_id: intent.correlationId,
        },
        { signal: nextController.signal }
      );
      if (nextController.signal.aborted) return;
      const view = adaptLineIdentityReplacementResult(result);
      setReplacementState('success');
      setReplacementResult(`綁定對象已更正為 ${view.subjectName}；目前版本 ${view.version}。`);
      onBindingChanged?.(result);
    } catch (error: unknown) {
      if (nextController.signal.aborted) return;
      setReplacementState('error');
      setReplacementError(safeError(error, 'LINE 身分更正提交失敗。'));
    }
  };

  const runMaintenance = async (operation: 'retry' | 'manual_complete') => {
    const requestId = binding.revocation_request_id;
    const reason = maintenanceReason.trim();
    if (!requestId || binding.revocation_status !== 'menu_reset_failed' || !reason) return;
    if (
      operation === 'manual_complete'
      && (!manualCompleteAllowed || !failureConfirmed || !overrideConfirmed)
    ) return;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setMaintenanceState('loading');
    setMaintenanceError(null);
    setMaintenanceResult(null);
    try {
      const result = operation === 'retry'
        ? await client.retryRevocation(requestId, { reason }, { signal: nextController.signal })
        : await client.manualCompleteRevocation(requestId, { reason }, { signal: nextController.signal });
      if (nextController.signal.aborted) return;
      setMaintenanceResult(adaptLineIdentityMaintenanceResult(result, operation));
      setMaintenanceState('success');
      onRevocationChanged?.(result);
    } catch (error: unknown) {
      if (nextController.signal.aborted) return;
      setMaintenanceState('error');
      setMaintenanceError(safeError(error, 'LINE 身分解除維護操作失敗。'));
    }
  };

  return (
    <div className="line-action-panel" data-control-id="line.identity.maintenance">
      {binding.status === 'bound' && (
        <section aria-labelledby="line-identity-replacement-title">
          <h4 id="line-identity-replacement-title">更正綁定對象</h4>
          <p>只允許更正為相同角色的既有對象；先預覽，確認後才會提交。</p>
          <label htmlFor="line-identity-target-reference">更正對象識別值</label>
          <input
            id="line-identity-target-reference"
            value={targetReference}
            maxLength={191}
            onChange={(event) => {
              setTargetReference(event.target.value);
              resetReplacementPreview();
            }}
          />
          <button
            type="button"
            disabled={!targetReference.trim() || replacementState === 'loading'}
            onClick={() => void previewReplacement()}
          >
            預覽對象更正
          </button>
          {replacementState === 'loading' && <p>正在驗證更正條件…</p>}
          {replacementPreview && (
            <div>
              <p>目標對象：<strong>{replacementPreview.targetSubjectName}</strong></p>
              {replacementPreview.hasBlockers ? (
                <ul>{replacementPreview.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
              ) : (
                <>
                  <label htmlFor="line-identity-replacement-reason">更正原因</label>
                  <textarea
                    id="line-identity-replacement-reason"
                    value={replacementReason}
                    rows={3}
                    maxLength={1000}
                    onChange={(event) => {
                      setReplacementReason(event.target.value);
                      setReplacementConfirmed(false);
                    }}
                  />
                  <label>
                    <input
                      type="checkbox"
                      checked={replacementConfirmed}
                      onChange={(event) => setReplacementConfirmed(event.target.checked)}
                    />
                    我已確認目前版本與更正對象
                  </label>
                  <button
                    type="button"
                    disabled={!replacementReason.trim() || !replacementConfirmed || replacementState === 'loading'}
                    onClick={() => void applyReplacement()}
                  >
                    提交對象更正
                  </button>
                </>
              )}
            </div>
          )}
          {replacementError && <div className="line-error" role="alert">{replacementError}</div>}
          {replacementResult && <div className="line-success" role="status">{replacementResult}</div>}
        </section>
      )}

      {binding.revocation_request_id && binding.revocation_status === 'pending_menu_reset' && (
        <section aria-labelledby="line-identity-pending-title">
          <h4 id="line-identity-pending-title">解除流程處理中</h4>
          <p>Durable worker 正在回復 Rich Menu；請重新查詢狀態，不直接呼叫 LINE provider。</p>
        </section>
      )}

      {binding.revocation_request_id && binding.revocation_status === 'menu_reset_failed' && (
        <section aria-labelledby="line-identity-maintenance-title">
          <h4 id="line-identity-maintenance-title">解除失敗維護</h4>
          <p>可重新排入 durable queue；只有確認 provider 永久失敗或重試耗盡時才能人工完成。</p>
          <label htmlFor="line-identity-maintenance-reason">維護原因</label>
          <textarea
            id="line-identity-maintenance-reason"
            value={maintenanceReason}
            rows={3}
            maxLength={1000}
            onChange={(event) => setMaintenanceReason(event.target.value)}
          />
          <button
            type="button"
            disabled={!maintenanceReason.trim() || maintenanceState === 'loading'}
            onClick={() => void runMaintenance('retry')}
          >
            重新排入 Rich Menu 回復
          </button>
          {manualCompleteAllowed ? (
            <>
              <label>
                <input
                  type="checkbox"
                  checked={failureConfirmed}
                  onChange={(event) => setFailureConfirmed(event.target.checked)}
                />
                我已確認 provider 永久失敗或重試已耗盡
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={overrideConfirmed}
                  onChange={(event) => setOverrideConfirmed(event.target.checked)}
                />
                我了解人工完成會直接完成解除並清除 owner projection
              </label>
              <button
                type="button"
                disabled={!maintenanceReason.trim() || !failureConfirmed || !overrideConfirmed || maintenanceState === 'loading'}
                onClick={() => void runMaintenance('manual_complete')}
              >
                人工完成解除
              </button>
            </>
          ) : (
            <p>人工完成只提供具 LINE 身分 override 權限的系統管理員。</p>
          )}
          {maintenanceState === 'loading' && <p>正在提交維護操作…</p>}
          {maintenanceError && <div className="line-error" role="alert">{maintenanceError}</div>}
          {maintenanceResult && (
            <div className="line-success" role="status">
              <strong>{maintenanceResult.statusLabel}</strong>
              <p>{maintenanceResult.notice}</p>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
