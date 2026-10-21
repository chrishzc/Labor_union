import { useUnsavedDraft } from './UnsavedChanges';
/**
 * File: LineRichMenuPublicationActions.tsx
 * Description: 提供 Rich Menu 發布檢查與一次點擊 queue 與可重試失敗的 durable retry 操作。
 */
import React, { useEffect, useRef, useState } from 'react';
import { LockKeyhole, RefreshCw, Rocket, TriangleAlert } from 'lucide-react';
import {
  adaptLineRichMenuPublicationReceipt,
  type LineRichMenuPublicationReceiptModel,
} from '../adapters/line_rich_menu_publication/line_rich_menu_publication_adapter';
import {
  lineRichMenuPublicationClient,
  type LineRichMenuPublicationClient,
} from '../api/line_rich_menu_publication/line_rich_menu_publication_client';
import { LineRichMenuPublicationError } from '../api/line_rich_menu_publication/line_rich_menu_publication_errors';
import type { LineRichMenuPublishRequest, LineRichMenuRetryRequest } from '../api/line_rich_menu_publication/line_rich_menu_publication_schemas';
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
      return '選單草稿或版本已變更，先前的發布預覽已過期；請重新查詢後再發布。';
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
  const [publishReason, setPublishReason] = useState('');
  const [publishState, setPublishState] = useState<OperationState>('idle');
  const [retryReason, setRetryReason] = useState('');
  const [retryState, setRetryState] = useState<OperationState>('idle');
  const [receipt, setReceipt] = useState<LineRichMenuPublicationReceiptModel | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const publicationAccess = publicationAccessMessage();
  const publishIntent = useRef<{ signature: string; command: LineRichMenuPublishRequest } | null>(null);
  const retryIntent = useRef<{ signature: string; command: LineRichMenuRetryRequest } | null>(null);

  useEffect(() => {
    controllerRef.current?.abort();
    publishIntent.current = null;
    setPublishReason('');
    setPublishState('idle');
    setReceipt(null);
    setErrorMessage(null);
  }, [selectedMenu?.id]);

  useEffect(() => {
    retryIntent.current = null;
    setRetryReason('');
    setRetryState('idle');
    setErrorMessage(null);
  }, [selectedPublication?.id, selectedPublication?.status]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const queuePublication = async (): Promise<void> => {
    if (!selectedMenu || busy || publicationAccess) return;
    const effectiveReason = publishReason.trim();
    const controller = new AbortController();
    controllerRef.current = controller;
    setPublishState('loading');
    setReceipt(null);
    setErrorMessage(null);
    try {
      const signature = JSON.stringify([selectedMenu.id, effectiveReason]);
      if (publishIntent.current?.signature !== signature) {
        const preview = await client.preview(selectedMenu.id, { signal: controller.signal });
        if (controller.signal.aborted) return;
        publishIntent.current = { signature, command: {
          preview_id: preview.preview_id, reason: effectiveReason,
          idempotency_key: uniqueOperationIdentity('line-rich-menu-publish-idem'),
          correlation_id: uniqueOperationIdentity('line-rich-menu-publish-corr'),
        } };
      }
      const result = await client.publish(selectedMenu.id, publishIntent.current.command, { signal: controller.signal });

      if (controller.signal.aborted) return;
      const nextReceipt = adaptLineRichMenuPublicationReceipt(result);
      setReceipt(nextReceipt);
      publishIntent.current = null;
      setPublishState('success');
      onQueued?.(nextReceipt);
    } catch (error) {
      if (controller.signal.aborted) return;

      if (error instanceof LineRichMenuPublicationError && error.category === 'conflict') publishIntent.current = null;
      setPublishState('error');
      setErrorMessage(displayError(error));
    }
  };

  const retryPublication = async (): Promise<void> => {
    if (
      selectedPublication?.status !== 'publish_retryable_failed'
      || busy || publicationAccess
    ) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setRetryState('loading');
    setReceipt(null);
    setErrorMessage(null);
    try {
      const signature = JSON.stringify([selectedPublication.id, retryReason.trim()]);
      if (retryIntent.current?.signature !== signature) retryIntent.current = { signature, command: {
        reason: retryReason.trim(),
        idempotency_key: uniqueOperationIdentity('line-rich-menu-retry-idem'),
        correlation_id: uniqueOperationIdentity('line-rich-menu-retry-corr'),
      } };
      const result = await client.retry(selectedPublication.id, retryIntent.current.command, { signal: controller.signal });
      if (controller.signal.aborted) return;
      const nextReceipt = adaptLineRichMenuPublicationReceipt(result);
      setReceipt(nextReceipt);
      retryIntent.current = null;
      setRetryState('success');
      onQueued?.(nextReceipt);
    } catch (error) {
      if (controller.signal.aborted) return;
      setRetryState('error');
      setErrorMessage(displayError(error));
    }
  };

  const busy = publishState === 'loading' || retryState === 'loading';
  useUnsavedDraft('圖文選單發布', { '發布原因': publishReason, '重試原因': retryReason }, { busy, resetKey: receipt });


  return (
    <section className="richmenu-publish-card" aria-label="Rich Menu 發布操作">
      <div className="richmenu-publish-header">
        <div>
          <h4 className="richmenu-editor-title">
            <Rocket aria-hidden="true" />{selectedMenu ? '發布選單' : '重新發布'}
          </h4>
          <p className="richmenu-editor-description">
             {selectedMenu ? `目前選單：${selectedMenu.name}` : '確認此筆失敗紀錄後重新排入發布。'}
          </p>
        </div>
      </div>
      {selectedMenu && <div className="richmenu-preview-box">
        <label htmlFor="line-rich-menu-publish-reason" className="richmenu-publish-field-label">發布原因（選填）</label>
        <input id="line-rich-menu-publish-reason" aria-label="發布原因（選填）" value={publishReason} maxLength={500} disabled={busy} className="richmenu-form-input richmenu-publish-reason" onChange={(event) => setPublishReason(event.target.value)} />
        <button type="button" className="line-primary-btn richmenu-publish-submit" data-control-id="line.richmenu.publish" disabled={busy || Boolean(publicationAccess)} onClick={() => void queuePublication()}><Rocket aria-hidden="true" />發布至 LINE</button>
      </div>}

      {publicationAccess && (
        <div className="line-error richmenu-publish-message" role="note">
          <LockKeyhole aria-hidden="true" />{publicationAccess}
        </div>
      )}

      {selectedPublication?.status === 'publish_retryable_failed' && (
        <div className="richmenu-preview-box richmenu-retry-box">
          <strong className="richmenu-retry-title"><TriangleAlert aria-hidden="true" />此選單發布可重新排入</strong>
          <p className="richmenu-retry-status">目前狀態：{selectedPublication.statusLabel}</p>
          <label htmlFor={`line-rich-menu-retry-reason-${selectedPublication.id}`} className="richmenu-publish-field-label">
            重試原因（選填）
          </label>
          <textarea
            id={`line-rich-menu-retry-reason-${selectedPublication.id}`}
            value={retryReason}
            rows={2}
            maxLength={500}
            disabled={busy}
            className="richmenu-form-textarea"
            onChange={(event) => {
              setRetryReason(event.target.value);
              setRetryState('idle');
            }}
          />
          <button
            type="button"
            className="line-warning-btn richmenu-publish-submit"
            disabled={busy || Boolean(publicationAccess)}
            onClick={() => void retryPublication()}
          >
            <RefreshCw aria-hidden="true" />重新排入發布
          </button>
        </div>
      )}

      {(publishState === 'loading' || retryState === 'loading') && (
        <div className="line-loading" role="status">正在排入發布工作…</div>
      )}
      {receipt && (
        <div className="line-success richmenu-publish-message" role="status">
          <strong>選單發布：{receipt.statusLabel}</strong>
          <p className="richmenu-publish-receipt-help">已排入發布工作；尚未代表 LINE 平台已完成發布。</p>
        </div>
      )}
      {errorMessage && <div className="line-error richmenu-publish-message" role="alert">{errorMessage}</div>}
    </section>
  );
};

export default LineRichMenuPublicationActions;
