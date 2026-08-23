/**
 * File: AnomaliesPage.tsx
 * Description: Anomalies 查詢與 Import Warning Preview／Apply／receipt 觀察抽屜。
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import './AnomaliesPage.css';
import { Drawer } from '../components/Drawer';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import { importWarningTransitionClient } from '../api/import_warning/import_warning_transition_client';
import { ImportWarningTransitionError } from '../api/import_warning/import_warning_transition_errors';
import type { WarningTransitionRequest } from '../api/import_warning/import_warning_transition_schemas';
import {
  adaptImportWarningTransitionPreview,
  adaptImportWarningTransitionReceipt,
  type ImportWarningTransitionPreviewViewModel,
  type ImportWarningTransitionReceiptViewModel,
} from '../adapters/import_warning/import_warning_transition_adapter';
import {
  adaptAnomalyDetailBundle,
  type AnomalyDetailBundleViewModel,
} from '../adapters/anomalies/anomaly_detail_adapter';
import {
  adaptAnomalySummary,
  adaptImportWarningTask,
  adaptImportWarningReferral,
  mapImportWarningStatusLabel,
  calculateAnomalyKPIs,
  filterAnomalies,
  CATEGORY_TAB_KEYS,
  type CategoryTabKey,
  type AnomalySummaryViewModel,
  type ImportWarningTaskViewModel,
  type ImportWarningReferralViewModel,
} from '../adapters/anomalies/anomaly_query_adapter';

type WarningFlowStatus =
  | 'idle' | 'editing' | 'preview_loading' | 'preview_ready' | 'apply_pending'
  | 'receipt_received' | 'requery_loading' | 'observed' | 'stale'
  | 'outcome_unknown' | 'observation_failed' | 'typed_error';

function warningKey(prefix: string): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return `${prefix}-${globalThis.crypto.randomUUID()}`;
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export const AnomaliesPage: React.FC = () => {
  const [selectedCategory, setSelectedCategory] = useState<CategoryTabKey>('全部');
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<'all' | 'open' | 'claimed' | 'resolved'>('all');
  const [selectedAnomaly, setSelectedAnomaly] = useState<AnomalySummaryViewModel | null>(null);
  const [selectedWarning, setSelectedWarning] = useState<ImportWarningTaskViewModel | null>(null);

  const [anomalyDetail, setAnomalyDetail] = useState<AnomalyDetailBundleViewModel | null>(null);
  const [anomalyDetailLoading, setAnomalyDetailLoading] = useState(false);
  const [anomalyDetailError, setAnomalyDetailError] = useState<string | null>(null);
  const [anomalyRecoveryError, setAnomalyRecoveryError] = useState<string | null>(null);
  const [warningReferral, setWarningReferral] = useState<ImportWarningReferralViewModel | null>(null);
  const [warningReferralLoading, setWarningReferralLoading] = useState(false);
  const [warningReferralError, setWarningReferralError] = useState<string | null>(null);
  const [warningFlowStatus, setWarningFlowStatus] = useState<WarningFlowStatus>('idle');
  const [warningAction, setWarningAction] = useState<WarningTransitionRequest['target_status']>('awaiting_external_confirmation');
  const [warningReason, setWarningReason] = useState('');
  const [warningPreview, setWarningPreview] = useState<ImportWarningTransitionPreviewViewModel | null>(null);
  const [warningReceipt, setWarningReceipt] = useState<ImportWarningTransitionReceiptViewModel | null>(null);
  const [warningFlowError, setWarningFlowError] = useState<string | null>(null);

  // Dual-lane State: Anomalies
  const [anomalies, setAnomalies] = useState<AnomalySummaryViewModel[]>([]);
  const [anomaliesLoading, setAnomaliesLoading] = useState<boolean>(true);
  const [anomaliesError, setAnomaliesError] = useState<string | null>(null);

  // Dual-lane State: Import Warnings
  const [importWarnings, setImportWarnings] = useState<ImportWarningTaskViewModel[]>([]);
  const [importWarningsLoading, setImportWarningsLoading] = useState<boolean>(true);
  const [importWarningsError, setImportWarningsError] = useState<string | null>(null);

  // Race condition guards
  const anomalyRequestSeq = useRef<number>(0);
  const importWarningRequestSeq = useRef<number>(0);
  const drawerRequestSeq = useRef<number>(0);
  const drawerAbortController = useRef<AbortController | null>(null);
  const warningFlowSeq = useRef(0);
  const warningPreviewKey = useRef(warningKey('warning-preview'));
  const warningApplyKey = useRef(warningKey('warning-apply'));
  const warningCorrelationId = useRef(warningKey('warning-transition'));
  const warningFlowLocked = ['apply_pending', 'receipt_received', 'requery_loading', 'outcome_unknown'].includes(warningFlowStatus);

  // Fetch Anomalies from live API
  const fetchAnomalies = useCallback(async () => {
    const seq = ++anomalyRequestSeq.current;
    setAnomaliesLoading(true);
    setAnomaliesError(null);

    try {
      const rawList = await anomalyQueryClient.queryAnomalies({ activeOnly: true });
      if (seq === anomalyRequestSeq.current) {
        const adaptedList = rawList.map(adaptAnomalySummary);
        setAnomalies(adaptedList);
      }
    } catch (err) {
      if (seq === anomalyRequestSeq.current) {
        const msg = err instanceof Error ? err.message : '載入異常資料失敗';
        setAnomaliesError(msg);
      }
    } finally {
      if (seq === anomalyRequestSeq.current) {
        setAnomaliesLoading(false);
      }
    }
  }, []);

  // Fetch Import Warning Tasks from live API
  const fetchImportWarnings = useCallback(async () => {
    const seq = ++importWarningRequestSeq.current;
    setImportWarningsLoading(true);
    setImportWarningsError(null);

    try {
      const rawTasks = await anomalyQueryClient.queryImportWarningTasks({ activeOnly: true });
      if (seq === importWarningRequestSeq.current) {
        const adaptedTasks = rawTasks.map(adaptImportWarningTask);
        setImportWarnings(adaptedTasks);
      }
    } catch (err) {
      if (seq === importWarningRequestSeq.current) {
        const msg = err instanceof Error ? err.message : '載入匯入警示資料失敗';
        setImportWarningsError(msg);
      }
    } finally {
      if (seq === importWarningRequestSeq.current) {
        setImportWarningsLoading(false);
      }
    }
  }, []);

  const closeDrawer = useCallback(() => {
    if (warningFlowLocked) return;
    drawerRequestSeq.current += 1;
    drawerAbortController.current?.abort();
    drawerAbortController.current = null;
    setSelectedAnomaly(null);
    setSelectedWarning(null);
    setAnomalyDetail(null);
    setWarningReferral(null);
    setAnomalyDetailLoading(false);
    setWarningReferralLoading(false);
    setWarningFlowStatus('idle');
    setWarningPreview(null);
    setWarningReceipt(null);
    setWarningFlowError(null);
  }, [warningFlowLocked]);

  const openAnomalyDrawer = useCallback((anomaly: AnomalySummaryViewModel) => {
    const seq = ++drawerRequestSeq.current;
    drawerAbortController.current?.abort();
    const controller = new AbortController();
    drawerAbortController.current = controller;
    setSelectedAnomaly(anomaly);
    setSelectedWarning(null);
    setAnomalyDetail(null);
    setAnomalyDetailError(null);
    setAnomalyRecoveryError(null);
    setAnomalyDetailLoading(true);
    setWarningReferral(null);
    void Promise.allSettled([
      anomalyDetailClient.queryAnomalyDetail({ fingerprint: anomaly.fingerprint }, { signal: controller.signal }),
      anomalyDetailClient.queryAnomalyRecovery({ fingerprint: anomaly.fingerprint }, { signal: controller.signal }),
    ])
      .then(([detailResult, recoveryResult]) => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          if (detailResult.status === 'rejected') throw detailResult.reason;
          const recovery = recoveryResult.status === 'fulfilled' ? recoveryResult.value : null;
          setAnomalyDetail(adaptAnomalyDetailBundle(detailResult.value, recovery));
          if (recoveryResult.status === 'rejected') {
            setAnomalyRecoveryError(recoveryResult.reason instanceof Error ? recoveryResult.reason.message : 'recovery context 暫時無法取得');
          }
        }
      })
      .catch((err: unknown) => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setAnomalyDetailError(err instanceof Error ? err.message : '載入異常詳情失敗');
        }
      })
      .finally(() => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setAnomalyDetailLoading(false);
        }
      });
  }, []);

  const openWarningDrawer = useCallback((warning: ImportWarningTaskViewModel) => {
    const seq = ++drawerRequestSeq.current;
    drawerAbortController.current?.abort();
    const controller = new AbortController();
    drawerAbortController.current = controller;
    setSelectedWarning(warning);
    setSelectedAnomaly(null);
    setWarningReferral(null);
    setWarningReferralError(null);
    setWarningReferralLoading(true);
    setAnomalyDetail(null);
    warningFlowSeq.current += 1;
    warningPreviewKey.current = warningKey('warning-preview');
    warningApplyKey.current = warningKey('warning-apply');
    warningCorrelationId.current = warningKey('warning-transition');
    setWarningFlowStatus('idle');
    setWarningAction('awaiting_external_confirmation');
    setWarningReason('');
    setWarningPreview(null);
    setWarningReceipt(null);
    setWarningFlowError(null);
    void anomalyQueryClient
      .queryImportWarningReferral(
        {
          occurrenceIdentity: warning.occurrenceIdentity,
          expectedVersion: warning.version,
        },
        { signal: controller.signal }
      )
      .then((referral) => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setWarningReferral(adaptImportWarningReferral(referral));
        }
      })
      .catch((err: unknown) => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setWarningReferralError(err instanceof Error ? err.message : '後端 typed referral contract 尚未開放');
        }
      })
      .finally(() => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setWarningReferralLoading(false);
        }
      });
  }, []);

  const invalidateWarningPreview = () => {
    if (warningFlowLocked) return;
    warningFlowSeq.current += 1;
    warningPreviewKey.current = warningKey('warning-preview');
    warningApplyKey.current = warningKey('warning-apply');
    warningCorrelationId.current = warningKey('warning-transition');
    setWarningPreview(null);
    setWarningReceipt(null);
    setWarningFlowError(null);
    setWarningFlowStatus('editing');
  };

  const warningRequest = (): WarningTransitionRequest | null => {
    if (!selectedWarning || !warningReason.trim()) return null;
    return {
      expected_version: selectedWarning.version,
      target_status: warningAction,
      reason_code: warningReason.trim(),
      note: null,
      evidence_reference: selectedWarning.evidenceReference,
    };
  };

  const previewWarningTransition = async () => {
    const request = warningRequest();
    if (!selectedWarning || !request || warningFlowLocked) {
      setWarningFlowError('請先選擇轉態並輸入理由。');
      return;
    }
    const seq = ++warningFlowSeq.current;
    setWarningFlowStatus('preview_loading');
    setWarningFlowError(null);
    try {
      const preview = adaptImportWarningTransitionPreview(await importWarningTransitionClient.preview(
        selectedWarning.occurrenceIdentity,
        request,
        { idempotencyKey: warningPreviewKey.current, correlationId: warningCorrelationId.current },
      ));
      if (seq !== warningFlowSeq.current) return;
      if (preview.occurrenceIdentity !== selectedWarning.occurrenceIdentity || preview.expectedVersion !== selectedWarning.version) {
        throw new Error('Preview identity 與目前匯入警示不一致。');
      }
      setWarningPreview(preview);
      setWarningFlowStatus('preview_ready');
    } catch (error) {
      if (seq !== warningFlowSeq.current) return;
      const typed = error instanceof ImportWarningTransitionError ? error : null;
      setWarningPreview(null);
      setWarningFlowStatus(typed?.code === 'IMPORT_WARNING_STALE' ? 'stale' : 'typed_error');
      setWarningFlowError(error instanceof Error ? error.message : 'Preview 無法完成。');
      if (typed?.code === 'IMPORT_WARNING_STALE') await fetchImportWarnings();
    }
  };

  const observeWarningReceipt = async (receipt: ImportWarningTransitionReceiptViewModel, seq: number) => {
    setWarningFlowStatus('requery_loading');
    try {
      const observed = adaptImportWarningTransitionReceipt(await importWarningTransitionClient.queryReceipt(
        receipt.receiptIdentity,
        { correlationId: warningCorrelationId.current },
      ));
      if (seq !== warningFlowSeq.current) return;
      if (
        observed.occurrenceIdentity !== receipt.occurrenceIdentity
        || observed.beforeStatus !== receipt.beforeStatus
        || observed.afterStatus !== receipt.afterStatus
        || observed.resultingVersion !== receipt.resultingVersion
        || observed.receiptIdentity !== receipt.receiptIdentity
        || observed.correlationId !== receipt.correlationId
      ) throw new Error('Receipt re-query 與 Apply receipt 不一致。');
      setWarningReceipt(observed);
      setWarningFlowStatus('observed');
      setWarningFlowError(null);
      setSelectedWarning((current) => current ? {
        ...current,
        status: observed.afterStatus,
        statusLabel: mapImportWarningStatusLabel(observed.afterStatus),
        version: observed.resultingVersion,
      } : current);
      setImportWarnings((items) => items.map((item) => item.occurrenceIdentity === observed.occurrenceIdentity ? {
        ...item,
        status: observed.afterStatus,
        statusLabel: mapImportWarningStatusLabel(observed.afterStatus),
        version: observed.resultingVersion,
      } : item));
    } catch (error) {
      if (seq !== warningFlowSeq.current) return;
      setWarningFlowStatus('observation_failed');
      setWarningFlowError(error instanceof Error ? error.message : 'Receipt 觀察失敗。');
    }
  };

  const applyWarningTransition = async (retry = false) => {
    const request = warningRequest();
    if (!selectedWarning || !request || !warningPreview) return;
    if (!retry && warningFlowStatus !== 'preview_ready') return;
    if (retry && warningFlowStatus !== 'outcome_unknown') return;
    const seq = retry ? warningFlowSeq.current : ++warningFlowSeq.current;
    setWarningFlowStatus('apply_pending');
    setWarningFlowError(null);
    try {
      const receipt = adaptImportWarningTransitionReceipt(await importWarningTransitionClient.apply(
        selectedWarning.occurrenceIdentity,
        request,
        { idempotencyKey: warningApplyKey.current, correlationId: warningCorrelationId.current },
      ));
      if (seq !== warningFlowSeq.current) return;
      if (
        receipt.occurrenceIdentity !== selectedWarning.occurrenceIdentity
        || receipt.beforeStatus !== selectedWarning.status
        || receipt.afterStatus !== warningPreview.resultingStatus
        || receipt.resultingVersion !== warningPreview.resultingVersion
      ) throw new Error('Apply receipt 與 Preview／warning identity 不一致。');
      setWarningReceipt(receipt);
      setWarningFlowStatus('receipt_received');
      await observeWarningReceipt(receipt, seq);
    } catch (error) {
      if (seq !== warningFlowSeq.current) return;
      const typed = error instanceof ImportWarningTransitionError ? error : null;
      if (typed?.outcomeUnknown) setWarningFlowStatus('outcome_unknown');
      else if (typed?.code === 'IMPORT_WARNING_STALE') {
        setWarningFlowStatus('stale');
        setWarningPreview(null);
        await fetchImportWarnings();
      } else setWarningFlowStatus('typed_error');
      setWarningFlowError(error instanceof Error ? error.message : 'Apply 無法完成。');
    }
  };

  useEffect(() => {
    fetchAnomalies();
    fetchImportWarnings();
    return () => {
      anomalyRequestSeq.current += 1;
      importWarningRequestSeq.current += 1;
      drawerRequestSeq.current += 1;
      drawerAbortController.current?.abort();
    };
  }, [fetchAnomalies, fetchImportWarnings]);

  const kpis = calculateAnomalyKPIs(anomalies);
  const filteredAnomalies = filterAnomalies(anomalies, selectedCategory, selectedStatusFilter);

  return (
    <div data-surface-id="anomalies.page">
      <div className="page-header-banner" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">⚠️ 異常與退款處理中心</h1>
          <p className="page-subtitle">跨領域根事實異常偵測、認領排查工作流、阻擋型警示與引導式修復閉環。</p>
        </div>
      </div>

      {/* 4 Metric Summary Cards */}
      <div className="anomalies-kpi-grid" data-surface-id="anomalies.kpis">
        <div className="anomaly-kpi-card" style={{ borderLeft: '6px solid #dc2626' }}>
          <div className="anomaly-kpi-label">🔴 阻擋型嚴重異常 (Critical Blockers)</div>
          <div className="anomaly-kpi-value" style={{ color: '#dc2626' }}>{kpis.criticalCount} 筆</div>
          <div className="anomaly-kpi-sub">阻擋跨階段推進與正式簽約</div>
        </div>

        <div className="anomaly-kpi-card" style={{ borderLeft: '6px solid #f59e0b' }}>
          <div className="anomaly-kpi-label">🟡 待補正警示 (Warning Alerts)</div>
          <div className="anomaly-kpi-value" style={{ color: '#d97706' }}>{kpis.warningCount} 筆</div>
          <div className="anomaly-kpi-sub">意願逾期、帳號缺失等提示</div>
        </div>

        <div className="anomaly-kpi-card">
          <div className="anomaly-kpi-label">⏳ 待認領處理 (Open Tasks)</div>
          <div className="anomaly-kpi-value" style={{ color: '#1e1b19' }}>{kpis.openCount} 筆</div>
          <div className="anomaly-kpi-sub">等待行政或會計人員認領</div>
        </div>

        <div className="anomaly-kpi-card">
          <div className="anomaly-kpi-label">🔵 處理中認領 (In Progress)</div>
          <div className="anomaly-kpi-value" style={{ color: '#3b82f6' }}>{kpis.claimedCount} 筆</div>
          <div className="anomaly-kpi-sub">已指派人員進行排查修復</div>
        </div>
      </div>

      {/* 8 Categories Filter Bar */}
      <div className="anomalies-category-bar" data-surface-id="anomalies.category-filters">
        {CATEGORY_TAB_KEYS.map((cat) => (
          <button
            key={cat}
            disabled={warningFlowLocked}
            className={`anomaly-cat-btn ${selectedCategory === cat ? 'active' : ''}`}
            onClick={() => setSelectedCategory(cat)}
          >
            {cat} {cat === '全部' ? `(${anomalies.length})` : ''}
          </button>
        ))}
      </div>

      {/* Status Secondary Filter Pills */}
      <div data-surface-id="anomalies.status-filters" style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <button
          disabled={warningFlowLocked}
          style={{
            padding: '4px 12px',
            borderRadius: '9999px',
            border: '1px solid #dec0b6',
            backgroundColor: selectedStatusFilter === 'all' ? '#ff7f50' : '#fff',
            color: selectedStatusFilter === 'all' ? '#fff' : '#57423b',
            fontSize: '0.8rem',
            fontWeight: 700,
            cursor: 'pointer',
          }}
          onClick={() => setSelectedStatusFilter('all')}
        >
          全部狀態 ({anomalies.length})
        </button>
        <button
          disabled={warningFlowLocked}
          style={{
            padding: '4px 12px',
            borderRadius: '9999px',
            border: '1px solid #dec0b6',
            backgroundColor: selectedStatusFilter === 'open' ? '#ff7f50' : '#fff',
            color: selectedStatusFilter === 'open' ? '#fff' : '#57423b',
            fontSize: '0.8rem',
            fontWeight: 700,
            cursor: 'pointer',
          }}
          onClick={() => setSelectedStatusFilter('open')}
        >
          🟡 待處理 ({kpis.openCount})
        </button>
        <button
          disabled={warningFlowLocked}
          style={{
            padding: '4px 12px',
            borderRadius: '9999px',
            border: '1px solid #dec0b6',
            backgroundColor: selectedStatusFilter === 'claimed' ? '#ff7f50' : '#fff',
            color: selectedStatusFilter === 'claimed' ? '#fff' : '#57423b',
            fontSize: '0.8rem',
            fontWeight: 700,
            cursor: 'pointer',
          }}
          onClick={() => setSelectedStatusFilter('claimed')}
        >
          🔵 已認領 ({kpis.claimedCount})
        </button>
        <button
          disabled={warningFlowLocked}
          style={{
            padding: '4px 12px',
            borderRadius: '9999px',
            border: '1px solid #dec0b6',
            backgroundColor: selectedStatusFilter === 'resolved' ? '#ff7f50' : '#fff',
            color: selectedStatusFilter === 'resolved' ? '#fff' : '#57423b',
            fontSize: '0.8rem',
            fontWeight: 700,
            cursor: 'pointer',
          }}
          onClick={() => setSelectedStatusFilter('resolved')}
        >
          ✅ 已排除
        </button>
      </div>

      <section data-surface-id="anomalies.list">
      {/* Anomalies List (Lane 1) */}
      {anomaliesLoading && (
        <div className="anomalies-loading">正在載入即時異常數據...</div>
      )}

      {anomaliesError && (
        <div className="anomalies-error">
          <span>載入異常資料失敗：{anomaliesError}</span>
          <button className="anomalies-retry-btn" onClick={fetchAnomalies}>重試</button>
        </div>
      )}

      {!anomaliesLoading && !anomaliesError && filteredAnomalies.length === 0 && (
        <div className="anomalies-empty">目前無符合條件之異常項目。</div>
      )}

      {!anomaliesLoading && !anomaliesError && filteredAnomalies.length > 0 && (
        <div className="anomalies-list">
          {filteredAnomalies.map((anm) => (
            <div
              key={anm.id}
              className={`anomaly-card ${anm.severityClass}`}
            >
              <div className="anomaly-card-top">
                <div className="anomaly-code-tag">
                  <span style={{ backgroundColor: '#fff8f6', border: '1px solid #fed9b8', padding: '2px 8px', borderRadius: '6px', fontSize: '0.85rem' }}>
                    {anm.code}
                  </span>
                  <span style={{ fontSize: '1.05rem', fontWeight: 700 }}>{anm.title}</span>
                </div>

                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span className={`anomaly-severity-badge ${anm.severityClass}`}>
                    {anm.severity}
                  </span>
                  <span style={{
                    padding: '3px 10px',
                    borderRadius: '9999px',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    backgroundColor: anm.rawWorkflowStatus === 'resolved' ? '#dcfce7' : anm.rawWorkflowStatus === 'claimed' ? '#dbeafe' : '#fef3c7',
                    color: anm.rawWorkflowStatus === 'resolved' ? '#166534' : anm.rawWorkflowStatus === 'claimed' ? '#1e40af' : '#92400e'
                  }}>
                    {anm.status}
                  </span>
                </div>
              </div>

              {/* Middle: Details & Related Entity */}
              <div style={{ fontSize: '0.88rem', color: '#57423b', lineHeight: '1.5' }}>
                <div><strong>關聯案件 / 實體：</strong><span style={{ color: '#c2410c', fontWeight: 600 }}>{anm.relatedEntity}</span></div>
                <div style={{ marginTop: '2px' }}><strong>異常描述：</strong>{anm.description}</div>
              </div>

              {/* Bottom Actions Row */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '10px', borderTop: '1px dashed #f2e2dc' }}>
                <div style={{ fontSize: '0.8rem', color: '#888' }}>
                  💡 建議處置：{anm.suggestedAction}
                </div>

                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    data-control-id="anomalies.card.claim"
                    disabled={true}
                    title="[查詢模式] 認領功能需待變更合約開放"
                    style={{ padding: '6px 14px', backgroundColor: '#94a3b8', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 600, fontSize: '0.82rem', cursor: 'not-allowed' }}
                  >
                    🔵 認領此案
                  </button>

                  <button
                    data-control-id="anomalies.card.drawer_open"
                    style={{ padding: '6px 14px', backgroundColor: '#ff7f50', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 700, fontSize: '0.82rem', cursor: 'pointer' }}
                    onClick={() => openAnomalyDrawer(anm)}
                  >
                    排查處置抽屜 ➔
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      </section>

      {/* Import Warning Tasks Section (Lane 2) */}
      <section data-surface-id="anomalies.import-warnings">
      <div className="anomalies-section-title">
        <span>📥 欄位級匯入警示追蹤任務 (Import Warning Tasks)</span>
      </div>

      {importWarningsLoading && (
        <div className="anomalies-loading">正在載入匯入警示追蹤數據...</div>
      )}

      {importWarningsError && (
        <div className="anomalies-error">
          <span>載入匯入警示資料失敗：{importWarningsError}</span>
          <button className="anomalies-retry-btn" onClick={fetchImportWarnings}>重試</button>
        </div>
      )}

      {!importWarningsLoading && !importWarningsError && importWarnings.length === 0 && (
        <div className="anomalies-empty">目前無待追蹤之匯入警示任務。</div>
      )}

      {!importWarningsLoading && !importWarningsError && importWarnings.length > 0 && (
        <div className="import-warnings-list">
          {importWarnings.map((task) => (
            <div key={task.occurrenceIdentity} className="import-warning-card">
              <div className="import-warning-header">
                <div className="import-warning-badges">
                  <span className="import-warning-lane-badge">{task.laneLabel}</span>
                  <span className="import-warning-code-badge">{task.logicalCode}</span>
                  <span style={{ fontSize: '0.78rem', color: '#64748b' }}>v{task.version}</span>
                </div>
                <span className={`import-warning-status-badge ${task.status}`}>
                  {task.statusLabel}
                </span>
              </div>

              <div className="import-warning-body">
                <div><strong>欄位路徑：</strong><span>{task.fieldPath}</span></div>
                <div><strong>受遮罩主體：</strong><span>{task.maskedSubject}</span></div>
                <div><strong>佐證參照：</strong><span>{task.evidenceReference || '無'}</span></div>
              </div>

              <div style={{ fontSize: '0.88rem', color: '#1e1b19', fontWeight: 600 }}>
                {task.displayMessage}
              </div>

              <div className="import-warning-footer">
                <div>
                  <strong style={{ fontSize: '0.8rem', color: '#8b7169' }}>問題代碼：</strong>
                  {task.issueCodes.map((ic) => (
                    <span key={ic} className="import-warning-issue-tag">{ic}</span>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <button
                    data-control-id="anomalies.warning.drawer_open"
                    type="button"
                    onClick={() => openWarningDrawer(task)}
                    style={{ padding: '4px 12px', backgroundColor: '#ff7f50', color: '#fff', border: 'none', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 700, cursor: 'pointer' }}
                  >
                    查看警示詳情
                  </button>
                  {task.navigationAction && (
                    <a
                      data-surface-id="anomalies.navigation.data-import"
                      href="#data-import"
                      style={{
                        display: 'inline-block',
                        padding: '4px 12px',
                        backgroundColor: '#6366f1',
                        color: '#fff',
                        borderRadius: '6px',
                        fontSize: '0.8rem',
                        fontWeight: 700,
                        textDecoration: 'none',
                      }}
                    >
                      前往匯入中心 ➔
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      </section>

      {/* Diagnostic & Recovery Drawer */}
      <Drawer
        isOpen={selectedAnomaly !== null || selectedWarning !== null}
        onClose={closeDrawer}
        closeDisabled={warningFlowLocked}
        title={selectedAnomaly ? `⚠️ 異常排查與修復處置 — ${selectedAnomaly.code}` : `📥 匯入警示詳情 — ${selectedWarning?.logicalCode ?? ''}`}
        footer={
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85rem', color: '#888' }}>
              💡 依 06_Anomalies_Domain 規範，修復記錄後若根因未除，系統將自動 reopen。
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                disabled={warningFlowLocked}
                style={{ padding: '8px 16px', border: '1px solid #dec0b6', borderRadius: '8px', background: '#fff', cursor: 'pointer' }}
                onClick={closeDrawer}
              >
                關閉
              </button>
              {selectedAnomaly ? (
                <button
                  data-control-id="anomalies.drawer.resolve"
                  disabled={true}
                  title="[查詢模式] 排除功能需待變更合約開放"
                  style={{ padding: '8px 20px', backgroundColor: '#94a3b8', color: '#fff', border: 'none', borderRadius: '8px', fontWeight: 700, cursor: 'not-allowed' }}
                >
                  確認排除異常 (Resolve)
                </button>
              ) : (
                <button
                  data-control-id="anomalies.warning.transition"
                  disabled={true}
                  title="Warning disposition 不代表來源根事實已修復"
                  style={{ padding: '8px 20px', backgroundColor: '#94a3b8', color: '#fff', border: 'none', borderRadius: '8px', fontWeight: 700, cursor: 'not-allowed' }}
                >
                  Claim／Resolve 與來源修復仍未開放
                </button>
              )}
            </div>
          </div>
        }
      >
        {selectedAnomaly && (
          <div data-surface-id="anomalies.drawer" style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {/* Anomaly Overview Box */}
            <div style={{ backgroundColor: selectedAnomaly.severityClass === 'critical' ? '#fff1f2' : '#fffbeb', padding: '18px', borderRadius: '12px', border: selectedAnomaly.severityClass === 'critical' ? '1px solid #fecdd3' : '1px solid #fed7aa' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontWeight: 700, color: selectedAnomaly.severityClass === 'critical' ? '#991b1b' : '#92400e', fontSize: '1.05rem' }}>
                  {selectedAnomaly.title}
                </span>
                <span style={{ padding: '2px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 700, backgroundColor: '#fff' }}>
                  {selectedAnomaly.code}
                </span>
              </div>
              <p style={{ fontSize: '0.88rem', color: '#57423b', lineHeight: '1.5' }}>
                <strong>領域 (Domain)：</strong>{selectedAnomaly.metadata.sourceDomain}<br />
                <strong>資料版本：</strong>v{selectedAnomaly.metadata.sourceVersion} ｜ <strong>工作流版本：</strong>v{selectedAnomaly.metadata.workflowVersion}<br />
                <strong>條件作用中：</strong>{selectedAnomaly.metadata.predicateActive ? '是 (Active)' : '否 (Inactive)'}<br />
                <strong>關聯實體：</strong>{selectedAnomaly.relatedEntity}<br />
                <strong>異常詳情：</strong>{selectedAnomaly.description}
              </p>
            </div>

            <div data-surface-id="anomalies.drawer.detail" className="anomalies-detail-card">
              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19', marginBottom: '8px' }}>📄 後端異常詳情 (Detail GET)</h4>
              {anomalyDetailLoading && <div className="anomalies-detail-loading">正在載入異常詳情與修復上下文...</div>}
              {!anomalyDetailLoading && anomalyDetailError && <div className="anomalies-detail-error">{anomalyDetailError}</div>}
              {!anomalyDetailLoading && !anomalyDetailError && !anomalyDetail && <div className="anomalies-detail-empty">沒有可顯示的 typed detail。</div>}
              {!anomalyDetailLoading && anomalyDetail && (
                <>
                  <div data-surface-id="anomalies.drawer.evidence" className="anomalies-evidence-card">
                    <strong>去敏證據（anomaly-safe.v1）</strong>
                    {anomalyDetail.evidence.map((item) => (
                      <div className="anomaly-evidence-row" key={`${item.key}-${item.kind}`}>
                        <span>{item.key} · {item.kind}</span><span>{item.value}</span>
                      </div>
                    ))}
                  </div>
                  <div data-surface-id="anomalies.drawer.timeline" className="anomalies-timeline-card">
                    <strong>工作流時間軸</strong>
                    {anomalyDetail.detailTimeline.length === 0 && <span>尚無工作流事件。</span>}
                    {anomalyDetail.detailTimeline.map((event) => (
                      <div className="anomaly-recovery-metadata-row" key={`${event.correlationId}-${event.resultingVersion}`}>
                        <span>{event.action} · {event.createdAt}</span>
                        <span>v{event.expectedVersion} → v{event.resultingVersion}；{event.actor}；{event.reason}；{event.correlationId}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div data-surface-id="anomalies.drawer.root-evidence" className="anomalies-root-evidence-card root-evidence">
              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19', marginBottom: '8px' }}>
                🔍 根事實觸發證據 (Root-Fact Trigger Evidence)：
              </h4>
              {!anomalyDetail && <div className="anomalies-detail-empty">等待 typed root fact。</div>}
              {anomalyDetail?.rootFacts.map((item) => (
                <div className="anomaly-evidence-row" key={item.key}>
                  <span>{item.key} · {item.kind}</span><span>{item.value}</span>
                </div>
              ))}
            </div>

            <div data-surface-id="anomalies.drawer.recovery" className="anomalies-recovery-card recovery">
              <h4>🎯 Recovery metadata（唯讀）</h4>
              {selectedAnomaly.staffCalendarNavigation && (
                <a href="#scheduling">
                  前往排班調度 ➔（目標日期: {selectedAnomaly.staffCalendarNavigation.target_date}，月嫂 ID: #{selectedAnomaly.staffCalendarNavigation.staff_id}）
                </a>
              )}
              {anomalyRecoveryError && <div className="anomalies-detail-error">{anomalyRecoveryError}</div>}
              {anomalyDetail && <>
                <div className="anomaly-recovery-metadata-row"><span>projection freshness</span><span>{anomalyDetail.projectionFreshness}</span></div>
                <div className="anomaly-recovery-metadata-row"><span>domain blocker</span><span>{String(anomalyDetail.domainBlockerActive)}</span></div>
                <div className="anomaly-recovery-metadata-row"><span>occurrences</span><span>{anomalyDetail.occurrences.length}</span></div>
                {anomalyDetail.actions.length === 0 && <div className="anomalies-detail-empty">沒有可用的 recovery action。</div>}
                {anomalyDetail.actions.map((action) => (
                  <div className="anomaly-recovery-metadata-row" key={action.key}>
                    <span>{action.label} · v{action.contractVersion}</span>
                    <span>owner={action.owner}；preview={action.previewOperation}；apply={action.applyOperation ?? 'none'}；bindings={action.bindings.join(', ') || 'none'}；inputs={action.requiredInputs.join(', ') || 'none'}；predicate={action.completionPredicate}</span>
                  </div>
                ))}
              </>}
            </div>

            {/* Resolution Form (Locked in Query Mode) */}
            <div style={{ border: '1px solid #dec0b6', padding: '16px', borderRadius: '12px', backgroundColor: '#fff' }}>
              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19', marginBottom: '10px' }}>
                ✍️ 排除異常處置紀錄 (Resolve Reason)：
              </h4>
              <textarea
                data-control-id="anomalies.drawer.resolve-reason"
                disabled={true}
                rows={3}
                value=""
                placeholder="[查詢模式] 排除異常處置紀錄需待變更合約開放..."
                style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.9rem', backgroundColor: '#f9f9f9', cursor: 'not-allowed' }}
              />
            </div>
          </div>
        )}
        {selectedWarning && (
          <div data-surface-id="anomalies.drawer" style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            <div data-surface-id="anomalies.drawer.referral" style={{ border: '1px solid #dec0b6', padding: '18px', borderRadius: '12px', backgroundColor: '#fff' }}>
              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19', marginBottom: '10px' }}>🔗 Owning referral（唯讀）</h4>
              {warningReferralLoading && <div className="anomalies-loading">正在載入匯入警示導向...</div>}
              {!warningReferralLoading && (warningReferralError || !warningReferral) && (
                <div style={{ color: '#888' }}>後端 typed referral contract 尚未開放</div>
              )}
              {!warningReferralLoading && warningReferral && (
                <div style={{ color: '#57423b', lineHeight: '1.7' }}>
                  <div><strong>來源業面：</strong>{warningReferral.owningLane}</div>
                  <div><strong>欄位：</strong>{warningReferral.fieldPath}</div>
                  <div><strong>受遮罩主體：</strong>{warningReferral.maskedSubject}</div>
                  <div><strong>訊息：</strong>{warningReferral.displayMessage}</div>
                  <div><strong>導向類型：</strong>{warningReferral.actionKind}</div>
                  {warningReferral.navigationAction === 'hcm_import_center' && (
                    <a href="#data-import" data-surface-id="anomalies.navigation.data-import">前往匯入中心 ➔</a>
                  )}
                </div>
              )}
            </div>
            <div data-surface-id="anomalies.drawer.recovery" className="import-warning-transition-panel">
              <div className="import-warning-transition-heading">
                <div>
                  <h4>追蹤狀態 disposition</h4>
                  <p>只變更 warning tracking；不代表來源根事實已修復、重新匯入或 Anomaly Resolve。</p>
                </div>
                <button
                  type="button"
                  data-control-id="anomalies.import-warning.transition.open"
                  disabled={warningFlowLocked || warningFlowStatus !== 'idle'}
                  onClick={() => setWarningFlowStatus('editing')}
                >
                  開啟追蹤狀態變更
                </button>
              </div>

              {warningFlowStatus !== 'idle' && <>
                <label className="import-warning-transition-field">
                  <span>目標追蹤狀態</span>
                  <select
                    data-control-id="anomalies.import-warning.transition.action"
                    value={warningAction}
                    disabled={warningFlowLocked}
                    onChange={(event) => {
                      setWarningAction(event.target.value as WarningTransitionRequest['target_status']);
                      invalidateWarningPreview();
                    }}
                  >
                    <option value="awaiting_external_confirmation">等待外部確認</option>
                    <option value="response_recorded">已記錄回應</option>
                    <option value="reimport_requested">已請求重新匯入</option>
                    <option value="closed">關閉追蹤</option>
                  </select>
                </label>
                <label className="import-warning-transition-field">
                  <span>轉態理由代碼</span>
                  <input
                    data-control-id="anomalies.import-warning.transition.reason"
                    value={warningReason}
                    maxLength={100}
                    disabled={warningFlowLocked}
                    onChange={(event) => {
                      setWarningReason(event.target.value);
                      invalidateWarningPreview();
                    }}
                    placeholder="例：contact_started"
                  />
                </label>
                <div className="import-warning-transition-actions">
                  <button
                    type="button"
                    data-control-id="anomalies.import-warning.transition.preview"
                    disabled={warningFlowLocked || warningFlowStatus === 'preview_loading' || !warningReason.trim()}
                    onClick={() => void previewWarningTransition()}
                  >
                    {warningFlowStatus === 'preview_loading' ? '預覽中…' : '預覽追蹤狀態變更'}
                  </button>
                  <button
                    type="button"
                    data-control-id="anomalies.import-warning.transition.apply"
                    disabled={warningFlowStatus !== 'preview_ready'}
                    onClick={() => void applyWarningTransition(false)}
                  >
                    套用追蹤狀態變更
                  </button>
                  {warningFlowStatus === 'outcome_unknown' && (
                    <button type="button" data-control-id="anomalies.import-warning.transition.retry" onClick={() => void applyWarningTransition(true)}>
                      以原冪等鍵重試 Apply
                    </button>
                  )}
                  {warningFlowStatus === 'observation_failed' && warningReceipt && (
                    <button type="button" data-control-id="anomalies.import-warning.transition.observe" onClick={() => void observeWarningReceipt(warningReceipt, warningFlowSeq.current)}>
                      重試 receipt 觀察
                    </button>
                  )}
                </div>
              </>}

              {warningPreview && (
                <div className="import-warning-transition-preview">
                  <strong>Preview（零寫入）</strong>
                  <span>{warningPreview.resultingStatus} · v{warningPreview.resultingVersion}</span>
                </div>
              )}
              {warningReceipt && (
                <div className="import-warning-transition-receipt">
                  <strong>Terminal receipt</strong>
                  <span>{warningReceipt.receiptIdentity}</span>
                  <span>{warningReceipt.beforeStatus} → {warningReceipt.afterStatus} · v{warningReceipt.resultingVersion}</span>
                  <span>correlation={warningReceipt.correlationId} · replayed={String(warningReceipt.replayed)}</span>
                </div>
              )}
              {warningFlowStatus === 'observed' && (
                <div className="import-warning-transition-observed">已經 authenticated receipt re-query 觀察到一致版本；只代表 tracking disposition 完成。</div>
              )}
              {warningFlowStatus === 'outcome_unknown' && (
                <div className="import-warning-transition-warning">Apply 結果未明；已保留原 payload 與冪等鍵，只能原鍵重試。</div>
              )}
              {warningFlowStatus === 'observation_failed' && (
                <div className="import-warning-transition-warning">Apply receipt 已收到，但觀察失敗；不得顯示 Apply 失敗。</div>
              )}
              {warningFlowStatus === 'stale' && (
                <div className="import-warning-transition-warning">版本已變更；已重查清單，請關閉後重開並再次 Preview。</div>
              )}
              {warningFlowError && <div className="anomalies-detail-error">{warningFlowError}</div>}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default AnomaliesPage;
