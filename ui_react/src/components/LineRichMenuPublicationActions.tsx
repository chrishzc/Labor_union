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

function publicationAccessMessage(): string | null {
  const user = sessionClient.getUser();
  if (!user) return '請先登入已啟用的內部使用者帳號，再排入發布工作。';
  if (user.id === null) {
    return '本機免驗證模式不可發布；請改用真實已登入的管理員 Session。';
  }
  return null;
}

function uniqueOperationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function displayError(error: unknown): string {
  if (error instanceof LineRichMenuPublicationError) {
    if (error.category === 'forbidden') {
      return '目前登入狀態不能排入發布工作；本機免驗證模式不可發布，其他情況請重新登入已啟用的內部使用者帳號。';
    }
    if (error.code === 'rich_menu_preview_stale') {
      return '選單草稿或版本已變更，先前的發布預覽已過期；請點擊右上角「🔍 檢查發布影響」重新預覽後，再勾選確認發布。';
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
    setErrorMessage(null);
    try {
      const result = await client.preview(selectedMenu.id, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setPreview(adaptLineRichMenuPublishPreview(result));
      setPublishConfirmed(false);
      if (!publishReason.trim()) {
        setPublishReason('工會人員更新圖文選單設定');
      }
      setPreviewState('success');
    } catch (error) {
      if (controller.signal.aborted) return;
      setPreviewState('error');
      setErrorMessage(displayError(error));
    }
  };

  const queuePublication = async (): Promise<void> => {
    if (!selectedMenu || !publishConfirmed) return;
    const effectiveReason = publishReason.trim() || '工會人員更新圖文選單設定';
    const controller = new AbortController();
    controllerRef.current = controller;
    setPublishState('loading');
    setReceipt(null);
    setErrorMessage(null);
    try {
      let activePreview = preview;
      if (!activePreview) {
        const previewResult = await client.preview(selectedMenu.id, { signal: controller.signal });
        activePreview = adaptLineRichMenuPublishPreview(previewResult);
        setPreview(activePreview);
      }

      let result;
      try {
        result = await client.publish(
          selectedMenu.id,
          {
            preview_id: activePreview.previewId,
            reason: effectiveReason,
            idempotency_key: uniqueOperationIdentity('line-rich-menu-publish-idem'),
            correlation_id: uniqueOperationIdentity('line-rich-menu-publish-corr'),
          },
          { signal: controller.signal }
        );
      } catch (publishErr) {
        if (publishErr instanceof LineRichMenuPublicationError && publishErr.code === 'rich_menu_preview_stale') {
          // 自動重新獲取最新預覽並重試發布
          const freshPreviewResult = await client.preview(selectedMenu.id, { signal: controller.signal });
          activePreview = adaptLineRichMenuPublishPreview(freshPreviewResult);
          setPreview(activePreview);
          result = await client.publish(
            selectedMenu.id,
            {
              preview_id: activePreview.previewId,
              reason: effectiveReason,
              idempotency_key: uniqueOperationIdentity('line-rich-menu-publish-idem'),
              correlation_id: uniqueOperationIdentity('line-rich-menu-publish-corr'),
            },
            { signal: controller.signal }
          );
        } else {
          throw publishErr;
        }
      }

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
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              type="button"
              className="line-primary-btn"
              disabled={busy || Boolean(publicationAccess)}
              onClick={() => {
                setPublishConfirmed(true);
                void queuePublication();
              }}
              style={{
                padding: '8px 20px',
                fontSize: '0.9rem',
                fontWeight: 700,
                background: '#ea580c',
                color: '#fff',
                border: 0,
                borderRadius: '8px',
                cursor: busy ? 'not-allowed' : 'pointer',
              }}
            >
              {publishState === 'loading' ? '正在發布至 LINE…' : '🚀 發布至 LINE'}
            </button>
            <button
              type="button"
              className="line-secondary-btn"
              disabled={busy}
              onClick={() => void runPreview()}
              style={{ padding: '8px 12px', fontSize: '0.82rem' }}
            >
              🔍 檢查發布影響
            </button>
          </div>
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
            發布原因
          </label>
          <input
            id="line-rich-menu-publish-reason"
            aria-label="發布原因"
            value={publishReason}
            maxLength={500}
            disabled={busy}
            placeholder="例如：工會人員更新圖文選單設定"
            style={{ width: '100%', padding: '8px', border: '1px solid #dec0b6', borderRadius: '8px', fontSize: '0.85rem', boxSizing: 'border-box', marginBottom: '8px' }}
            onChange={(event) => {
              setPublishReason(event.target.value);
            }}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.82rem', color: '#57423b', margin: '8px 0' }}>
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
            style={{ width: '100%', padding: '10px', background: '#ea580c', color: '#fff', border: 0, borderRadius: '8px', fontWeight: 700, cursor: 'pointer' }}
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
