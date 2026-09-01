/**
 * File: SafeReviewLinkWorkbench.tsx
 * Description: M4 管理端／行動端安全審核連結去敏 readback 與一次性操作入口。
 */

import { useState } from 'react';
import { safeReviewLinkClient, type SafeReviewLinkClient } from '../api/line_safe_review_link/line_safe_review_link_client';
import { SafeReviewLinkClientError } from '../api/line_safe_review_link/line_safe_review_link_errors';
import type { SafeReviewLink, SafeReviewLinkReceipt } from '../api/line_safe_review_link/line_safe_review_link_schemas';

interface Props { client?: SafeReviewLinkClient; }

function operationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function errorText(error: unknown): string {
  if (error instanceof SafeReviewLinkClientError) return `${error.publicCode ?? error.code}：${error.message}`;
  return '安全審核連結操作失敗，請依 readback 的失敗原因處理。';
}

function statusLabel(status: SafeReviewLink['status']): string {
  return { issued: '待審核', redeemed: '已使用', expired: '已過期', revoked: '已撤銷' }[status];
}

export function SafeReviewLinkWorkbench({ client = safeReviewLinkClient }: Props) {
  const [linkId, setLinkId] = useState('');
  const [rawToken, setRawToken] = useState('');
  const [capability, setCapability] = useState('line.alert.manage');
  const [target, setTarget] = useState('');
  const [targetVersion, setTargetVersion] = useState('0');
  const [revokeReason, setRevokeReason] = useState('');
  const [view, setView] = useState<SafeReviewLink | null>(null);
  const [receipt, setReceipt] = useState<SafeReviewLinkReceipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = async () => {
    if (!linkId.trim()) return;
    setBusy(true); setError(null); setReceipt(null);
    try { setView(await client.query(linkId.trim(), { correlationId: operationIdentity('safe-review-query') })); }
    catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  };

  const redeem = async () => {
    const version = Number(targetVersion);
    if (!linkId.trim() || !rawToken.trim() || !capability.trim() || !target.trim() || !Number.isInteger(version) || version < 0) return;
    setBusy(true); setError(null);
    try {
      const next = await client.redeem(linkId.trim(), {
        raw_token: rawToken,
        capability: capability.trim(),
        current_target: target.trim(),
        current_target_version: version,
        idempotency_key: operationIdentity('safe-review-redeem'),
        correlation_id: operationIdentity('safe-review-redeem-correlation'),
      });
      setReceipt(next); setView(next.readback); setRawToken('');
    } catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  };

  const revoke = async () => {
    if (!linkId.trim() || !revokeReason.trim()) return;
    setBusy(true); setError(null);
    try {
      const next = await client.revoke(linkId.trim(), {
        reason: revokeReason.trim(),
        idempotency_key: operationIdentity('safe-review-revoke'),
        correlation_id: operationIdentity('safe-review-revoke-correlation'),
      });
      setReceipt(next); setView(next.readback);
    } catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  };

  return (
    <section className="line-workspace-card" data-control-id="line.safe-review-link.workbench">
      <div className="line-section-heading">
        <div>
          <h3>🔐 M4 安全審核連結</h3>
          <p>管理端／行動端只讀回去敏目標與一次性結果；原 token 不會由回應或畫面保存。</p>
        </div>
      </div>
      <div className="line-detail-grid">
        <label>連結識別 <input className="line-search-input" value={linkId} onChange={(event) => setLinkId(event.target.value)} /></label>
        <label>目前目標路徑 <input className="line-search-input" value={target} onChange={(event) => setTarget(event.target.value)} placeholder="/api/v1/runtime/health-status" /></label>
        <label>目標版本 <input className="line-search-input" inputMode="numeric" value={targetVersion} onChange={(event) => setTargetVersion(event.target.value)} /></label>
        <label>審核能力 <input className="line-search-input" value={capability} onChange={(event) => setCapability(event.target.value)} /></label>
      </div>
      <div className="line-detail-grid" style={{ marginTop: '10px' }}>
        <label>一次性 token（僅本次記憶體操作） <input className="line-search-input" type="password" value={rawToken} onChange={(event) => setRawToken(event.target.value)} autoComplete="off" /></label>
        <label>撤銷原因 <input className="line-search-input" value={revokeReason} onChange={(event) => setRevokeReason(event.target.value)} maxLength={500} /></label>
      </div>
      <div className="line-row-actions" style={{ marginTop: '12px' }}>
        <button type="button" className="line-secondary-btn" onClick={() => void query()} disabled={busy || !linkId.trim()}>查詢去敏狀態</button>
        <button type="button" className="line-primary-btn" onClick={() => void redeem()} disabled={busy || !linkId.trim() || !rawToken.trim() || !target.trim()}>確認使用審核連結</button>
        <button type="button" className="line-secondary-btn" onClick={() => void revoke()} disabled={busy || !linkId.trim() || !revokeReason.trim()}>撤銷審核連結</button>
      </div>
      {error && <p className="line-error" role="alert">{error}</p>}
      {receipt && <p className="line-success" role="status">已收到 {receipt.outcome} readback；receipt：{receipt.receipt_id}{receipt.replayed ? '（重播）' : ''}</p>}
      {view && <dl className="line-detail-grid" data-surface-id="line.safe-review-link.readback">
        <div><dt>目前狀態</dt><dd>{statusLabel(view.status)}</dd></div>
        <div><dt>審核目標</dt><dd>{view.canonical_internal_target}</dd></div>
        <div><dt>來源警示</dt><dd>{view.source_alert_identity}</dd></div>
        <div><dt>到期時間</dt><dd>{view.expires_at_utc}</dd></div>
        <div><dt>根版本</dt><dd>{view.root_version}</dd></div>
        {view.redeemed_at_utc && <div><dt>使用時間</dt><dd>{view.redeemed_at_utc}</dd></div>}
        {view.revoked_at_utc && <div><dt>撤銷時間</dt><dd>{view.revoked_at_utc}</dd></div>}
      </dl>}
    </section>
  );
}

export default SafeReviewLinkWorkbench;
