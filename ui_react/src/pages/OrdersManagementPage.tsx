/**
 * Orders management wrapper: exposes incomplete intake repair without changing complete-order workbenches.
 */
import React, { useCallback, useEffect, useLayoutEffect, useState } from 'react';
import { subscribeOrderSummarySnapshots } from '../api/orders/order_query_client';
import type { OrderSummaryItem } from '../api/orders/order_query_schemas';
import {
  intakeBlockerMessage,
  intakeRepairErrorMessage,
  orderIntakeCompletionClient,
  type IntakeClientNamePreview,
  type IntakeCompletionPreview,
  type IntakeMissingField,
  type IntakeTermsPreview,
} from '../api/orders/order_intake_completion_client';
import { OrdersPage } from './OrdersPage';

const FIELD_LABELS: Record<IntakeMissingField, string> = {
  client_name: '客戶姓名',
  start_date: '約定服務開始日',
  service_days: '服務天數',
};

function needsIntakeRepair(item: OrderSummaryItem): boolean {
  return item.order_status === '待補件'
    || item.client_name.startsWith('待補姓名')
    || item.start_date === null
    || item.service_days === null;
}

function operationKey(caseNo: string, operation: string): string {
  return `orders-intake-${operation}-${caseNo}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

interface IntakeRepairCardProps {
  item: OrderSummaryItem;
  onChanged: () => Promise<void>;
}

const IntakeRepairCard: React.FC<IntakeRepairCardProps> = ({ item, onChanged }) => {
  const [completion, setCompletion] = useState<IntakeCompletionPreview | null>(null);
  const [completionLoading, setCompletionLoading] = useState(true);
  const [clientName, setClientName] = useState(
    item.client_name.startsWith('待補姓名') ? '' : item.client_name,
  );
  const [startDate, setStartDate] = useState(item.start_date ?? '');
  const [serviceDays, setServiceDays] = useState(item.service_days?.toString() ?? '');
  const [reason, setReason] = useState('');
  const [clientPreview, setClientPreview] = useState<IntakeClientNamePreview | null>(null);
  const [termsPreview, setTermsPreview] = useState<IntakeTermsPreview | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshCompletion = useCallback(async () => {
    setCompletionLoading(true);
    try {
      const preview = await orderIntakeCompletionClient.previewCompletion(item.case_no);
      setCompletion(preview);
      setError(null);
      return preview;
    } catch (caught) {
      setCompletion(null);
      setError(intakeRepairErrorMessage(caught));
      return null;
    } finally {
      setCompletionLoading(false);
    }
  }, [item.case_no]);

  useEffect(() => {
    void refreshCompletion();
  }, [refreshCompletion]);

  const localMissing: IntakeMissingField[] = [
    ...(item.client_name.startsWith('待補姓名') ? ['client_name' as const] : []),
    ...(item.start_date === null ? ['start_date' as const] : []),
    ...(item.service_days === null ? ['service_days' as const] : []),
  ];
  const missingFields = completion?.missing_fields ?? localMissing;
  const termsMissing = missingFields.includes('start_date') || missingFields.includes('service_days');
  const hasReason = reason.trim().length > 0;
  const validTermsDraft = /^\d{4}-\d{2}-\d{2}$/.test(startDate)
    && Number.isInteger(Number(serviceDays))
    && Number(serviceDays) > 0;
  const termsProtectionReady = completion !== null && completion.blockers.length === 0;

  const finalizeIfComplete = async (successMessage: string) => {
    const fresh = await orderIntakeCompletionClient.previewCompletion(item.case_no);
    if (fresh.apply_allowed) {
      await orderIntakeCompletionClient.applyCompletion(
        item.case_no,
        fresh,
        reason,
        operationKey(item.case_no, 'complete'),
      );
      setNotice(`${successMessage}；已重新判定完整並恢復為洽談中。`);
    } else {
      setCompletion(fresh);
      setNotice(successMessage);
    }
    await onChanged();
  };

  const previewClientName = async () => {
    setBusy('client-preview');
    setError(null);
    setNotice(null);
    try {
      setClientPreview(await orderIntakeCompletionClient.previewClientName(item.case_no, clientName));
    } catch (caught) {
      setClientPreview(null);
      setError(intakeRepairErrorMessage(caught));
    } finally {
      setBusy(null);
    }
  };

  const applyClientName = async () => {
    if (!clientPreview || !hasReason) return;
    setBusy('client-apply');
    setError(null);
    setNotice(null);
    try {
      await orderIntakeCompletionClient.applyClientName(
        item.case_no,
        clientPreview,
        reason,
        operationKey(item.case_no, 'client-name'),
      );
      setClientPreview(null);
      await finalizeIfComplete('客戶姓名已補齊');
    } catch (caught) {
      setError(intakeRepairErrorMessage(caught));
      await refreshCompletion();
    } finally {
      setBusy(null);
    }
  };

  const previewTerms = async () => {
    if (!validTermsDraft || !termsProtectionReady) return;
    setBusy('terms-preview');
    setError(null);
    setNotice(null);
    try {
      setTermsPreview(await orderIntakeCompletionClient.previewTerms(
        item.case_no,
        startDate,
        Number(serviceDays),
      ));
    } catch (caught) {
      setTermsPreview(null);
      setError(intakeRepairErrorMessage(caught));
    } finally {
      setBusy(null);
    }
  };

  const applyTerms = async () => {
    if (!termsPreview || !termsPreview.apply_allowed || !hasReason) return;
    setBusy('terms-apply');
    setError(null);
    setNotice(null);
    try {
      await orderIntakeCompletionClient.applyTerms(
        item.case_no,
        termsPreview,
        reason,
        operationKey(item.case_no, 'terms'),
      );
      setTermsPreview(null);
      await finalizeIfComplete('約定服務日期／天數已補齊');
    } catch (caught) {
      setError(intakeRepairErrorMessage(caught));
      await refreshCompletion();
    } finally {
      setBusy(null);
    }
  };

  const finalizeExistingCompleteIntake = async () => {
    if (!completion?.apply_allowed || !hasReason) return;
    setBusy('completion-apply');
    setError(null);
    setNotice(null);
    try {
      await orderIntakeCompletionClient.applyCompletion(
        item.case_no,
        completion,
        reason,
        operationKey(item.case_no, 'complete'),
      );
      setNotice('缺件已重新判定完成，訂單已恢復為洽談中。');
      await onChanged();
    } catch (caught) {
      setError(intakeRepairErrorMessage(caught));
      await refreshCompletion();
    } finally {
      setBusy(null);
    }
  };

  return (
    <article
      data-surface-id="orders.intake-repair.card"
      style={{ border: '1px solid #d8c7bd', borderRadius: 12, padding: 16, background: '#fff', display: 'grid', gap: 14 }}
    >
      <header>
        <strong>{item.case_no}</strong>
        <span style={{ marginLeft: 10, color: '#8a4b32' }}>狀態：{item.order_status}</span>
      </header>

      <section aria-label={`${item.case_no} 缺件項目`}>
        <strong>目前阻擋項目</strong>
        {missingFields.length > 0 ? (
          <ul style={{ margin: '6px 0 0', paddingLeft: 22 }}>
            {missingFields.map((field) => <li key={field}>{FIELD_LABELS[field]}</li>)}
          </ul>
        ) : (
          <div style={{ marginTop: 6, color: '#166534' }}>必填進件資料已齊全，待重新判定訂單狀態。</div>
        )}
      </section>

      {completionLoading && <div role="status">正在檢查服務資料鎖與版本限制…</div>}
      {completion && completion.blockers.length > 0 && (
        <section role="status" style={{ border: '1px solid #f0b37e', background: '#fff7ed', borderRadius: 8, padding: 10 }}>
          <strong>目前不可完成補件</strong>
          <ul style={{ margin: '6px 0 0', paddingLeft: 22 }}>
            {completion.blockers.map((blocker) => <li key={blocker}>{intakeBlockerMessage(blocker)}</li>)}
          </ul>
        </section>
      )}

      <label style={{ display: 'grid', gap: 4, fontWeight: 600 }}>
        補件原因（稽核必填）
        <textarea
          aria-label={`${item.case_no} 補件原因`}
          rows={2}
          maxLength={500}
          value={reason}
          disabled={busy !== null}
          onChange={(event) => setReason(event.target.value)}
          placeholder="請填寫人工補件原因"
        />
      </label>

      {missingFields.includes('client_name') && (
        <section aria-label="補齊客戶姓名" style={{ display: 'grid', gap: 8 }}>
          <strong>客戶姓名</strong>
          <input
            aria-label={`${item.case_no} 客戶姓名`}
            value={clientName}
            disabled={busy !== null}
            onChange={(event) => {
              setClientName(event.target.value);
              setClientPreview(null);
              setError(null);
            }}
            placeholder="輸入正式客戶姓名"
          />
          <button type="button" disabled={busy !== null || clientName.trim().length === 0} onClick={() => void previewClientName()}>
            {busy === 'client-preview' ? '檢查中…' : '檢查姓名補件'}
          </button>
          {clientPreview && (
            <div style={{ display: 'grid', gap: 6 }}>
              <div>補件後姓名：<strong>{clientPreview.after_client_name}</strong></div>
              <button type="button" disabled={busy !== null || !hasReason} onClick={() => void applyClientName()}>
                {busy === 'client-apply' ? '套用中…' : '確認補齊客戶姓名'}
              </button>
            </div>
          )}
        </section>
      )}

      {termsMissing && (
        <section aria-label="補齊約定服務資料" style={{ display: 'grid', gap: 8 }}>
          <strong>約定服務資料</strong>
          <label style={{ display: 'grid', gap: 4 }}>
            約定服務開始日
            <input
              aria-label={`${item.case_no} 約定服務開始日`}
              type="date"
              value={startDate}
              disabled={busy !== null || !missingFields.includes('start_date')}
              onChange={(event) => {
                setStartDate(event.target.value);
                setTermsPreview(null);
                setError(null);
              }}
            />
          </label>
          <label style={{ display: 'grid', gap: 4 }}>
            服務天數
            <input
              aria-label={`${item.case_no} 服務天數`}
              type="number"
              min="1"
              value={serviceDays}
              disabled={busy !== null || !missingFields.includes('service_days')}
              onChange={(event) => {
                setServiceDays(event.target.value);
                setTermsPreview(null);
                setError(null);
              }}
            />
          </label>
          <button
            type="button"
            disabled={busy !== null || !validTermsDraft || !termsProtectionReady}
            onClick={() => void previewTerms()}
          >
            {busy === 'terms-preview' ? '檢查中…' : '檢查服務資料補件'}
          </button>
          {termsPreview && (
            <div style={{ display: 'grid', gap: 6 }}>
              <div>補件欄位：{termsPreview.changed_fields.map((field) => FIELD_LABELS[field]).join('、') || '無'}</div>
              {termsPreview.blockers.length > 0 && (
                <ul style={{ margin: 0, paddingLeft: 22, color: '#9a3412' }}>
                  {termsPreview.blockers.map((blocker) => <li key={blocker}>{intakeBlockerMessage(blocker)}</li>)}
                </ul>
              )}
              <button
                type="button"
                disabled={busy !== null || !termsPreview.apply_allowed || !hasReason}
                onClick={() => void applyTerms()}
              >
                {busy === 'terms-apply' ? '套用中…' : '確認補齊服務資料'}
              </button>
            </div>
          )}
        </section>
      )}

      {completion?.apply_allowed && missingFields.length === 0 && (
        <section aria-label="恢復訂單操作" style={{ display: 'grid', gap: 8 }}>
          <div>所有必填進件資料已齊全；確認後會以最新版本重新判定並恢復為「洽談中」。</div>
          <button type="button" disabled={busy !== null || !hasReason} onClick={() => void finalizeExistingCompleteIntake()}>
            {busy === 'completion-apply' ? '重新判定中…' : '恢復訂單操作'}
          </button>
        </section>
      )}

      {notice && <div role="status" style={{ color: '#166534', fontWeight: 600 }}>{notice}</div>}
      {error && <div role="alert" style={{ color: '#991b1b', fontWeight: 600 }}>{error}</div>}
    </article>
  );
};

export const OrdersManagementPage: React.FC = () => {
  const [repairItems, setRepairItems] = useState<OrderSummaryItem[]>([]);
  const [repairLoading, setRepairLoading] = useState(true);
  const [repairError, setRepairError] = useState<string | null>(null);
  const [ordersRevision, setOrdersRevision] = useState(0);

  useLayoutEffect(() => subscribeOrderSummarySnapshots(({ page, params }) => {
    if (params.lifecycle_scope !== 'unfinished' || params.query_text || params.after_case_no) return;
    setRepairItems(page.items.filter(needsIntakeRepair));
    setRepairLoading(false);
    setRepairError(null);
  }), []);

  const handleChanged = async () => {
    setRepairLoading(true);
    setRepairError(null);
    setOrdersRevision((current) => current + 1);
  };

  return (
    <div>
      {(repairLoading || repairError || repairItems.length > 0) && (
        <section
          aria-label="訂單缺件補齊"
          data-surface-id="orders.intake-repair"
          style={{ marginBottom: 20, padding: 18, border: '1px solid #e7c8b5', borderRadius: 14, background: '#fffaf7' }}
        >
          <h2 style={{ marginTop: 0, marginBottom: 6, fontSize: '1.1rem' }}>訂單缺件補齊</h2>
          <p style={{ marginTop: 0, color: '#6b5146' }}>
            僅列出目前缺少必要進件資料的訂單。補件先 Preview，再以最新版本與稽核原因 Apply；完整訂單仍使用下方既有工作台。
          </p>
          {repairLoading && <div role="status">正在重新判定缺件…</div>}
          {repairError && <div role="alert" style={{ color: '#991b1b' }}>{repairError}</div>}
          {!repairLoading && !repairError && repairItems.length > 0 && (
            <div style={{ display: 'grid', gap: 12 }}>
              {repairItems.map((item) => <IntakeRepairCard key={item.case_no} item={item} onChanged={handleChanged} />)}
            </div>
          )}
        </section>
      )}

      <OrdersPage key={ordersRevision} />
    </div>
  );
};

export default OrdersManagementPage;
