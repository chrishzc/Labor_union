/**
 * File: AlertGroupSecurity.tsx
 * Description: 以 typed LINE runtime target 契約完成查詢、Preview、確認、Apply、receipt 與 readback。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, RotateCcw, SearchCheck, ShieldCheck } from 'lucide-react';
import { lineRuntimeTargetClient } from '../../api/line_runtime_targets/line_runtime_target_client';
import { LineRuntimeTargetError } from '../../api/line_runtime_targets/line_runtime_target_errors';
import type {
  LineRuntimeGroupResetRequest,
  LineRuntimeTarget,
  LineRuntimeTargetEnabledRequest,
  LineRuntimeTargetPreview,
  LineRuntimeTargetReceipt,
} from '../../api/line_runtime_targets/line_runtime_target_schemas';
import { LineManagementPage } from '../LineManagementPage';
import '../LineManagementPage.css';

export interface RuntimeTargetClient {
  listTargets: typeof lineRuntimeTargetClient.listTargets;
  previewResetGroup: typeof lineRuntimeTargetClient.previewResetGroup;
  resetGroup: typeof lineRuntimeTargetClient.resetGroup;
  previewSetEnabled: typeof lineRuntimeTargetClient.previewSetEnabled;
  setEnabled: typeof lineRuntimeTargetClient.setEnabled;
}

export interface AlertGroupSecurityProps {
  client?: RuntimeTargetClient;
  runtimeTargetClient?: RuntimeTargetClient;
}

type PendingAction =
  | {
      kind: 'group_reset';
      target: LineRuntimeTarget;
      request: LineRuntimeGroupResetRequest;
      preview: LineRuntimeTargetPreview;
    }
  | {
      kind: 'toggle';
      target: LineRuntimeTarget;
      request: LineRuntimeTargetEnabledRequest;
      preview: LineRuntimeTargetPreview;
    };

function publicFailureMessage(error: unknown): string {
  if (error instanceof LineRuntimeTargetError) {
    return error.message;
  }
  return 'LINE 通知群組操作失敗，請重新登入或稍後再試。';
}

function stateLabel(state: string): string {
  if (state === 'active') return '啟用';
  if (state === 'disabled') return '停用';
  if (state === 'revoked') return '已解除';
  return '待確認';
}

function minimumStatusLabel(status: LineRuntimeTarget['minimum_status']): string {
  if (status === 'critical') return '重大異常';
  if (status === 'warning') return '重要通知';
  return '一般通知';
}

function identityPart(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
}

function commandIdentity(operation: string): { correlation_id: string; idempotency_key: string } {
  const part = identityPart();
  return {
    correlation_id: `line-security:${operation}:${part}`,
    idempotency_key: `line-security:${operation}:${part}`,
  };
}

export const AlertGroupSecurity: React.FC<AlertGroupSecurityProps> = ({
  client,
  runtimeTargetClient,
}) => {
  const targetClient = client ?? runtimeTargetClient ?? lineRuntimeTargetClient;
  const [targets, setTargets] = useState<LineRuntimeTarget[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [busy, setBusy] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [reason, setReason] = useState<string>('工會人員調整異常通知群組');
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [confirmed, setConfirmed] = useState<boolean>(false);
  const [receipt, setReceipt] = useState<LineRuntimeTargetReceipt | null>(null);
  const [readbackMessage, setReadbackMessage] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [activeWorkspace, setActiveWorkspace] = useState<'groups' | 'operations'>('groups');
  const groupTarget = targets.find((target) => target.target_kind === 'group') ?? null;

  const loadTargets = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const result = await targetClient.listTargets({ correlationId: `line-security-query:${identityPart()}`, signal });
      setTargets(result);
    } catch (error) {
      if (signal?.aborted) return;
      setTargets([]);
      setErrorMessage(publicFailureMessage(error));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [targetClient]);

  useEffect(() => {
    const controller = new AbortController();
    void loadTargets(controller.signal);
    return () => controller.abort();
  }, [loadTargets, reloadKey]);

  const clearCandidate = () => {
    setPending(null);
    setConfirmed(false);
  };

  const previewToggle = async (target: LineRuntimeTarget) => {
    const normalizedReason = reason.trim();
    if (!normalizedReason) {
      setErrorMessage('請先填寫異動原因。');
      return;
    }
    setBusy(true);
    setErrorMessage(null);
    setReceipt(null);
    setReadbackMessage(null);
    clearCandidate();
    try {
      const request: LineRuntimeTargetEnabledRequest = {
        expected_version: target.current_version,
        enabled: target.state !== 'active',
        reason: normalizedReason,
        ...commandIdentity('toggle'),
      };
      const preview = await targetClient.previewSetEnabled(target.target_id, request);
      setPending({ kind: 'toggle', target, request, preview });
    } catch (error) {
      setErrorMessage(publicFailureMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const previewGroupReset = async (target: LineRuntimeTarget) => {
    const normalizedReason = reason.trim();
    if (!normalizedReason) {
      setErrorMessage('請先填寫異動原因。');
      return;
    }
    setBusy(true);
    setErrorMessage(null);
    setReceipt(null);
    setReadbackMessage(null);
    clearCandidate();
    try {
      const request: LineRuntimeGroupResetRequest = {
        expected_version: target.current_version,
        reason: normalizedReason,
        ...commandIdentity('group-reset'),
      };
      const preview = await targetClient.previewResetGroup(request);
      setPending({ kind: 'group_reset', target, request, preview });
    } catch (error) {
      setErrorMessage(publicFailureMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const applyPending = async () => {
    if (!pending || !confirmed) return;
    setBusy(true);
    setErrorMessage(null);
    try {
      const applied = pending.kind === 'group_reset'
        ? await targetClient.resetGroup({
            ...pending.request,
            preview_fingerprint: pending.preview.preview_fingerprint,
          })
        : await targetClient.setEnabled(pending.target.target_id, {
            ...pending.request,
            preview_fingerprint: pending.preview.preview_fingerprint,
          });
      setReceipt(applied);
      setPending(null);
      setConfirmed(false);
      try {
        const readback = await targetClient.listTargets({ correlationId: `line-security-readback:${identityPart()}` });
        setTargets(readback);
        setReadbackMessage('已重新查詢並確認最新狀態。');
      } catch {
        setReadbackMessage('變更已受理，但最新狀態暫時無法取得；可按「重新整理」再次查詢，不會重複提交。');
      }
    } catch (error) {
      setErrorMessage(publicFailureMessage(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="alert-group-security-container">
      <header className="line-hub-page-header alert-security-page-header">
        <div className="line-hub-page-heading">
          <span className="line-hub-page-icon" aria-hidden="true"><ShieldCheck /></span>
          <div>
            <p className="line-hub-eyebrow">LINE 專區</p>
            <h1>群組與安全</h1>
            <p>查詢異常通知對象，並以影響預覽與明確確認保護每次異動。</p>
          </div>
        </div>
      </header>

      <nav className="line-hub-section-tabs alert-security-tabs" aria-label="群組與安全功能">
        <button
          type="button"
          className={activeWorkspace === 'groups' ? 'active' : ''}
          aria-current={activeWorkspace === 'groups' ? 'page' : undefined}
          onClick={() => setActiveWorkspace('groups')}
        >
          通知群組
        </button>
        <button
          type="button"
          className={activeWorkspace === 'operations' ? 'active' : ''}
          aria-current={activeWorkspace === 'operations' ? 'page' : undefined}
          onClick={() => setActiveWorkspace('operations')}
        >
          安全與人工升級
        </button>
      </nav>

      {activeWorkspace === 'groups' ? <>

      <section className="line-workspace-card alert-security-query-section" aria-labelledby="alert-targets-title">
        <div className="line-section-heading">
          <div>
            <h2 id="alert-targets-title">通知對象與目前狀態</h2>
            <p>重大異常的唯一群組廣播設定；顯示為啟用不代表訊息已送達。</p>
          </div>
          <button type="button" className="line-secondary-btn" onClick={() => setReloadKey((value) => value + 1)} disabled={loading || busy}>
            {loading ? '查詢中…' : '重新整理'}
          </button>
        </div>

        {errorMessage && <div className="line-error" role="alert">{errorMessage}</div>}
        {!loading && !errorMessage && targets.length === 0 && (
          <div className="line-empty-state compact">
            <strong>目前沒有已登錄的通知對象</strong>
            <span>通知對象會由正式 LINE 群組綁定流程建立；本頁不會自行新增或猜測群組。</span>
          </div>
        )}

        {!loading && groupTarget && (
          <>
            <div className="line-detail-grid alert-security-detail-grid">
              <div><span>目前綁定之群組名稱</span><strong>{groupTarget.display_label}</strong></div>
              <div><span>目前狀態</span><strong>{stateLabel(groupTarget.state)}</strong></div>
              <div><span>綁定／更新時間</span><strong>{groupTarget.updated_at}</strong></div>
            </div>
            <div className="line-events alert-security-lock-note">
              <h3>單一互斥鎖定保護</h3>
              <p className="alert-security-explanation">
                系統只允許一個啟用中的群組。新增或替換必須先檢查影響，並由已登入且啟用的內部使用者確認，
                不能由聊天室文字或畫面自行覆蓋正式設定。
              </p>
            </div>
          </>
        )}

        <div className="line-grid-cards">
          {targets.map((target) => (
            <article className="line-info-card" key={target.target_id}>
              <div className="line-section-heading">
                <strong>{target.display_label}</strong>
                <span className={`line-status ${target.state === 'active' ? 'line-status-resolved' : 'line-status-waiting'}`}>
                  {target.state === 'active' ? '啟用' : '停用'}
                </span>
              </div>
              <div className="line-detail-grid alert-security-detail-grid">
                <div><span>對象類型</span><strong>{target.target_kind === 'group' ? 'LINE 群組' : '內部使用者'}</strong></div>
                <div><span>通知範圍</span><strong>{minimumStatusLabel(target.minimum_status)}</strong></div>
                <div><span>更新時間</span><strong>{target.updated_at}</strong></div>
              </div>
              <div className="line-actions line-block-spacing">
                <button type="button" className="line-secondary-btn" onClick={() => void previewToggle(target)} disabled={busy}>
                  檢查{target.state === 'active' ? '停用' : '啟用'}影響
                </button>
              </div>
              {target.target_kind === 'group' && target.state !== 'active' && (
                <p className="field-hint">群組目前未啟用，因此不能重設；請先完成啟用流程。</p>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="line-workspace-card alert-security-change-section" aria-labelledby="alert-change-title">
        <div className="line-section-heading">
          <div>
            <h2 id="alert-change-title">通知對象異動</h2>
            <p>更換幹部群組前，必須先檢查影響，確認後才允許重新配對。</p>
          </div>
        </div>
        <label htmlFor="line-security-reason">異動原因</label>
        <textarea
          id="line-security-reason"
          className="line-textarea"
          rows={3}
          maxLength={240}
          value={reason}
          onChange={(event) => {
            setReason(event.target.value);
            clearCandidate();
          }}
          disabled={busy}
          aria-describedby="line-security-reason-help"
        />
        <div id="line-security-reason-help" className="field-hint alert-security-reason-help">
          <span>修改原因後必須重新檢查變更影響。</span>
          <span>{reason.length} / 240</span>
        </div>

        {groupTarget && (
        <div className="alert-security-reset-row">
          <div>
            <strong>重設異常通知群組</strong>
            <p className="field-hint">
              不直接清除資料；固定先檢查影響、明確確認、套用，再重新查詢結果。
            </p>
          </div>
          <button
            type="button"
            className="line-warning-btn"
            onClick={() => void previewGroupReset(groupTarget)}
            disabled={busy || groupTarget.state !== 'active'}
          >
            <RotateCcw aria-hidden="true" />檢查重設影響
          </button>
        </div>
        )}
        {groupTarget && groupTarget.state !== 'active' && (
          <p className="field-hint">群組目前未啟用，因此不能重設；請先完成啟用流程。</p>
        )}
      </section>

      {pending && (
        <div className="line-workspace-card alert-security-preview-card">
          <h3 className="alert-security-preview-title"><SearchCheck aria-hidden="true" />異動影響確認</h3>
          <div className="line-detail-grid alert-security-detail-grid">
            <div><span>操作</span><strong>{pending.kind === 'group_reset' ? '重設告警群組' : '變更通知啟用狀態'}</strong></div>
            <div><span>對象</span><strong>{pending.target.display_label}</strong></div>
            <div><span>目前狀態</span><strong>{stateLabel(pending.preview.previous_state)}</strong></div>
            <div><span>變更後狀態</span><strong>{stateLabel(pending.preview.resulting_state)}</strong></div>
          </div>
          <label className="checkbox-item line-block-spacing">
            <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            我已核對目前狀態、變更後狀態與影響範圍，確認套用此異動。
          </label>
          <div className="line-actions line-block-spacing">
            <button type="button" className="mock-primary-btn" onClick={() => void applyPending()} disabled={!confirmed || busy}>
              {busy ? '套用中…' : '確認套用'}
            </button>
            <button type="button" className="line-secondary-btn" onClick={clearCandidate} disabled={busy}>取消</button>
          </div>
        </div>
      )}

      {receipt && (
        <div className="line-success" role="status">
          <strong className="alert-security-receipt-title"><CheckCircle2 aria-hidden="true" />通知對象已更新</strong>
          <div>{stateLabel(receipt.previous_state)} → {stateLabel(receipt.resulting_state)}</div>
          {readbackMessage && <div>{readbackMessage}</div>}
        </div>
      )}
      </> : (
        <LineManagementPage runtimeOnly />
      )}
    </div>
  );
};
