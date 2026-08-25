/**
 * File: LineRichMenuPublicationActions.tsx
 * Description: 提供 Rich Menu 發布 Preview、人工確認 queue 與可重試失敗的 durable retry 操作。
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  adaptLineRichMenuPublicationReceipt,
  adaptLineRichMenuPublishPreview,
  type LineRichMenuPublicationReceiptModel,
  type LineRichMenuPublishPreviewModel,
} from '../adapters/line_rich_menu_publication/line_rich_menu_publication_adapter';
import {
  lineRichMenuPublicationClient,
  type LineRichMenuPublicationClient,
} from '../api/line_rich_menu_publication/line_rich_menu_publication_client';
import { LineRichMenuPublicationError } from '../api/line_rich_menu_publication/line_rich_menu_publication_errors';
import { sessionClient } from '../api/auth/session_client';

export interface LineRichMenuPublicationMenu {
  id: string;
  name: string;
}

export interface LineRichMenuRetryPublication {
  id: number;
  menuDefinitionId: string;
  status: string;
  statusLabel: string;
}

export interface LineRichMenuPublicationActionsProps {
  selectedMenu: LineRichMenuPublicationMenu | null;
  selectedPublication?: LineRichMenuRetryPublication | null;
  client?: LineRichMenuPublicationClient;
  onQueued?: (receipt: LineRichMenuPublicationReceiptModel) => void;
}

type OperationState = 'idle' | 'loading' | 'success' | 'error';

const RICH_MENU_PUBLISH_CAPABILITIES = new Set([
  'line.menu.publish',
  'line.rich_menu.publish',
]);

function publicationAccessMessage(): string | null {
  const user = sessionClient.getUser();
  if (!user) return null;
  if (user.capabilities.some((capability) => RICH_MENU_PUBLISH_CAPABILITIES.has(capability))) {
    return null;
  }
  if (user.id === null) {
    return '本機免驗證模式不可發布；請改用真實已登入的管理員 Session。';
  }
  return '目前登入的管理員 Session 沒有 Rich Menu 發布能力；請改用具發布能力的管理員 Session。';
}

function uniqueOperationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function displayError(error: unknown): string {
  if (error instanceof LineRichMenuPublicationError) {
    if (error.category === 'forbidden') {
      return '目前登入的管理員 Session 沒有 Rich Menu 發布能力；若目前使用本機免驗證模式，該模式不可發布，請改用真實已登入的管理員 Session。';
    }
    return `${error.code}：${error.message}`;
  }
  return error instanceof Error ? error.message : 'Rich Menu 發布操作失敗，請重新查詢後再試。';
}

export const LineRichMenuPublicationActions: React.FC<LineRichMenuPublicationActionsProps> = ({
  selectedMenu,
  selectedPublication = null,
  client = lineRichMenuPublicationClient,
  onQueued,
}) => {
  const [preview, setPreview] = useState<LineRichMenuPublishPreviewModel | null>(null);
  const [previewState, setPreviewState] = useState<OperationState>('idle');
  const [publishReason, setPublishReason] = useState('');
  const [publishConfirmed, setPublishConfirmed] = useState(false);
  const [publishState, setPublishState] = useState<OperationState>('idle');
  const [retryReason, setRetryReason] = useState('');
  const [retryConfirmed, setRetryConfirmed] = useState(false);
  const [retryState, setRetryState] = useState<OperationState>('idle');
  const [receipt, setReceipt] = useState<LineRichMenuPublicationReceiptModel | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const publicationAccess = publicationAccessMessage();

  useEffect(() => {
    controllerRef.current?.abort();
    setPreview(null);
    setPreviewState('idle');
    setPublishReason('');
    setPublishConfirmed(false);
    setPublishState('idle');
    setReceipt(null);
    setErrorMessage(null);
  }, [selectedMenu?.id]);

  useEffect(() => {
    setRetryReason('');
    setRetryConfirmed(false);
    setRetryState('idle');
    setErrorMessage(null);
  }, [selectedPublication?.id, selectedPublication?.status]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const runPreview = async (): Promise<void> => {
    if (!selectedMenu) return;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setPreviewState('loading');
    setPreview(null);
    setReceipt(null);
    setPublishConfirmed(false);
    setErrorMessage(null);
    try {
      const result = await client.preview(selectedMenu.id, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setPreview(adaptLineRichMenuPublishPreview(result));
      setPreviewState('success');
    } catch (error) {
      if (controller.signal.aborted) return;
      setPreviewState('error');
      setErrorMessage(displayError(error));
    }
  };

  const queuePublication = async (): Promise<void> => {
    if (!selectedMenu || !preview || !publishConfirmed || !publishReason.trim()) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setPublishState('loading');
    setReceipt(null);
    setErrorMessage(null);
    try {
      const result = await client.publish(
        selectedMenu.id,
        {
          preview_id: preview.previewId,
          reason: publishReason.trim(),
          idempotency_key: uniqueOperationIdentity('line-rich-menu-publish-idem'),
          correlation_id: uniqueOperationIdentity('line-rich-menu-publish-corr'),
        },
        { signal: controller.signal }
      );
      if (controller.signal.aborted) return;
      const nextReceipt = adaptLineRichMenuPublicationReceipt(result);
      setReceipt(nextReceipt);
      setPublishConfirmed(false);
      setPublishState('success');
      onQueued?.(nextReceipt);
    } catch (error) {
      if (controller.signal.aborted) return;
      setPublishState('error');
      setErrorMessage(displayError(error));
    }
  };

  const retryPublication = async (): Promise<void> => {
    if (
      selectedPublication?.status !== 'publish_retryable_failed'
      || !retryConfirmed
      || !retryReason.trim()
    ) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setRetryState('loading');
    setReceipt(null);
    setErrorMessage(null);
    try {
      const result = await client.retry(
        selectedPublication.id,
        {
          reason: retryReason.trim(),
          idempotency_key: uniqueOperationIdentity('line-rich-menu-retry-idem'),
          correlation_id: uniqueOperationIdentity('line-rich-menu-retry-corr'),
        },
        { signal: controller.signal }
      );
      if (controller.signal.aborted) return;
      const nextReceipt = adaptLineRichMenuPublicationReceipt(result);
      setReceipt(nextReceipt);
      setRetryConfirmed(false);
      setRetryState('success');
      onQueued?.(nextReceipt);
    } catch (error) {
      if (controller.signal.aborted) return;
      setRetryState('error');
      setErrorMessage(displayError(error));
    }
  };

  const busy = previewState === 'loading' || publishState === 'loading' || retryState === 'loading';

  return (
    <section className="richmenu-publish-card" aria-label="Rich Menu 發布操作">
      <div className="richmenu-publish-header">
        <div>
          <h4 style={{ margin: 0, fontSize: '1.05rem', color: '#1e1b19', fontWeight: 700 }}>
            🚀 Rich Menu 發布操作
          </h4>
          <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: '#74593f' }}>
             {selectedMenu ? `目前選單：${selectedMenu.name}` : '請先由上方選擇要發布的 Rich Menu'}
          </p>
        </div>
        {selectedMenu && (
          <button
            type="button"
            className="line-secondary-btn"
            disabled={busy}
            onClick={() => void runPreview()}
            style={{ padding: '6px 14px', fontSize: '0.85rem' }}
          >
            🔍 檢查發布影響
          </button>
        )}
      </div>

      {previewState === 'loading' && <div className="line-loading" role="status">正在檢查發布影響…</div>}
      {preview && (
        <div className="richmenu-preview-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <strong style={{ color: '#166534', fontSize: '0.9rem' }}>✅ 發布影響已確認</strong>
          </div>
          <p style={{ fontSize: '0.78rem', color: '#74593f', fontFamily: 'monospace', margin: '4px 0 10px', wordBreak: 'break-all' }}>
             選單設定已通過檢查，請核對影響範圍後發布。
          </p>

          <label htmlFor="line-rich-menu-publish-reason" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: '#57423b', marginBottom: '4px' }}>
            發布原因說明
          </label>
          <textarea
            id="line-rich-menu-publish-reason"
            value={publishReason}
            rows={2}
            maxLength={500}
            disabled={busy}
            placeholder="例如：更新秋季月嫂媒合方案與線上補助試算連結..."
            style={{ width: '100%', padding: '8px', border: '1px solid #dec0b6', borderRadius: '8px', fontSize: '0.85rem', boxSizing: 'border-box' }}
            onChange={(event) => {
              setPublishReason(event.target.value);
              setPublishConfirmed(false);
              setPublishState('idle');
            }}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.82rem', color: '#57423b', margin: '10px 0' }}>
            <input
              type="checkbox"
              checked={publishConfirmed}
              disabled={busy}
              onChange={(event) => setPublishConfirmed(event.target.checked)}
            />
            我已確認選單內容與影響範圍，同意排入發布序列
          </label>
          <button
            type="button"
            style={{ width: '100%', padding: '10px', background: '#ff7f50', color: '#fff', border: 0, borderRadius: '8px', fontWeight: 700, cursor: 'pointer' }}
            disabled={busy || Boolean(publicationAccess) || !publishConfirmed || publishReason.trim().length === 0}
            onClick={() => void queuePublication()}
          >
            🚀 確認排入異步發布
          </button>
        </div>
      )}

      {publicationAccess && (
        <div className="line-error" role="note" style={{ marginTop: '10px' }}>
          🔒 {publicationAccess}
        </div>
      )}

      {selectedPublication?.status === 'publish_retryable_failed' && (
        <div className="richmenu-preview-box" style={{ borderColor: '#fecdd3', background: '#fff5f5' }}>
          <strong style={{ color: '#991b1b' }}>⚠️ 此選單發布可重新排入</strong>
          <p style={{ fontSize: '0.82rem', margin: '4px 0 8px' }}>目前狀態：{selectedPublication.statusLabel}</p>
          <label htmlFor={`line-rich-menu-retry-reason-${selectedPublication.id}`} style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700 }}>
            重試原因
          </label>
          <textarea
            id={`line-rich-menu-retry-reason-${selectedPublication.id}`}
            value={retryReason}
            rows={2}
            maxLength={500}
            disabled={busy}
            style={{ width: '100%', padding: '8px', border: '1px solid #dec0b6', borderRadius: '8px', fontSize: '0.85rem', boxSizing: 'border-box' }}
            onChange={(event) => {
              setRetryReason(event.target.value);
              setRetryConfirmed(false);
              setRetryState('idle');
            }}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.82rem', margin: '8px 0' }}>
            <input
              type="checkbox"
              checked={retryConfirmed}
              disabled={busy}
              onChange={(event) => setRetryConfirmed(event.target.checked)}
            />
            我已確認此紀錄為發布可重試失敗
          </label>
          <button
            type="button"
            style={{ width: '100%', padding: '10px', background: '#ea580c', color: '#fff', border: 0, borderRadius: '8px', fontWeight: 700, cursor: 'pointer' }}
            disabled={busy || Boolean(publicationAccess) || !retryConfirmed || retryReason.trim().length === 0}
            onClick={() => void retryPublication()}
          >
            🔄 確認重新排入發布
          </button>
        </div>
      )}

      {(publishState === 'loading' || retryState === 'loading') && (
        <div className="line-loading" role="status">正在排入發布工作…</div>
      )}
      {receipt && (
        <div className="line-success" role="status" style={{ marginTop: '10px' }}>
          <strong>選單發布：{receipt.statusLabel}</strong>
          <p style={{ margin: '4px 0 0', fontSize: '0.82rem' }}>已排入發布工作；尚未代表 LINE 平台已完成發布。</p>
        </div>
      )}
      {errorMessage && <div className="line-error" role="alert" style={{ marginTop: '10px' }}>{errorMessage}</div>}
    </section>
  );
};

export default LineRichMenuPublicationActions;
