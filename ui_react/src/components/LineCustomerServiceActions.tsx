/**
 * File: LineCustomerServiceActions.tsx
 * Description: 提供客服接手、內部備註與建立 LINE durable 回覆任務的 typed 操作面板。
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  adaptCustomerServiceDetail,
  type CustomerServiceDetailModel,
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
  const [mutationState, setMutationState] = useState<MutationState>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    controllerRef.current?.abort();
    setDetail(externalDetail);
    setInternalNote(externalDetail.ticket.internalNote ?? '');
    setReplyText('');
    setResolveAfterReply(false);
    setMutationState('idle');
    setMessage(null);
  }, [externalDetail]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const commitDetail = (nextDetail: CustomerServiceDetailModel, successMessage: string): void => {
    setDetail(nextDetail);
    setInternalNote(nextDetail.ticket.internalNote ?? '');
    setMutationState('success');
    setMessage(successMessage);
    onCommitted?.(nextDetail);
  };

  const updateTicket = async (status: CustomerServiceStatus, successMessage: string): Promise<void> => {
    const controller = new AbortController();
    controllerRef.current = controller;
    setMutationState('loading');
    setMessage(null);
    try {
      const result = await client.updateTicket(
        detail.ticket.ticketId,
        {
          status,
          internal_note: internalNote.trim() || null,
          expected_version: detail.ticket.version,
          idempotency_key: operationIdentity(`line-ticket-${status}`),
        },
        { signal: controller.signal }
      );
      commitDetail(adaptCustomerServiceDetail(result), successMessage);
    } catch (error) {
      if (controller.signal.aborted) return;
      setMutationState('error');
      setMessage(displayError(error));
    }
  };

  const replyTicket = async (): Promise<void> => {
    const controller = new AbortController();
    controllerRef.current = controller;
    setMutationState('loading');
    setMessage(null);
    try {
      const result = await client.replyTicket(
        detail.ticket.ticketId,
        {
          reply_text: replyText.trim(),
          resolve: resolveAfterReply,
          internal_note: internalNote.trim() || null,
          expected_version: detail.ticket.version,
          idempotency_key: operationIdentity('line-ticket-reply'),
        },
        { signal: controller.signal }
      );
      setReplyText('');
      setResolveAfterReply(false);
      commitDetail(
        adaptCustomerServiceDetail(result),
        resolveAfterReply ? 'LINE 回覆已排入發送佇列，工單已結案。' : 'LINE 回覆已排入發送佇列。'
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
          onClick={() => void updateTicket('handling', '工單已進入處理中。')}
        >
          開始處理
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
          setMutationState('idle');
          setMessage(null);
        }}
      />
      <button
        type="button"
        disabled={busy || noteUnchanged}
        onClick={() => void updateTicket(detail.ticket.status, '內部備註已更新。')}
      >
        儲存內部備註
      </button>

      <label htmlFor={`line-ticket-reply-${detail.ticket.ticketId}`}>LINE 回覆內容</label>
      <textarea
        id={`line-ticket-reply-${detail.ticket.ticketId}`}
        value={replyText}
        rows={4}
        maxLength={2000}
        disabled={busy}
        onChange={(event) => {
          setReplyText(event.target.value);
          setMutationState('idle');
          setMessage(null);
        }}
      />
      <label>
        <input
          type="checkbox"
          checked={resolveAfterReply}
          disabled={busy}
          onChange={(event) => setResolveAfterReply(event.target.checked)}
        />
        回覆後結案
      </label>
      <button
        type="button"
        disabled={busy || replyText.trim().length === 0}
        onClick={() => void replyTicket()}
      >
        建立 LINE 回覆發送任務
      </button>
      <p>訊息由後端建立 durable delivery task；本頁不直接呼叫 LINE provider。</p>

      {mutationState === 'loading' && <div role="status">正在提交客服操作…</div>}
      {mutationState === 'success' && <div className="line-success" role="status">{message}</div>}
      {mutationState === 'error' && <div className="line-error" role="alert">{message}</div>}
    </section>
  );
};

export default LineCustomerServiceActions;
