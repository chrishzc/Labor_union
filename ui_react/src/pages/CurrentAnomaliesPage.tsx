/** Current-only Anomalies page: current rows, typed detail and owner action descriptors. */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import './AnomaliesPage.css';
import { Drawer } from '../components/Drawer';
import { currentAnomalyQueryClient } from '../api/anomalies/current_anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import type { ImportWarningTaskView } from '../api/anomalies/anomaly_query_schemas';
import { importWarningSkipClient, type ImportWarningSkipPreview } from '../api/anomalies/import_warning_skip_client';
import type {
  CurrentAnomalyRecoveryContextView,
  RecoveryAction,
  AnomalyEvidenceField,
} from '../api/anomalies/anomaly_detail_schemas';
import { lineNotificationTimelineClient } from '../api/line/notification_timeline_client';
import {
  lineNotificationManualReplayClient,
  type LineNotificationManualReplayPreview,
  type LineNotificationManualReplayReceipt,
  lineNotificationWarningSkipClient, type LineNotificationWarningSkipPreview,
} from '../api/line/notification_manual_replay_client';
import {
  adaptCurrentAnomalySummary,
  type CurrentAnomalyRowViewModel,
} from '../adapters/anomalies/current_anomaly_adapter';
import { HcmControlledCorrectionWorkbench } from '../components/HcmControlledCorrectionWorkbench';
import { hcmResubmissionClient, type HcmCurrentReview, type HcmReviewSkipPreview } from '../api/case_import/hcm_resubmission_client';

const REGISTRY_PROFILE_FIELDS: Readonly<Record<string, string>> = {
  姓名: 'name', 性別: 'gender', 行動電話: 'phone', 縣市: 'city',
  '預產期/預計服務開始月份': 'due_month', 不符合原因: 'reject_reason',
  居住型態: 'residence_type', 生產方式: 'delivery_type', 寶寶資訊: 'baby_info',
};
const REGISTRY_ORDER_FIELDS = new Set(['服務時間', '預計服務日期', '希望服務天數']);

function registryHref(caseNo: string, field: string): string {
  const params = new URLSearchParams({ case: caseNo });
  if (REGISTRY_PROFILE_FIELDS[field]) params.set('field', REGISTRY_PROFILE_FIELDS[field]);
  return `#clients?${params}`;
}

const PAGE_SIZE = 50;
const MANUAL_REPLAY_ACTION = 'manual_replay_failed_notification';
type WarningSkipDialog =
  | { kind: 'hcm'; preview: HcmReviewSkipPreview; idempotencyKey: string }
  | { kind: 'import'; preview: ImportWarningSkipPreview; task: ImportWarningTaskView; idempotencyKey: string }
  | { kind: 'line'; preview: LineNotificationWarningSkipPreview; idempotencyKey: string };

function displayError(error: unknown): string {
  const code = String((error as { code?: unknown })?.code ?? '').toUpperCase();
  const status = Number((error as { status?: unknown })?.status ?? 0);
  if (status === 401 || code.includes('UNAUTHENTICATED')) return '登入狀態已失效，請重新登入後再查詢。';
  if (status === 403 || code.includes('FORBIDDEN')) return '目前帳號沒有查看異常資料的權限。';
  if (status === 404 || code.includes('NOT_FOUND')) return '這筆問題已不存在，請重新整理目前異常清單。';
  if (status === 409 || code.includes('STALE') || code.includes('CONFLICT')) return '問題資料已變更，請重新整理後再查看。';
  if (code.includes('NETWORK') || code.includes('TIMEOUT') || code.includes('UNAVAILABLE')) return '異常資料暫時無法取得，請稍後重試。';
  return '目前異常資料暫時無法使用，請稍後重試。';
}

function renderEvidence(value: unknown): string {
  return Array.isArray(value) ? value.join('、') : String(value);
}

const EVIDENCE_LABELS: Readonly<Record<string, string>> = {
  case_no: '案件編號',
  notification_reason: '通知未完成原因',
  applicable_source_count: '相關通知筆數',
  unresolved_source_count: '待處理通知筆數',
  root_condition_active: '問題是否仍存在',
};

function businessEvidence(field: AnomalyEvidenceField): string {
  if (field.key === 'notification_reason') {
    return field.value === 'recipient_unavailable' ? '目前無法通知收件者' : '請到 LINE 通知管理確認通知設定。';
  }
  if (field.kind === 'boolean') return field.value ? '是' : '否';
  return renderEvidence(field.value);
}

function ownerLabel(owner: string): string {
  return ({
    scheduling: '排班管理',
    staff_payables: '服務人員應付款',
    government_subsidy: '政府補助',
    case_import: '案件資料匯入',
    finance_import: '銀行流水匯入',
    line: 'LINE 管理',
  } as Record<string, string>)[owner] ?? '對應業務流程';
}

function operationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function sourceBinding(action: RecoveryAction, key: string): string | number | null {
  return action.source_bindings.find((binding) => binding.key === key)?.value ?? null;
}

function replayErrorMessage(error: unknown): string {
  const status = Number((error as { status?: unknown })?.status ?? 0);
  if (status === 401) return '登入狀態已失效，請重新登入後再操作。';
  if (status === 403) return '目前帳號沒有重新處理 LINE 通知的權限。';
  if (status === 404) return '找不到這筆 LINE 通知來源，請重新查詢異常。';
  if (status === 409) return 'LINE 通知資料已變更，請重新檢查後再操作。';
  if (status === 422) return '目前 LINE 通知不符合重新發送條件。';
  return 'LINE 通知重新處理未完成，請重新查詢後再試。';
}

export const CurrentAnomaliesPage: React.FC = () => {
  const [items, setItems] = useState<CurrentAnomalyRowViewModel[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importItems, setImportItems] = useState<ImportWarningTaskView[]>([]);
  const [importLoading, setImportLoading] = useState(true);
  const [importError, setImportError] = useState<string | null>(null);
  const [hcmReviews, setHcmReviews] = useState<HcmCurrentReview[]>([]);
  const [hcmCursor, setHcmCursor] = useState<number | null>(null);
  const [hcmLoading, setHcmLoading] = useState(true);
  const [hcmError, setHcmError] = useState<string | null>(null);
  const [skip, setSkip] = useState<WarningSkipDialog | null>(null);
  const [skipBusy, setSkipBusy] = useState(false);
  const [skipError, setSkipError] = useState<string | null>(null);
  const [skipMessage, setSkipMessage] = useState<string | null>(null);
  const [hcmCorrection, setHcmCorrection] = useState<{
    caseNo: string;
    displayMessage: string;
    reviewIdentity: string;
  } | null>(null);
  const [selected, setSelected] = useState<CurrentAnomalyRowViewModel | null>(null);
  const [detail, setDetail] = useState<CurrentAnomalyRecoveryContextView | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [replayPreview, setReplayPreview] = useState<LineNotificationManualReplayPreview | null>(null);
  const [replayReceipt, setReplayReceipt] = useState<LineNotificationManualReplayReceipt | null>(null);
  const [replayReason, setReplayReason] = useState('');
  const [replayConfirmed, setReplayConfirmed] = useState(false);
  const [replayError, setReplayError] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const load = useCallback(async (cursor?: string) => {
    const sequence = ++requestSequence.current;
    setLoading(true);
    setError(null);
    try {
      const page = await currentAnomalyQueryClient.queryCurrentAnomalies({
        limit: PAGE_SIZE,
        cursor,
      });
      if (sequence !== requestSequence.current) return;
      const incoming = page.items.map(adaptCurrentAnomalySummary);
      setItems((existing) => {
        if (!cursor) return incoming;
        const byKey = new Map(existing.map((item) => [item.issueKey, item]));
        for (const item of incoming) byKey.set(item.issueKey, item);
        return [...byKey.values()];
      });
      setNextCursor(page.next_cursor);
    } catch (caught) {
      if (sequence === requestSequence.current) setError(displayError(caught));
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, []);

  const loadImportWarnings = useCallback(async () => {
    setImportLoading(true);
    setImportError(null);
    try {
      const tasks = await anomalyQueryClient.queryImportWarningTasks({ activeOnly: true, limit: 200 });
      // The owner query excludes bound HCM field occurrences already represented by canonical reviews.
      setImportItems(tasks);
    } catch (caught) {
      setImportError(displayError(caught));
    } finally {
      setImportLoading(false);
    }
  }, []);

  const loadHcmReviews = useCallback(async (cursor?: number) => {
    setHcmLoading(true); setHcmError(null);
    try {
      const page = await hcmResubmissionClient.current(cursor);
      setHcmReviews((existing) => cursor === undefined ? page.items : [...existing, ...page.items]);
      setHcmCursor(page.next_cursor);
    } catch (caught) { setHcmError(displayError(caught)); }
    finally { setHcmLoading(false); }
  }, []);

  useEffect(() => { void load(); void loadImportWarnings(); void loadHcmReviews(); }, [load, loadImportWarnings, loadHcmReviews]);

  const previewSkip = async (review: HcmCurrentReview, field: string) => {
    setSkipBusy(true); setSkipError(null); setSkipMessage(null);
    try {
      const preview = await hcmResubmissionClient.previewFieldSkip(review.review_identity, field);
      if (preview.review_identity !== review.review_identity || preview.case_no !== review.case_no) throw new Error('Review binding mismatch');
      setSkip({ kind: 'hcm', preview, idempotencyKey: operationIdentity('hcm-field-skip') });
    } catch (caught) { setSkipError(displayError(caught)); }
    finally { setSkipBusy(false); }
  };

  const previewImportSkip = async (task: ImportWarningTaskView) => {
    setSkipBusy(true); setSkipError(null); setSkipMessage(null);
    try {
      const idempotencyKey = operationIdentity('import-warning-skip');
      const preview = await importWarningSkipClient.preview(task, idempotencyKey);
      setSkip({ kind: 'import', preview, task, idempotencyKey });
    } catch (caught) { setSkipError(displayError(caught)); }
    finally { setSkipBusy(false); }
  };

  const previewLineSkip = async (item: CurrentAnomalyRowViewModel) => {
    setSkipBusy(true); setSkipError(null); setSkipMessage(null);
    try {
      const preview = await lineNotificationWarningSkipClient.preview(item.issueKey);
      setSelected(null); setDetail(null);
      setSkip({ kind: 'line', preview, idempotencyKey: operationIdentity('line-warning-skip') });
    } catch (caught) { setSkipError(displayError(caught)); }
    finally { setSkipBusy(false); }
  };

  const applySkip = async () => {
    if (!skip || skipBusy) return;
    setSkipBusy(true); setSkipError(null);
    try {
      if (skip.kind === 'hcm') await hcmResubmissionClient.applyFieldSkip(skip.preview, skip.idempotencyKey);
      else if (skip.kind === 'import') await importWarningSkipClient.apply(skip.preview, skip.idempotencyKey);
      else await lineNotificationWarningSkipClient.apply(skip.preview, skip.idempotencyKey);
      setSkip(null);
      setSkipMessage('已略過這項警示並保存紀錄，案件與原始資料維持原狀。');
      if (skip.kind === 'hcm') await loadHcmReviews();
      else if (skip.kind === 'import') await loadImportWarnings();
      else { setSelected(null); setDetail(null); await load(); }
    } catch (caught) { setSkipError(displayError(caught)); }
    finally { setSkipBusy(false); }
  };

  const openImportWarning = useCallback(async (task: ImportWarningTaskView) => {
    if (task.owning_lane !== 'hcm' || !['HCM-FIELD-001', 'HCM-FIELD-002'].includes(task.logical_code)) {
      window.location.hash = task.navigation_action === 'finance_import_recovery_center' ? '#finance' : '#data-import';
      return;
    }
    setImportError(null);
    try {
      const referral = await anomalyQueryClient.queryImportWarningReferral({
        occurrenceIdentity: task.occurrence_identity,
        expectedVersion: task.tracking_version,
      });
      if (referral.target_command !== 'preview_hcm_resubmission') throw new Error('HCM correction referral unavailable');
      setHcmCorrection({
        caseNo: task.subject,
        displayMessage: task.display_message,
        reviewIdentity: referral.review_identity,
      });
    } catch (caught) {
      setImportError(displayError(caught));
    }
  }, []);

  const openDetail = useCallback(async (item: CurrentAnomalyRowViewModel) => {
    setSelected(item);
    setDetail(null);
    setDetailError(null);
    setReplayPreview(null);
    setReplayReceipt(null);
    setReplayReason('');
    setReplayConfirmed(false);
    setReplayError(null);
    setDetailLoading(true);
    try {
      const current = await anomalyDetailClient.queryCurrentAnomalyRecovery({ issueKey: item.issueKey });
      setDetail(current);
    } catch (caught) {
      setDetailError(displayError(caught));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const previewManualReplay = useCallback(async (action: RecoveryAction) => {
    setReplayLoading(true);
    setReplayError(null);
    setReplayReceipt(null);
    try {
      const caseNo = sourceBinding(action, 'case_no');
      const sourceEventId = sourceBinding(action, 'source_version');
      if (typeof caseNo !== 'string' || typeof sourceEventId !== 'number') {
        throw new Error('manual replay source bindings are incomplete');
      }
      const timeline = await lineNotificationTimelineClient.query(caseNo);
      if (!timeline.records.some((record) => record.source_event_id === sourceEventId)) {
        throw new Error('manual replay source does not belong to the current case');
      }
      const preview = await lineNotificationManualReplayClient.preview(sourceEventId);
      if (preview.source_event_id !== sourceEventId) {
        throw new Error('manual replay preview identity mismatch');
      }
      setReplayPreview(preview);
    } catch (caught) {
      setReplayPreview(null);
      setReplayError(replayErrorMessage(caught));
    } finally {
      setReplayLoading(false);
    }
  }, []);

  const applyManualReplay = useCallback(async () => {
    if (!replayPreview || !replayConfirmed || !replayReason.trim()) return;
    setReplayLoading(true);
    setReplayError(null);
    try {
      const receipt = await lineNotificationManualReplayClient.apply(
        replayPreview.source_event_id,
        {
          reason: replayReason.trim(),
          idempotency_key: operationIdentity('anomaly-line-replay-idem'),
          correlation_id: operationIdentity('anomaly-line-replay-corr'),
        },
      );
      setReplayPreview(null);
      setReplayConfirmed(false);
      if (selected) await openDetail(selected);
      await load();
      setReplayReceipt(receipt);
    } catch (caught) {
      setReplayError(replayErrorMessage(caught));
    } finally {
      setReplayLoading(false);
    }
  }, [load, openDetail, replayConfirmed, replayPreview, replayReason, selected]);

  return (
    <main className="anomalies-page" aria-labelledby="current-anomalies-title">
      <header className="page-header anomalies-page-header">
        <div>
          <h1 id="current-anomalies-title">異常審核</h1>
          <p>顯示目前仍成立的問題，並提供可用的業務處理入口。</p>
        </div>
        <button type="button" className="anomalies-primary-action" onClick={() => { void load(); void loadImportWarnings(); void loadHcmReviews(); }} disabled={loading || importLoading || hcmLoading}>重新查詢</button>
      </header>

      <section aria-labelledby="import-anomalies-title" className="anomalies-section">
        <h2 id="import-anomalies-title" className="anomalies-section-title">匯入資料待檢查</h2>
        <p>可補齊資料，或逐筆略過不需再處理的警示。略過會保存紀錄。</p>
        {hcmError && <div role="alert" className="error-message">{hcmError}</div>}
        {skipError && <div role="alert" className="error-message">{skipError}</div>}
        {skipMessage && <p role="status">{skipMessage}</p>}
        {importError && <div role="alert" className="error-message">匯入待檢查資料暫時無法取得；其他異常仍可使用。{importError}</div>}
        {!importLoading && !hcmLoading && importItems.length === 0 && hcmReviews.length === 0 && !importError && !hcmError && <p>目前沒有待處理的匯入資料。</p>}
        <div className="import-warnings-list">
          {hcmReviews.map((review) => <article className="import-warning-card" key={review.review_identity}>
            <div className="import-warning-header"><strong>案件 {review.case_no}</strong><span className="import-warning-status-badge">待處理</span></div>
            {review.fields.map((field) => <div key={field} className="import-warning-field">
              <p>{field}待補齊或修正</p>
              <div className="import-warning-actions">
                {(REGISTRY_PROFILE_FIELDS[field] || REGISTRY_ORDER_FIELDS.has(field)) && <a className="anomalies-action-btn" href={registryHref(review.case_no, field)}>{field === '不符合原因' ? '補填不符合原因' : '前往客戶名冊補資料'}</a>}
                <button className="anomalies-action-btn" type="button" disabled={skipBusy} onClick={() => void previewSkip(review, field)}>略過並解除這項警示</button>
                {!REGISTRY_PROFILE_FIELDS[field] && !REGISTRY_ORDER_FIELDS.has(field) && <a className="anomalies-action-btn" href="#data-import">前往資料匯入確認來源</a>}
              </div>
            </div>)}
            {review.can_correct && <button type="button" className="anomalies-action-btn" onClick={() => setHcmCorrection({ caseNo: review.case_no, displayMessage: review.fields.join('、'), reviewIdentity: review.review_identity })}>使用修正版工作簿處理</button>}
          </article>)}
          {importItems.map((task) => (
            <article className="import-warning-card" key={task.occurrence_identity}>
              <div className="import-warning-header">
                <strong>{task.owning_lane === 'hcm' ? '案件' : '資料'} {task.subject}</strong>
                <span className="import-warning-status-badge">待處理</span>
              </div>
              <p>{task.display_message}</p>
              <div className="import-warning-actions"><button className="anomalies-action-btn" type="button" onClick={() => void openImportWarning(task)}>
                {task.owning_lane === 'hcm' && ['HCM-FIELD-001', 'HCM-FIELD-002'].includes(task.logical_code) ? '檢查並提交修正' : '前往負責頁面處理'}
              </button>
              <button className="anomalies-action-btn" type="button" disabled={skipBusy} onClick={() => void previewImportSkip(task)}>略過並解除這項警示</button></div>
            </article>
          ))}
        </div>
        {hcmCursor !== null && <button type="button" disabled={hcmLoading} onClick={() => void loadHcmReviews(hcmCursor)}>載入更多待補資料</button>}
      </section>

      <Drawer isOpen={skip !== null} closeDisabled={skipBusy} onClose={() => { if (!skipBusy) setSkip(null); }} title="確認略過這項警示" size="normal"
        footer={skip && <>
          <button className="warning-skip-cancel" type="button" disabled={skipBusy} onClick={() => setSkip(null)}>取消</button>
          <button className="anomalies-action-btn warning-skip-confirm" type="button" disabled={skipBusy} onClick={() => void applySkip()}>{skipBusy ? '正在保存…' : '確認略過並保存紀錄'}</button>
        </>}>
        {skip && <><p>案件 {skip.kind === 'import' ? skip.task.subject : skip.preview.case_no}</p>
          <p>警示：{skip.kind === 'hcm' ? skip.preview.source_field : skip.kind === 'import' ? skip.task.display_message : 'LINE 通知失敗'}</p>
          <p>將解除這項警示並保存人工略過紀錄，案件與原始資料維持原狀。其他警示仍會保留。</p>
          {skipError && <p role="alert">{skipError}</p>}</>}
      </Drawer>

      {hcmCorrection && <HcmControlledCorrectionWorkbench
        {...hcmCorrection}
        onCancel={() => setHcmCorrection(null)}
        onApplied={() => { setHcmCorrection(null); void loadImportWarnings(); }}
      />}

      {error && <div role="alert" className="error-message">{error}</div>}

      <section aria-label="其他目前異常清單" className="anomalies-section">
        <h2 className="anomalies-section-title">其他目前異常</h2>
        {!loading && items.length === 0 && !error && <p>目前沒有其他異常。</p>}
        <div className="anomalies-list">
        {items.map((item) => (
          <article
            className={`anomaly-card ${item.blocking ? 'critical' : 'warning'}`}
            key={item.issueKey}
          >
            <button type="button" className="anomaly-card-open" onClick={() => void openDetail(item)}>
            <span className="anomaly-card-top"><strong className="anomaly-code-tag">{item.definitionCode}</strong><span className={`anomaly-severity-badge ${item.blocking ? 'critical' : 'warning'}`}>{item.blocking ? '阻擋作業' : '需要處理'}</span></span>
            <span>{ownerLabel(item.ownerDomain)}</span>
            <span>最近確認：{new Date(item.lastVerifiedAt).toLocaleString('zh-TW')}</span>
            </button>
            <button type="button" className="anomalies-action-btn" disabled={skipBusy} onClick={() => void previewLineSkip(item)}>略過並解除這項警示</button>
          </article>
        ))}
        </div>
      </section>

      {nextCursor && (
        <button type="button" onClick={() => void load(nextCursor)} disabled={loading}>
          載入更多
        </button>
      )}

      <Drawer
        isOpen={selected !== null}
        onClose={() => {
          setSelected(null);
          setDetail(null);
          setDetailError(null);
          setReplayPreview(null);
          setReplayReceipt(null);
          setReplayError(null);
        }}
        title={selected ? `${selected.definitionCode} 詳情` : '異常詳情'}
        size="normal"
      >
        {detailLoading && <p>正在讀取最新業務資料…</p>}
        {detailError && <div role="alert" className="error-message">{detailError}</div>}
        {detail && (
          <div>
            <p><strong>負責流程：</strong>{ownerLabel(detail.owner_domain)}</p>
            <p><strong>影響：</strong>{detail.blocking ? '目前會阻擋作業' : '目前需要人工確認'}</p>

            <h3>目前可判斷資料</h3>
            <dl>
              {[...detail.subject.fields, ...detail.details.fields].filter((field) => EVIDENCE_LABELS[field.key]).map((field) => (
                <React.Fragment key={`${field.kind}:${field.key}`}>
                  <dt>{EVIDENCE_LABELS[field.key]}</dt>
                  <dd>{businessEvidence(field)}</dd>
                </React.Fragment>
              ))}
            </dl>
            <h3>人工處理入口</h3>
            {detail.available_actions.length === 0 ? (
              <p>這類問題目前沒有可安全執行的處理操作；系統不會用通用結案取代業務修正。</p>
            ) : detail.available_actions.map((action) => (
              <article key={action.action_key} className="anomaly-action">
                <strong>{action.label}</strong>
                <p>完成操作後，系統會重新查詢最新業務資料並確認問題是否解除。</p>
                {action.action_key === MANUAL_REPLAY_ACTION ? (
                  <button
                    type="button"
                    onClick={() => void previewManualReplay(action)}
                    disabled={replayLoading}
                  >
                    {replayLoading ? '正在檢查…' : '檢查重新發送'}
                  </button>
                ) : <p>目前沒有可用的操作入口。</p>}

              </article>
            ))}
            {replayError && <div role="alert" className="error-message">{replayError}</div>}
            {replayPreview && (
              <section aria-label="LINE 通知重新發送確認" className="anomaly-action">
                <h3>重新發送檢查結果</h3>
                <p>來源事件：{replayPreview.source_event_id}｜通知類型：{replayPreview.event_code}</p>
                <p>符合目前規則：{replayPreview.matching_rule_count} 項</p>
                {replayPreview.historical_silent || !replayPreview.will_create_new_immutable_source ? (
                  <p role="alert">這筆通知目前不能建立新的重新發送工作。</p>
                ) : (
                  <>
                    <label htmlFor="anomaly-line-replay-reason">重新發送原因</label>
                    <textarea
                      id="anomaly-line-replay-reason"
                      value={replayReason}
                      onChange={(event) => setReplayReason(event.target.value)}
                      maxLength={1000}
                    />
                    <label>
                      <input
                        type="checkbox"
                        checked={replayConfirmed}
                        onChange={(event) => setReplayConfirmed(event.target.checked)}
                      />
                      我已確認目前收件者與通知規則，並同意建立重新發送工作
                    </label>
                    <button
                      type="button"
                      onClick={() => void applyManualReplay()}
                      disabled={replayLoading || !replayConfirmed || !replayReason.trim()}
                    >
                      確認建立重新發送工作
                    </button>
                  </>
                )}
              </section>
            )}
            {replayReceipt && (
              <p role="status">
                已建立重新發送來源 {replayReceipt.replayed_source_event_id}；系統會依目前設定處理，請稍後重新查詢結果。
              </p>
            )}
            <button type="button" onClick={() => selected && void openDetail(selected)}>
              重新查詢最新資料
            </button>
            <button type="button" className="anomalies-action-btn" disabled={skipBusy} onClick={() => selected && void previewLineSkip(selected)}>略過並解除這項警示</button>
            <p>可依負責流程處理，或確認略過這次警示並保存紀錄。</p>
          </div>
        )}
      </Drawer>
    </main>
  );
};

export default CurrentAnomaliesPage;
