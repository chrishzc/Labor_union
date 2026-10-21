import { useUnsavedDraft } from '../components/UnsavedChanges';
import { useRef } from 'react';
/** Audit & System storage-management surface with one-click cleanup and readback. */
import React, { useCallback, useEffect, useState } from 'react';
import {
  operationalRetentionClient,
  type RetentionDashboard,
  type RetentionMode,
  type RetentionPreview,
  type RetentionReceipt,
  type RetentionSource,
} from '../api/system/operational_retention_client';
import './StorageManagementPage.css';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && value >= 1024; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${unit}`;
}

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-TW') : '尚無';
}

function operationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${suffix}`;
}

function errorMessage(error: unknown): string {
  const status = Number((error as { status?: unknown })?.status ?? 0);
  const code = String((error as { code?: unknown })?.code ?? '');
  if (status === 401) return '登入狀態已失效，請重新登入。';
  if (status === 403) return '僅限最高權限管理員使用。請以具此權限的帳號登入。';
  if (code.includes('STALE')) return '資料已改變，請重新送出清理。';
  if (code.includes('UNCONFIGURED')) return '此來源尚未設定容量上限，無法執行容量清理。';
  if (code.includes('UNCLASSIFIED')) return '此來源尚未完成安全分類，系統不會刪除。';
  return '儲存空間服務暫時無法使用，請稍後重試。';
}

function capacityLabel(source: RetentionSource): string {
  if (source.capacity_status === 'high') return '超過容量上限';
  if (source.capacity_status === 'normal') return '容量正常';
  if (source.capacity_status === 'unavailable') return '容量無法讀取';
  return '尚未設定容量上限';
}

interface PreparedCleanup {
  readonly preview: RetentionPreview;
  readonly idempotencyKey: string;
  readonly correlationId: string;
}

export const StorageManagementPage: React.FC = () => {
  const [dashboard, setDashboard] = useState<RetentionDashboard | null>(null);
  const [selected, setSelected] = useState<RetentionSource | null>(null);
  const [mode, setMode] = useState<RetentionMode>('expired');
  const [reason, setReason] = useState('');
  const submittingRef = useRef(false);
  const [preview, setPreview] = useState<RetentionPreview | null>(null);
  const [receipt, setReceipt] = useState<RetentionReceipt | null>(null);
  const [pendingCleanup, setPendingCleanup] = useState<PreparedCleanup | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await operationalRetentionClient.dashboard();
      setDashboard(next);
      setSelected((current) => (
        current ? next.sources.find((item) => item.source_id === current.source_id) ?? null : null
      ));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const chooseSource = (source: RetentionSource) => {
    setSelected(source);
    setPreview(null);
    setReceipt(null);
    setError(null);
  };

  const applyPrepared = async (prepared: PreparedCleanup) => {
    try {
      const result = await operationalRetentionClient.apply(
        prepared.preview,
        prepared.idempotencyKey,
        prepared.correlationId,
      );
      setPendingCleanup(null);
      setReceipt(result);
      setPreview(null);
      await load();
    } catch (caught) {
      const status = Number((caught as { status?: unknown })?.status ?? 0);
      if (status === 0 || status >= 500) {
        setPendingCleanup(prepared);
        setError('清理結果尚待確認。請再次確認本次結果，系統會使用相同操作資料與識別碼。');
      } else {
        setPendingCleanup(null);
        setError(errorMessage(caught));
      }
    }
  };

  const saveCleanup = async () => {
    if (!selected || working || pendingCleanup || submittingRef.current) return;
    submittingRef.current = true;
    setWorking(true);
    setError(null);
    setReceipt(null);
    setPreview(null);
    try {
      const prepared = await operationalRetentionClient.preview({
        source_id: selected.source_id,
        mode,
        reason: reason.trim(),
        batch_size: 250,
      });
      setPreview(prepared);
      if (prepared.candidate_count === 0) return;
      await applyPrepared({
        preview: prepared,
        idempotencyKey: operationIdentity('retention-apply'),
        correlationId: operationIdentity('retention-correlation'),
      });
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      submittingRef.current = false;
      setWorking(false);
    }
  };

  const retryCleanup = async () => {
    if (!pendingCleanup || working || submittingRef.current) return;
    submittingRef.current = true;
    setWorking(true);
    setError(null);
    try {
      await applyPrepared(pendingCleanup);
    } finally {
      submittingRef.current = false;
      setWorking(false);
    }
  };
  useUnsavedDraft('儲存空間清理', { '清理模式': mode, '原因': reason }, { enabled: !!selected, busy: working, resetKey: receipt });


  return (
    <main className="storage-management-page" aria-labelledby="storage-management-title">
      <header className="storage-management-header">
        <div>
          <p className="storage-management-eyebrow">稽核與系統</p>
          <h1 id="storage-management-title">儲存空間管理</h1>
          <p>只管理系統紀錄、AI 客服使用紀錄與舊搜尋資料；會員、訂單、財務、合約及正式稽核證據不會被刪除。</p>
        </div>
        <button type="button" onClick={() => void load()} disabled={loading || working}>重新整理</button>
      </header>

      <section className="storage-policy-note" aria-label="保留政策">
        <strong>最長保留 30 天</strong>
        <span>到期自動清理；容量超過上限時，從允許清理的資料中優先移除最舊紀錄。資料庫回報的是可重新使用的空間，檔案大小不一定立即減少。</span>
      </section>

      {error && <div className="storage-error" role="alert">{error}</div>}
      {loading && <p role="status">正在讀取儲存空間…</p>}

      <section className="storage-source-grid" aria-label="可管理的儲存來源">
        {dashboard?.sources.map((source) => (
          <article className="storage-source-card" key={source.source_id} data-source-id={source.source_id}>
            <div className="storage-source-title-row">
              <h2>{source.label}</h2>
              <span className={`storage-capacity-badge ${source.capacity_status}`}>{capacityLabel(source)}</span>
            </div>
            <dl>
              <div><dt>目前用量</dt><dd>{formatBytes(source.current_logical_bytes)}</dd></div>
              <div><dt>已到期</dt><dd>{source.expired_count} 筆／檔</dd></div>
              <div><dt>預估可回收</dt><dd>{formatBytes(source.estimated_reclaimable_bytes)}</dd></div>
              <div><dt>最舊候選</dt><dd>{formatTime(source.oldest_eligible_at_utc)}</dd></div>
              <div><dt>最近清理</dt><dd>{formatTime(source.last_run_at_utc)}</dd></div>
              <div><dt>最近結果</dt><dd>{source.last_outcome ?? '尚無'}</dd></div>
            </dl>
            {source.blocked_reason && <p className="storage-blocked">{source.blocked_reason}</p>}
            <button
              type="button"
              onClick={() => chooseSource(source)}
              disabled={source.classification !== 'eligible' || working || !!pendingCleanup}
            >
              設定清理
            </button>
          </article>
        ))}
      </section>

      {selected && (
        <section className="storage-cleanup-panel" aria-labelledby="storage-cleanup-title">
          <h2 id="storage-cleanup-title">清理：{selected.label}</h2>
          <div className="storage-form-grid">
            <label>
              清理模式
              <select value={mode} disabled={working || !!pendingCleanup} onChange={(event) => { setMode(event.target.value as RetentionMode); setPreview(null); }}>
                <option value="expired">清理已滿 30 天資料</option>
                <option value="capacity">容量超標時優先清理最舊紀錄</option>
              </select>
            </label>
            <label>
              操作原因（選填）
              <input value={reason} maxLength={500} disabled={working || !!pendingCleanup} onChange={(event) => { setReason(event.target.value); setPreview(null); }} />
            </label>
          </div>
          <button className="storage-danger" type="button" onClick={() => void saveCleanup()} disabled={working || !!pendingCleanup}>
            {working ? '正在清理…' : '清理資料'}
          </button>

          {preview?.candidate_count === 0 && (
            <div className="storage-preview" role="status">
              <p>目前沒有符合條件的資料。</p>
            </div>
          )}
          {pendingCleanup && (
            <button type="button" onClick={() => void retryCleanup()} disabled={working}>再次確認清理結果</button>
          )}
        </section>
      )}

      {receipt && (
        <section className={`storage-receipt ${receipt.outcome}`} aria-label="清理 readback" role="status">
          <h2>清理 readback</h2>
          <p>結果：{receipt.outcome}；刪除 {receipt.deleted_count}，失敗 {receipt.failed_count}，釋放可重新使用的空間 {formatBytes(receipt.deleted_logical_bytes)}。</p>
          <p>Correlation：{receipt.correlation_id}</p>
        </section>
      )}
    </main>
  );
};

export default StorageManagementPage;
