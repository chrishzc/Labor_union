/** Current-only Anomalies page: current rows, typed detail and owner action descriptors. */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import './AnomaliesPage.css';
import { Drawer } from '../components/Drawer';
import { currentAnomalyQueryClient } from '../api/anomalies/current_anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import type { ImportWarningTaskView } from '../api/anomalies/anomaly_query_schemas';
import type {
  CurrentAnomalyRecoveryContextView,
  RecoveryAction,
} from '../api/anomalies/anomaly_detail_schemas';
import { lineNotificationTimelineClient } from '../api/line/notification_timeline_client';
import {
  lineNotificationManualReplayClient,
  type LineNotificationManualReplayPreview,
  type LineNotificationManualReplayReceipt,
} from '../api/line/notification_manual_replay_client';
import {
  adaptCurrentAnomalySummary,
  type CurrentAnomalyRowViewModel,
} from '../adapters/anomalies/current_anomaly_adapter';
import { HcmControlledCorrectionWorkbench } from '../components/HcmControlledCorrectionWorkbench';

const PAGE_SIZE = 50;
const MANUAL_REPLAY_ACTION = 'manual_replay_failed_notification';

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
      const seenSubjects = new Set<string>();
      setImportItems(tasks.filter((task) => {
        const subjectKey = `${task.owning_lane}:${task.subject}`;
        if (seenSubjects.has(subjectKey)) return false;
        seenSubjects.add(subjectKey);
        return true;
      }));
    } catch (caught) {
      setImportError(displayError(caught));
    } finally {
      setImportLoading(false);
    }
  }, []);

  useEffect(() => { void load(); void loadImportWarnings(); }, [load, loadImportWarnings]);

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
        <button type="button" className="anomalies-primary-action" onClick={() => { void load(); void loadImportWarnings(); }} disabled={loading || importLoading}>重新查詢</button>
      </header>

      <section aria-labelledby="import-anomalies-title" className="anomalies-section">
        <h2 id="import-anomalies-title" className="anomalies-section-title">匯入資料待檢查</h2>
        {importError && <div role="alert" className="error-message">匯入待檢查資料暫時無法取得；其他異常仍可使用。{importError}</div>}
        {!importLoading && importItems.length === 0 && !importError && <p>目前沒有待處理的匯入資料。</p>}
        <div className="import-warnings-list">
          {importItems.map((task) => (
            <article className="import-warning-card" key={task.occurrence_identity}>
              <div className="import-warning-header">
                <strong>{task.owning_lane === 'hcm' ? '案件' : '資料'} {task.subject}</strong>
                <span className="import-warning-status-badge">待處理</span>
              </div>
              <p>{task.display_message}</p>
              <button className="anomalies-action-btn" type="button" onClick={() => void openImportWarning(task)}>
                {task.owning_lane === 'hcm' && ['HCM-FIELD-001', 'HCM-FIELD-002'].includes(task.logical_code) ? '檢查並提交修正' : '前往負責頁面處理'}
              </button>
            </article>
          ))}
        </div>
      </section>

      {hcmCorrection && <HcmControlledCorrectionWorkbench
        {...hcmCorrection}
        onCancel={() => setHcmCorrection(null)}
        onApplied={() => { setHcmCorrection(null); void loadImportWarnings(); }}
      />}

      {error && <div role="alert" className="error-message">{error}</div>}
      {!loading && items.length === 0 && !error && <p>目前沒有異常。</p>}

      <section aria-label="其他目前異常清單" className="anomalies-section">
        <h2 className="anomalies-section-title">其他目前異常</h2>
        <div className="anomalies-list">
        {items.map((item) => (
          <button
            type="button"
            className={`anomaly-card ${item.blocking ? 'critical' : 'warning'}`}
            key={item.issueKey}
            onClick={() => void openDetail(item)}
          >
            <span className="anomaly-card-top"><strong className="anomaly-code-tag">{item.definitionCode}</strong><span className={`anomaly-severity-badge ${item.blocking ? 'critical' : 'warning'}`}>{item.blocking ? '阻擋作業' : '需要處理'}</span></span>
            <span>{ownerLabel(item.ownerDomain)}</span>
            <span>最近確認：{new Date(item.lastVerifiedAt).toLocaleString('zh-TW')}</span>
          </button>
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
        size="wide"
      >
        {detailLoading && <p>正在讀取最新業務資料…</p>}
        {detailError && <div role="alert" className="error-message">{detailError}</div>}
        {detail && (
          <div>
            <p><strong>負責流程：</strong>{ownerLabel(detail.owner_domain)}</p>
            <p><strong>影響：</strong>{detail.blocking ? '目前會阻擋作業' : '目前需要人工確認'}</p>
            <details><summary>技術詳情與資料來源</summary><p>資料版本：{detail.owner_version}</p><p>負責模組：{detail.owner_domain}</p></details>
            <h3>目前可判斷資料</h3>
            <dl>
              {[...detail.subject.fields, ...detail.details.fields].map((field) => (
                <React.Fragment key={`${field.kind}:${field.key}`}>
                  <dt>{field.key}</dt>
                  <dd>{renderEvidence(field.value)}</dd>
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
                <details><summary>操作技術詳情</summary><p>{action.owning_domain} · {action.preview_operation} → {action.apply_operation ?? '僅供查詢'}</p><p>完成條件：{action.completion_predicate}</p></details>
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
            <p>只有重新檢查證實問題原因已消失後，這筆提醒才會從清單移除。</p>
          </div>
        )}
      </Drawer>
    </main>
  );
};

export default CurrentAnomaliesPage;
