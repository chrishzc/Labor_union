/**
 * File: LineCustomerServiceActions.tsx
 * Description: 提供客服接手、內部備註與建立 LINE durable 回覆任務的 typed 操作面板。
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  adaptCustomerServiceReplyPreview,
  adaptCustomerServiceReplyReceipt,
  adaptCustomerServiceResolvePreview,
  adaptCustomerServiceUpdateReceipt,
  type CustomerServiceDetailModel,
  type CustomerServiceReplyPreviewModel,
  type CustomerServiceReplyReceiptModel,
  type CustomerServiceResolvePreviewModel,
  type CustomerServiceUpdateReceiptModel,
} from '../adapters/customer_service/customer_service_adapter';
import {
  customerServiceClient,
  type CustomerServiceActionsClient,
} from '../api/customer_service/customer_service_client';
import { CustomerServiceClientError } from '../api/customer_service/customer_service_errors';
import type { CustomerServiceStatus } from '../api/customer_service/customer_service_schemas';

export interface LineCustomerServiceActionsProps {
  detail: CustomerServiceDetailModel;
  client?: CustomerServiceActionsClient;
  onCommitted?: (detail: CustomerServiceDetailModel) => void;
}

type MutationState = 'idle' | 'loading' | 'success' | 'error';

interface UpdateOperation {
  status: CustomerServiceStatus;
  successMessage: string;
  correlationId: string;
  idempotencyKey: string;
}

interface ReplyOperation {
  correlationId: string;
  idempotencyKey: string;
}

function operationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function displayError(error: unknown): string {
  if (error instanceof CustomerServiceClientError) {
    return `${error.code}：${error.message}`;
  }
  return error instanceof Error ? error.message : '客服操作失敗，請重新載入工單後再試。';
}

export const LineCustomerServiceActions: React.FC<LineCustomerServiceActionsProps> = ({
  detail: externalDetail,
  client = customerServiceClient,
  onCommitted,
}) => {
  const [detail, setDetail] = useState(externalDetail);
  const [internalNote, setInternalNote] = useState(externalDetail.ticket.internalNote ?? '');
  const [replyText, setReplyText] = useState('');
  const [resolveAfterReply, setResolveAfterReply] = useState(false);
  const [updatePreview, setUpdatePreview] = useState<CustomerServiceResolvePreviewModel | null>(null);
  const [updateOperation, setUpdateOperation] = useState<UpdateOperation | null>(null);
  const [updateConfirmed, setUpdateConfirmed] = useState(false);
  const [updateReceipt, setUpdateReceipt] = useState<CustomerServiceUpdateReceiptModel | null>(null);
  const [replyPreview, setReplyPreview] = useState<CustomerServiceReplyPreviewModel | null>(null);
  const [replyOperation, setReplyOperation] = useState<ReplyOperation | null>(null);
  const [replyConfirmed, setReplyConfirmed] = useState(false);
  const [replyReceipt, setReplyReceipt] = useState<CustomerServiceReplyReceiptModel | null>(null);
  const [mutationState, setMutationState] = useState<MutationState>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const committedReadbackRef = useRef<string | null>(null);

  useEffect(() => {
    controllerRef.current?.abort();
    setDetail(externalDetail);
    setInternalNote(externalDetail.ticket.internalNote ?? '');
    const incomingReadback = `${externalDetail.ticket.ticketId}:${externalDetail.ticket.version}`;
    if (committedReadbackRef.current === incomingReadback) {
      committedReadbackRef.current = null;
      return;
    }
    setReplyText('');
    setResolveAfterReply(false);
    setUpdatePreview(null);
    setUpdateOperation(null);
    setUpdateConfirmed(false);
    setUpdateReceipt(null);
    setReplyPreview(null);
    setReplyOperation(null);
    setReplyConfirmed(false);
    setReplyReceipt(null);
    setMutationState('idle');
    setMessage(null);
  }, [externalDetail]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const commitDetail = (nextDetail: CustomerServiceDetailModel, successMessage: string): void => {
    committedReadbackRef.current = `${nextDetail.ticket.ticketId}:${nextDetail.ticket.version}`;
    setDetail(nextDetail);
    setInternalNote(nextDetail.ticket.internalNote ?? '');
    setMutationState('success');
    setMessage(successMessage);
    onCommitted?.(nextDetail);
  };

  const invalidateUpdatePreview = (): void => {
    setUpdatePreview(null);
    setUpdateOperation(null);
    setUpdateConfirmed(false);
    setUpdateReceipt(null);
  };

  const invalidateReplyPreview = (): void => {
    setReplyPreview(null);
    setReplyOperation(null);
    setReplyConfirmed(false);
    setReplyReceipt(null);
  };

  const previewUpdate = async (status: CustomerServiceStatus, successMessage: string): Promise<void> => {
    const controller = new AbortController();
    controllerRef.current = controller;
    setMutationState('loading');
    setMessage(null);
    try {
      const operation: UpdateOperation = {
        status,
        successMessage,
        correlationId: operationIdentity(`line-ticket-${status}-preview`),
        idempotencyKey: operationIdentity(`line-ticket-${status}-apply`),
      };
      const result = await client.previewUpdate(
        detail.ticket.ticketId,
        {
          status,
          internal_note: internalNote.trim() || null,
          expected_version: detail.ticket.version,
        },
        { signal: controller.signal, correlationId: operation.correlationId }
      );
      setUpdatePreview(adaptCustomerServiceResolvePreview(result));
      setUpdateOperation(operation);
      setUpdateConfirmed(false);
      setUpdateReceipt(null);
      setMutationState('idle');
    } catch (error) {
      if (controller.signal.aborted) return;
      setMutationState('error');
      setMessage(displayError(error));
    }
  };

  const applyUpdate = async (): Promise<void> => {
    if (!updatePreview || !updateOperation || !updateConfirmed) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setMutationState('loading');
    setMessage(null);
    try {
      const result = await client.applyUpdate(
        detail.ticket.ticketId,
        {
          status: updateOperation.status,
          internal_note: internalNote.trim() || null,
          expected_version: updatePreview.expectedVersion,
          preview_fingerprint: updatePreview.previewFingerprint,
        },
        {
          signal: controller.signal,
          correlationId: updateOperation.correlationId,
          idempotencyKey: updateOperation.idempotencyKey,
        }
      );
      const receipt = adaptCustomerServiceUpdateReceipt(result);
      setUpdateReceipt(receipt);
      setUpdatePreview(null);
      setUpdateOperation(null);
      setUpdateConfirmed(false);
      commitDetail(receipt.readback, updateOperation.successMessage);
    } catch (error) {
      if (controller.signal.aborted) return;
      setMutationState('error');
      setMessage(displayError(error));
    }
  };

  const previewReply = async (): Promise<void> => {
    const controller = new AbortController();
    controllerRef.current = controller;
    setMutationState('loading');
    setMessage(null);
    try {
      const operation: ReplyOperation = {
        correlationId: operationIdentity('line-ticket-reply-preview'),
        idempotencyKey: operationIdentity('line-ticket-reply-apply'),
      };
      const result = await client.previewReply(
        detail.ticket.ticketId,
        {
          reply_text: replyText.trim(),
          resolve: resolveAfterReply,
          internal_note: internalNote.trim() || null,
          expected_version: detail.ticket.version,
        },
        { signal: controller.signal, correlationId: operation.correlationId }
      );
      setReplyPreview(adaptCustomerServiceReplyPreview(result));
      setReplyOperation(operation);
      setReplyConfirmed(false);
      setReplyReceipt(null);
      setMutationState('idle');
    } catch (error) {
      if (controller.signal.aborted) return;
      setMutationState('error');
      setMessage(displayError(error));
    }
  };

  const applyReply = async (): Promise<void> => {
    if (!replyPreview || !replyOperation || !replyConfirmed) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setMutationState('loading');
    setMessage(null);
    try {
      const result = await client.applyReply(
        detail.ticket.ticketId,
        {
          reply_text: replyText.trim(),
          resolve: resolveAfterReply,
          internal_note: internalNote.trim() || null,
          expected_version: replyPreview.expectedVersion,
          idempotency_key: replyOperation.idempotencyKey,
          preview_fingerprint: replyPreview.previewFingerprint,
        },
        { signal: controller.signal, correlationId: replyOperation.correlationId }
      );
      const receipt = adaptCustomerServiceReplyReceipt(result);
      setReplyReceipt(receipt);
      setReplyPreview(null);
      setReplyOperation(null);
      setReplyConfirmed(false);
      setReplyText('');
      setResolveAfterReply(false);
      commitDetail(
        receipt.readback,
        resolveAfterReply
          ? '客服回覆已保存並建立 delivery task，工單已結案；LINE 尚未送達。'
          : '客服回覆已保存並建立 delivery task；LINE 尚未送達。'
      );
    } catch (error) {
      if (controller.signal.aborted) return;
      setMutationState('error');
      setMessage(displayError(error));
    }
  };

  const busy = mutationState === 'loading';
  const noteUnchanged = internalNote === (detail.ticket.internalNote ?? '');

  return (
    <section className="line-action-panel" aria-label="客服工單操作">
      <h4>客服處理</h4>
      {detail.ticket.status === 'waiting' && (
        <button
          type="button"
          disabled={busy}
          onClick={() => void previewUpdate('handling', '工單已進入處理中。')}
        >
          預覽開始處理
        </button>
      )}

      <label htmlFor={`line-ticket-note-${detail.ticket.ticketId}`}>內部備註</label>
      <textarea
        id={`line-ticket-note-${detail.ticket.ticketId}`}
        value={internalNote}
        rows={3}
        maxLength={4000}
        disabled={busy}
        onChange={(event) => {
          setInternalNote(event.target.value);
          invalidateUpdatePreview();
          invalidateReplyPreview();
          setMutationState('idle');
          setMessage(null);
        }}
      />
      <button
        type="button"
        disabled={busy || noteUnchanged}
        onClick={() => void previewUpdate(detail.ticket.status, '內部備註已更新。')}
      >
        預覽更新內部備註
      </button>

      {updatePreview && updateOperation && (
        <div className="line-preview-result">
          <strong>{updatePreview.beforeStatusLabel} → {updatePreview.afterStatusLabel}</strong>
          <p>確認後會重新核對並讀回最新工單狀態。</p>
          <label>
            <input
              type="checkbox"
              checked={updateConfirmed}
              disabled={busy}
              onChange={(event) => setUpdateConfirmed(event.target.checked)}
            />
            我已確認狀態與備註內容
          </label>
          <button type="button" disabled={busy || !updateConfirmed} onClick={() => void applyUpdate()}>
            確認套用客服操作
          </button>
        </div>
      )}
      {updateReceipt && (
        <div className="line-success" role="status">
          客服工單已更新為「{updateReceipt.resultingStatusLabel}」。
        </div>
      )}

      <label htmlFor={`line-ticket-reply-${detail.ticket.ticketId}`}>LINE 回覆內容</label>
      <textarea
        id={`line-ticket-reply-${detail.ticket.ticketId}`}
        value={replyText}
        rows={4}
        maxLength={2000}
        disabled={busy}
        onChange={(event) => {
          setReplyText(event.target.value);
          invalidateReplyPreview();
          setMutationState('idle');
          setMessage(null);
        }}
      />
      <label>
        <input
          type="checkbox"
          checked={resolveAfterReply}
          disabled={busy}
          onChange={(event) => {
            setResolveAfterReply(event.target.checked);
            invalidateReplyPreview();
          }}
        />
        回覆後結案
      </label>
      <button
        type="button"
        disabled={busy || replyText.trim().length === 0}
        onClick={() => void previewReply()}
      >
        預覽 LINE 回覆
      </button>
      <p>預覽不會送出；確認後只排入 LINE 發送佇列，尚不代表客戶已收到。</p>

      {replyPreview && replyOperation && (
        <div className="line-preview-result">
          <strong>{replyPreview.beforeStatusLabel} → {replyPreview.afterStatusLabel}</strong>
          <p>{replyPreview.replyCharacterCount} 字；確認後將排入發送佇列，尚未送達 LINE。</p>
          <label>
            <input
              type="checkbox"
              checked={replyConfirmed}
              disabled={busy}
              onChange={(event) => setReplyConfirmed(event.target.checked)}
            />
            我已確認回覆內容與工單狀態
          </label>
          <button type="button" disabled={busy || !replyConfirmed} onClick={() => void applyReply()}>
            確認建立 LINE 回覆任務
          </button>
        </div>
      )}
      {replyReceipt && (
        <div className="line-success" role="status">
          LINE 回覆已排入發送佇列，尚未送達。
        </div>
      )}

      {mutationState === 'loading' && <div role="status">正在提交客服操作…</div>}
      {mutationState === 'success' && <div className="line-success" role="status">{message}</div>}
      {mutationState === 'error' && <div className="line-error" role="alert">{message}</div>}
    </section>
  );
};

export default LineCustomerServiceActions;
