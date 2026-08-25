/**
 * File: OrderServiceCompletionActions.tsx
 * Description: 提供管理員依 AutoComplete owner command 完成服務的 Preview、確認、Apply 與 receipt UI。
 */
import React, { useRef, useState } from 'react';

import {
  orderServiceCompletionClient,
  type OrderServiceCompletionPreview,
  type OrderServiceCompletionReceipt,
} from '../api/orders/order_service_completion_client';

interface Props {
  caseNo: string;
  orderStatus: string;
  onCompleted: () => void | Promise<void>;
}

type MutationStatus = 'idle' | 'previewing' | 'previewed' | 'applying' | 'completed' | 'failed';

export const OrderServiceCompletionActions: React.FC<Props> = ({
  caseNo,
  orderStatus,
  onCompleted,
}) => {
  const [status, setStatus] = useState<MutationStatus>('idle');
  const [preview, setPreview] = useState<OrderServiceCompletionPreview | null>(null);
  const [receipt, setReceipt] = useState<OrderServiceCompletionReceipt | null>(null);
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const idempotencyKeys = useRef(new Map<string, string>());

  const previewCompletion = async () => {
    setStatus('previewing');
    setError(null);
    setPreview(null);
    setReceipt(null);
    setConfirmed(false);
    try {
      const result = await orderServiceCompletionClient.preview(caseNo);
      setPreview(result);
      setStatus('previewed');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '無法檢查服務完成影響。');
      setStatus('failed');
    }
  };

  const applyCompletion = async () => {
    if (!preview || !confirmed || !reason.trim()) return;
    setStatus('applying');
    setError(null);
    const identity = `${preview.fingerprint}:${reason.trim()}`;
    const key = idempotencyKeys.current.get(identity)
      ?? `ui-order-service-completion-${crypto.randomUUID()}`;
    idempotencyKeys.current.set(identity, key);
    try {
      const result = await orderServiceCompletionClient.apply(
        caseNo,
        preview,
        reason,
        key,
      );
      setReceipt(result);
      setStatus('completed');
      await onCompleted();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '無法確認完成服務。');
      setStatus('failed');
    }
  };

  return (
    <div className="calendar-workbench-card" style={{ marginTop: '16px' }}>
      <div className="calendar-card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="calendar-badge actual">完工</span>
          <h4 className="calendar-card-title">服務完成與結案階段</h4>
        </div>
      </div>

      {orderStatus === '訂單完成' ? (
        <div role="status" style={{ color: '#166534', fontWeight: 700 }}>
          本案已有正式服務完成事件；後續請依 Client Finance 與 Staff Payables owner 處理結算。
        </div>
      ) : orderStatus !== '服務中' ? (
        <div role="status" style={{ color: '#92400e' }}>
          目前狀態為「{orderStatus}」；只有已確認實際開工且進入服務中的案件，才能預覽服務完成。
        </div>
      ) : (
        <>
          <p style={{ margin: '0 0 10px', color: '#57423b', fontSize: '0.86rem' }}>
            系統會重新鎖定正式排班、完整服務日、服務結束時刻與 lifecycle controls；不接受手動指定目標狀態。
          </p>
          <button
            type="button"
            className="btn-secondary-action"
            disabled={status === 'previewing' || status === 'applying'}
            onClick={() => void previewCompletion()}
          >
            {status === 'previewing' ? '正在檢查完成影響…' : '檢查服務完成影響'}
          </button>

          {preview && (
            <div style={{ background: '#fffdfb', border: '1px solid #fed9b8', borderRadius: '12px', padding: '14px', marginTop: '12px' }}>
              <strong>服務完成內容已檢查</strong>
              <div>目前狀態：{preview.current_status}</div>
              <div>完成時刻：{new Date(preview.completion_instant).toLocaleString('zh-TW')}</div>
              <div>正式服務日：{preview.official_service_dates.join('、')}</div>
              <div>確認後訂單會進入服務完成狀態。</div>
              <label style={{ display: 'block', marginTop: '10px', fontWeight: 700 }}>
                完工確認原因
                <textarea
                  aria-label="完工確認原因"
                  rows={2}
                  maxLength={500}
                  value={reason}
                  disabled={status === 'applying'}
                  onChange={(event) => {
                    setReason(event.target.value);
                    setConfirmed(false);
                  }}
                  style={{ width: '100%', marginTop: '6px' }}
                />
              </label>
              <label style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={status === 'applying'}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                我已核對正式服務日與完成時刻，確認將訂單標記為服務完成。
              </label>
              <button
                type="button"
                className="btn-primary-action"
                style={{ marginTop: '10px' }}
                disabled={!confirmed || !reason.trim() || status === 'applying'}
                onClick={() => void applyCompletion()}
              >
                {status === 'applying' ? '服務完成套用中…' : '確認套用服務完成'}
              </button>
            </div>
          )}
        </>
      )}

      {receipt && (
        <div role="status" style={{ color: '#166534', fontWeight: 700, marginTop: '10px' }}>
          服務完成已登記並完成回讀。
        </div>
      )}
      {error && <div role="alert" style={{ color: '#b91c1c', marginTop: '10px' }}>{error}</div>}
    </div>
  );
};
