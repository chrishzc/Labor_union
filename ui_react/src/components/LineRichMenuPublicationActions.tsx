/**
 * File: LineRichMenuPublicationActions.tsx
 * Description: 提供 Rich Menu 發布 Preview、人工確認 queue 與可重試失敗的 durable retry 操作。
 */
import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle2, LockKeyhole, RefreshCw, Rocket, SearchCheck, TriangleAlert } from 'lucide-react';
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
      return '選單草稿或版本已變更，先前的發布預覽已過期；請重新檢查發布影響後，再勾選確認發布。';
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
          <h4 className="richmenu-editor-title">
            <Rocket aria-hidden="true" />Rich Menu 發布操作
          </h4>
          <p className="richmenu-editor-description">
             {selectedMenu ? `目前選單：${selectedMenu.name}` : '請先由上方選擇要發布的 Rich Menu'}
          </p>
        </div>
        {selectedMenu && (
          <div className="richmenu-publish-actions">
            <button
              type="button"
              className="line-secondary-btn"
              disabled={busy}
              onClick={() => void runPreview()}
            >
              <SearchCheck aria-hidden="true" />{previewState === 'loading' ? '檢查中…' : '檢查發布影響'}
            </button>
          </div>
        )}
      </div>

      {previewState === 'loading' && <div className="line-loading" role="status">正在檢查發布影響…</div>}
      {preview && (
        <div className="richmenu-preview-box">
          <div className="richmenu-publish-preview-heading">
            <strong><CheckCircle2 aria-hidden="true" />發布影響已確認</strong>
          </div>
          <p className="richmenu-publish-preview-description">
             選單設定已通過檢查，請核對影響範圍後發布。
          </p>

          <label htmlFor="line-rich-menu-publish-reason" className="richmenu-publish-field-label">
            發布原因
          </label>
          <input
            id="line-rich-menu-publish-reason"
            aria-label="發布原因"
            value={publishReason}
            maxLength={500}
            disabled={busy}
            placeholder="例如：工會人員更新圖文選單設定"
            className="richmenu-form-input richmenu-publish-reason"
            onChange={(event) => {
              setPublishReason(event.target.value);
            }}
          />
          <label className="richmenu-confirm-checkbox-label richmenu-publish-confirm">
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
            className="line-primary-btn richmenu-publish-submit"
            disabled={busy || Boolean(publicationAccess) || !publishConfirmed || publishReason.trim().length === 0}
            onClick={() => void queuePublication()}
          >
            <Rocket aria-hidden="true" />確認排入異步發布
          </button>
        </div>
      )}

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
            重試原因
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
              setRetryConfirmed(false);
              setRetryState('idle');
            }}
          />
          <label className="richmenu-confirm-checkbox-label richmenu-publish-confirm">
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
            className="line-warning-btn richmenu-publish-submit"
            disabled={busy || Boolean(publicationAccess) || !retryConfirmed || retryReason.trim().length === 0}
            onClick={() => void retryPublication()}
          >
            <RefreshCw aria-hidden="true" />確認重新排入發布
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
