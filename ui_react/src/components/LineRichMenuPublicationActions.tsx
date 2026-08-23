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

function uniqueOperationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function displayError(error: unknown): string {
  if (error instanceof LineRichMenuPublicationError) {
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
    <section className="line-action-panel" aria-label="Rich Menu 發布操作">
      <h4>發布操作</h4>
      {selectedMenu ? (
        <>
          <p>目前選單：{selectedMenu.name}（{selectedMenu.id}）</p>
          <button type="button" disabled={busy} onClick={() => void runPreview()}>
            預覽發布
          </button>
        </>
      ) : <p>請先選擇要發布的 Rich Menu。</p>}

      {previewState === 'loading' && <div role="status">正在建立零寫入發布預覽…</div>}
      {preview && (
        <div className="line-preview-result">
          <strong>預覽已就緒</strong>
          <p>設定版本：{preview.configurationRevision}</p>
          <p>設定指紋摘要：{preview.fingerprintSummary}</p>
          <label htmlFor="line-rich-menu-publish-reason">發布原因</label>
          <textarea
            id="line-rich-menu-publish-reason"
            value={publishReason}
            rows={3}
            maxLength={500}
            disabled={busy}
            onChange={(event) => {
              setPublishReason(event.target.value);
              setPublishConfirmed(false);
              setPublishState('idle');
            }}
          />
          <label>
            <input
              type="checkbox"
              checked={publishConfirmed}
              disabled={busy}
              onChange={(event) => setPublishConfirmed(event.target.checked)}
            />
            我已確認選單、設定版本與指紋摘要
          </label>
          <button
            type="button"
            disabled={busy || !publishConfirmed || publishReason.trim().length === 0}
            onClick={() => void queuePublication()}
          >
            確認排入發布
          </button>
        </div>
      )}

      {selectedPublication?.status === 'publish_retryable_failed' && (
        <div className="line-preview-result">
          <strong>發布紀錄 #{selectedPublication.id} 可重新排入</strong>
          <p>{selectedPublication.menuDefinitionId}｜{selectedPublication.statusLabel}</p>
          <label htmlFor={`line-rich-menu-retry-reason-${selectedPublication.id}`}>重試原因</label>
          <textarea
            id={`line-rich-menu-retry-reason-${selectedPublication.id}`}
            value={retryReason}
            rows={3}
            maxLength={500}
            disabled={busy}
            onChange={(event) => {
              setRetryReason(event.target.value);
              setRetryConfirmed(false);
              setRetryState('idle');
            }}
          />
          <label>
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
            disabled={busy || !retryConfirmed || retryReason.trim().length === 0}
            onClick={() => void retryPublication()}
          >
            確認重新排入
          </button>
        </div>
      )}

      {(publishState === 'loading' || retryState === 'loading') && (
        <div role="status">正在建立 durable 發布工作…</div>
      )}
      {receipt && (
        <div className="line-success" role="status">
          <strong>發布工作 #{receipt.publicationId}：{receipt.statusLabel}</strong>
          <p>設定版本 {receipt.configurationRevision}</p>
          <p>{receipt.durableNotice}</p>
        </div>
      )}
      {errorMessage && <div className="line-error" role="alert">{errorMessage}</div>}
    </section>
  );
};

export default LineRichMenuPublicationActions;
