import { useCallback, useEffect, useState } from 'react';
import {
  intakeBlockerMessage,
  intakeRepairErrorMessage,
  orderIntakeCompletionClient,
  type IntakeClientNamePreview,
  type IntakeCompletionPreview,
  type IntakeMissingField,
  type IntakeTermsPreview,
} from '../api/orders/order_intake_completion_client';
import { ordersQueryClient } from '../api/orders/order_query_client';

const FIELD_LABELS: Record<IntakeMissingField, string> = {
  client_name: '客戶姓名',
  start_date: '服務開始日',
  service_days: '服務天數',
};

function operationKey(caseNo: string, operation: string): string {
  return `orders-intake-${operation}-${caseNo}-${crypto.randomUUID()}`;
}

export interface OrderIntakeRepairPanelProps {
  caseNo: string;
  orderStatus: string;
  onChanged?: () => Promise<void> | void;
  onHistoricalRestartRequested?: () => Promise<void> | void;
}

type IntakeOperation = 'name-preview' | 'name-apply' | 'terms-preview' | 'terms-apply' | 'completion-apply' | null;

export function OrderIntakeRepairPanel({
  caseNo,
  orderStatus,
  onChanged,
  onHistoricalRestartRequested,
}: OrderIntakeRepairPanelProps) {
  const [completion, setCompletion] = useState<IntakeCompletionPreview | null>(null);
  const [clientName, setClientName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [serviceDays, setServiceDays] = useState('');
  const [reason, setReason] = useState('');
  const [namePreview, setNamePreview] = useState<IntakeClientNamePreview | null>(null);
  const [termsPreview, setTermsPreview] = useState<IntakeTermsPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [operation, setOperation] = useState<IntakeOperation>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    const [completionResult, detailResult] = await Promise.allSettled([
      orderIntakeCompletionClient.previewCompletion(caseNo, { signal }),
      ordersQueryClient.getOrderDetail(caseNo, { signal }),
    ]);
    if (completionResult.status === 'rejected') throw completionResult.reason;
    if (signal?.aborted) return;
    setCompletion(completionResult.value);
    if (detailResult.status === 'fulfilled' && detailResult.value.case_no === caseNo) {
      const detail = detailResult.value;
      setClientName(detail.client_name.startsWith('待補姓名') ? '' : detail.client_name);
      setStartDate(detail.start_date ?? '');
      setServiceDays(detail.service_days > 0 ? String(detail.service_days) : '');
    }
    setLoading(false);
  }, [caseNo]);

  useEffect(() => {
    const controller = new AbortController();
    setCompletion(null);
    setNamePreview(null);
    setTermsPreview(null);
    setReason('');
    setNotice(null);
    void refresh(controller.signal).catch((caught) => {
      if (!controller.signal.aborted) {
        setLoading(false);
        setError(intakeRepairErrorMessage(caught));
      }
    });
    return () => controller.abort();
  }, [refresh]);

  const afterMutation = async (message: string) => {
    setNamePreview(null);
    setTermsPreview(null);
    setNotice(message);
    await onChanged?.();
    await refresh();
  };

  const previewName = async () => {
    setOperation('name-preview');
    setError(null);
    setNotice(null);
    try {
      setNamePreview(await orderIntakeCompletionClient.previewClientName(caseNo, clientName));
    } catch (caught) {
      setNamePreview(null);
      setError(intakeRepairErrorMessage(caught));
    } finally {
      setOperation(null);
    }
  };

  const applyName = async () => {
    if (!namePreview || !reason.trim()) return;
    setOperation('name-apply');
    setError(null);
    try {
      await orderIntakeCompletionClient.applyClientName(
        caseNo,
        namePreview,
        reason,
        operationKey(caseNo, 'client-name'),
      );
      await afterMutation('客戶姓名已補齊並完成回讀。');
    } catch (caught) {
      setError(intakeRepairErrorMessage(caught));
    } finally {
      setOperation(null);
    }
  };

  const previewTerms = async () => {
    const parsedDays = Number(serviceDays);
    if (!startDate || !Number.isInteger(parsedDays) || parsedDays <= 0) {
      setError('請輸入有效的服務開始日與正整數服務天數。');
      return;
    }
    setOperation('terms-preview');
    setError(null);
    setNotice(null);
    try {
      setTermsPreview(await orderIntakeCompletionClient.previewTerms(caseNo, startDate, parsedDays));
    } catch (caught) {
      setTermsPreview(null);
      setError(intakeRepairErrorMessage(caught));
    } finally {
      setOperation(null);
    }
  };

  const applyTerms = async () => {
    if (!termsPreview || !reason.trim()) return;
    setOperation('terms-apply');
    setError(null);
    try {
      await orderIntakeCompletionClient.applyTerms(
        caseNo,
        termsPreview,
        reason,
        operationKey(caseNo, 'terms'),
      );
      await afterMutation('服務開始日／天數已補齊並完成回讀。');
    } catch (caught) {
      setError(intakeRepairErrorMessage(caught));
    } finally {
      setOperation(null);
    }
  };

  const applyCompletion = async () => {
    if (!completion || !completion.apply_allowed || completion.missing_fields.length > 0 || !reason.trim()) return;
    setOperation('completion-apply');
    setError(null);
    try {
      await orderIntakeCompletionClient.applyCompletion(
        caseNo,
        completion,
        reason,
        operationKey(caseNo, 'completion'),
      );
      await afterMutation('進件缺件已完成，案件已回讀最新狀態。');
    } catch (caught) {
      setError(intakeRepairErrorMessage(caught));
    } finally {
      setOperation(null);
    }
  };

  const historicalRestartAvailable = orderStatus === '歷史訂單－未服務' || orderStatus === '歷史訂單－服務中';
  const historicalCompleted = orderStatus === '歷史訂單－服務完成' || orderStatus === '歷史訂單－帳務完成';
  const repairAllowed = completion !== null && completion.blockers.length === 0;
  const missingName = completion?.missing_fields.includes('client_name') ?? false;
  const missingTerms = completion?.missing_fields.some((field) => field === 'start_date' || field === 'service_days') ?? false;
  const shouldRender = loading
    || error !== null
    || completion === null
    || completion.missing_fields.length > 0
    || completion.apply_allowed
    || ((historicalRestartAvailable || historicalCompleted) && completion.blockers.length > 0);

  if (!shouldRender) return null;

  return (
    <section
      aria-label="訂單缺件"
      data-surface-id="orders.intake-repair.drawer"
      style={{ border: '1px solid #fdba74', borderRadius: '12px', padding: '14px 16px', background: '#fffaf5', display: 'grid', gap: '10px' }}
    >
      <header>
        <strong style={{ color: '#9a3412' }}>缺件</strong>
        <div style={{ color: '#74593f', fontSize: '0.82rem', marginTop: '3px' }}>
          是否可補件以 Orders intake owner 的即時檢查為準；缺欄位本身不代表仍可回到 intake。
        </div>
      </header>

      {loading && <div role="status">正在檢查目前可用的補件流程…</div>}
      {error && <div role="alert" style={{ color: '#991b1b' }}>{error}</div>}
      {notice && <div role="status" style={{ color: '#166534' }}>{notice}</div>}

      {completion && !loading && (
        <>
          <div style={{ fontSize: '0.84rem', color: '#57423b' }}>
            缺少資料：{completion.missing_fields.length > 0
              ? completion.missing_fields.map((field) => FIELD_LABELS[field]).join('、')
              : '無'}
          </div>

          {completion.blockers.length > 0 && (
            <div role="status" style={{ color: '#991b1b', display: 'grid', gap: '4px' }}>
              <strong>目前不可完成補件</strong>
              <ul style={{ margin: 0, paddingLeft: '20px' }}>
                {completion.blockers.map((blocker) => <li key={blocker}>{intakeBlockerMessage(blocker)}</li>)}
              </ul>
            </div>
          )}

          {historicalRestartAvailable && completion.blockers.length > 0 && (
            <div style={{ display: 'grid', gap: '6px' }}>
              <span style={{ fontSize: '0.82rem', color: '#74593f' }}>
                此歷史案件不放寬 intake；請改走既有「重啟正常流程」，回到訂單成立後再使用正式日期／媒合／排班流程。
              </span>
              <button
                type="button"
                className="btn-secondary-action"
                data-control-id="orders.intake-repair.historical-restart"
                onClick={() => void onHistoricalRestartRequested?.()}
              >
                前往重啟正常流程
              </button>
            </div>
          )}

          {historicalCompleted && completion.blockers.length > 0 && (
            <div role="status" style={{ color: '#74593f', fontSize: '0.82rem' }}>
              此案已進入歷史完成階段，不提供 intake 或重啟倒退；後續帳務可用性由正式歷史帳務流程處理。
            </div>
          )}

          {repairAllowed && (missingName || missingTerms || completion.apply_allowed) && (
            <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem', color: '#57423b' }}>
              補件原因（套用時必填）
              <input
                value={reason}
                maxLength={500}
                disabled={operation !== null}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
          )}

          {repairAllowed && missingName && (
            <div style={{ borderTop: '1px solid #fed7aa', paddingTop: '10px', display: 'grid', gap: '6px' }}>
              <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem' }}>
                客戶姓名
                <input
                  value={clientName}
                  maxLength={100}
                  disabled={operation !== null}
                  onChange={(event) => { setClientName(event.target.value); setNamePreview(null); }}
                />
              </label>
              <button type="button" className="btn-secondary-action" disabled={operation !== null || !clientName.trim()} onClick={() => void previewName()}>
                {operation === 'name-preview' ? '正在檢查姓名補件…' : '檢查姓名補件影響'}
              </button>
              {namePreview && (
                <div style={{ display: 'grid', gap: '6px' }}>
                  {namePreview.blockers.length > 0
                    ? <div role="status" style={{ color: '#991b1b' }}>{namePreview.blockers.map(intakeBlockerMessage).join('；')}</div>
                    : <div role="status">姓名：{namePreview.before_client_name || '未登錄'} → {namePreview.after_client_name}</div>}
                  <button
                    type="button"
                    className="btn-primary-action"
                    disabled={operation !== null || !namePreview.apply_allowed || !reason.trim()}
                    onClick={() => void applyName()}
                  >
                    {operation === 'name-apply' ? '正在套用姓名補件…' : '確認套用姓名補件'}
                  </button>
                </div>
              )}
            </div>
          )}

          {repairAllowed && missingTerms && (
            <div style={{ borderTop: '1px solid #fed7aa', paddingTop: '10px', display: 'grid', gap: '6px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem' }}>
                  服務開始日
                  <input type="date" value={startDate} disabled={operation !== null} onChange={(event) => { setStartDate(event.target.value); setTermsPreview(null); }} />
                </label>
                <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem' }}>
                  服務天數
                  <input type="number" min="1" value={serviceDays} disabled={operation !== null} onChange={(event) => { setServiceDays(event.target.value); setTermsPreview(null); }} />
                </label>
              </div>
              <button type="button" className="btn-secondary-action" disabled={operation !== null || !startDate || Number(serviceDays) <= 0} onClick={() => void previewTerms()}>
                {operation === 'terms-preview' ? '正在檢查日期／天數補件…' : '檢查日期／天數補件影響'}
              </button>
              {termsPreview && (
                <div style={{ display: 'grid', gap: '6px' }}>
                  {termsPreview.blockers.length > 0
                    ? <div role="status" style={{ color: '#991b1b' }}>{termsPreview.blockers.map(intakeBlockerMessage).join('；')}</div>
                    : <div role="status">服務開始日 {termsPreview.after_start_date}；服務天數 {termsPreview.after_service_days} 天。</div>}
                  <button
                    type="button"
                    className="btn-primary-action"
                    disabled={operation !== null || !termsPreview.apply_allowed || !reason.trim()}
                    onClick={() => void applyTerms()}
                  >
                    {operation === 'terms-apply' ? '正在套用日期／天數補件…' : '確認套用日期／天數補件'}
                  </button>
                </div>
              )}
            </div>
          )}

          {repairAllowed && completion.missing_fields.length === 0 && completion.apply_allowed && (
            <button
              type="button"
              className="btn-primary-action"
              disabled={operation !== null || !reason.trim()}
              onClick={() => void applyCompletion()}
            >
              {operation === 'completion-apply' ? '正在完成進件補齊…' : '確認完成進件補齊'}
            </button>
          )}
        </>
      )}
    </section>
  );
}

export default OrderIntakeRepairPanel;
