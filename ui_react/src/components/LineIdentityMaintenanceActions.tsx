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
>;

interface LineIdentityMaintenanceActionsProps {
  lineUserId: string;
  binding: Pick<
    LineIdentityBindingView,
    'status' | 'revocation_request_id' | 'revocation_status'
  >;
  client?: MaintenanceClient;
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
  if (!(error instanceof LineIdentityClientError)) return fallback;
  if (error.outcomeUnknown) return '操作結果尚未確認，請先重新查詢最新狀態，不要再次提交。';
  if (error.code === 'UNAUTHENTICATED') return '登入已失效，請重新登入後再試。';
  if (error.code === 'FORBIDDEN') return '目前帳號沒有執行這項 LINE 身分維護的權限。';
  if (error.code === 'NOT_FOUND') return '找不到這筆 LINE 身分資料，請重新查詢。';
  if (error.code === 'CONFLICT') return 'LINE 身分資料已變更，請重新查詢後再次確認。';
  if (error.code === 'REQUEST_INVALID') return '維護資料不完整，請檢查後再試。';
  return 'LINE 身分維護服務目前無法安全完成這項操作，請稍後再試。';
}

export function LineIdentityMaintenanceActions({
  lineUserId,
  binding,
  client = lineIdentityClient,
  onBindingChanged,
  onRevocationChanged,
}: LineIdentityMaintenanceActionsProps) {
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
      setReplacementResult(`綁定對象已更正為 ${view.subjectName}，並已回讀確認。`);
      onBindingChanged?.(result);
    } catch (error: unknown) {
      if (nextController.signal.aborted) return;
      setReplacementState('error');
      setReplacementError(safeError(error, 'LINE 身分更正提交失敗。'));
    }
  };

  const retryMenuRestore = async () => {
    const requestId = binding.revocation_request_id;
    const reason = maintenanceReason.trim();
    const retryableStatus = binding.revocation_status === 'menu_reset_failed'
      || binding.revocation_status === 'manual_completed';
    if (!requestId || !retryableStatus || !reason) return;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setMaintenanceState('loading');
    setMaintenanceError(null);
    setMaintenanceResult(null);
    try {
      const result = await client.retryRevocation(requestId, { reason }, { signal: nextController.signal });
      if (nextController.signal.aborted) return;
      setMaintenanceResult(adaptLineIdentityMaintenanceResult(result, 'retry'));
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
                    我已核對目前綁定與更正對象
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
          <p>背景服務正在回復 LINE 選單；請重新查詢最新狀態。</p>
        </section>
      )}

      {binding.revocation_request_id && binding.revocation_status === 'menu_reset_failed' && (
        <section aria-labelledby="line-identity-maintenance-title">
          <h4 id="line-identity-maintenance-title">解除失敗維護</h4>
          <p>身分授權已停止，系統仍需將 LINE 圖文選單自動回復成訪客模式。請先確認「訪客／預設選單」已重新發布，再重新排入回復流程。</p>
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
            onClick={() => void retryMenuRestore()}
          >
            重新排入訪客選單回復
          </button>
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

      {binding.revocation_request_id && binding.revocation_status === 'manual_completed' && (
        <section aria-labelledby="line-identity-menu-repair-title">
          <h4 id="line-identity-menu-repair-title">修復 LINE 訪客選單</h4>
          <p>系統授權已人工解除，但 LINE 圖文選單尚未確認回復。請先重新發布「訪客／預設選單」，再執行修復。</p>
          <label htmlFor="line-identity-menu-repair-reason">修復原因</label>
          <textarea
            id="line-identity-menu-repair-reason"
            value={maintenanceReason}
            rows={3}
            maxLength={1000}
            onChange={(event) => setMaintenanceReason(event.target.value)}
          />
          <button
            type="button"
            disabled={!maintenanceReason.trim() || maintenanceState === 'loading'}
            onClick={() => void retryMenuRestore()}
          >
            重新排入訪客選單回復
          </button>
          {maintenanceState === 'loading' && <p>正在提交選單修復…</p>}
          {maintenanceError && <div className="line-error" role="alert">{maintenanceError}</div>}
          {maintenanceResult && (
            <div className="line-success" role="status">
              <p>{maintenanceResult.notice}</p>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
