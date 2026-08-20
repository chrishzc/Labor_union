/**
 * File: AnomaliesPage.tsx
 * Description: Anomalies list、warning list 與 lazy GET Drawer。
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import './AnomaliesPage.css';
import { Drawer } from '../components/Drawer';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import {
  adaptAnomalySummary,
  adaptImportWarningTask,
  adaptAnomalyDetail,
  adaptImportWarningReferral,
  calculateAnomalyKPIs,
  filterAnomalies,
  CATEGORY_TAB_KEYS,
  type CategoryTabKey,
  type AnomalySummaryViewModel,
  type ImportWarningTaskViewModel,
  type AnomalyDetailViewModel,
  type ImportWarningReferralViewModel,
} from '../adapters/anomalies/anomaly_query_adapter';

export const AnomaliesPage: React.FC = () => {
  const [selectedCategory, setSelectedCategory] = useState<CategoryTabKey>('全部');
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<'all' | 'open' | 'claimed' | 'resolved'>('all');
  const [selectedAnomaly, setSelectedAnomaly] = useState<AnomalySummaryViewModel | null>(null);
  const [selectedWarning, setSelectedWarning] = useState<ImportWarningTaskViewModel | null>(null);

  const [anomalyDetail, setAnomalyDetail] = useState<AnomalyDetailViewModel | null>(null);
  const [anomalyDetailLoading, setAnomalyDetailLoading] = useState(false);
  const [anomalyDetailError, setAnomalyDetailError] = useState<string | null>(null);
  const [warningReferral, setWarningReferral] = useState<ImportWarningReferralViewModel | null>(null);
  const [warningReferralLoading, setWarningReferralLoading] = useState(false);
  const [warningReferralError, setWarningReferralError] = useState<string | null>(null);

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
  const anomalyListAbortController = useRef<AbortController | null>(null);
  const importWarningListAbortController = useRef<AbortController | null>(null);
  const drawerRequestSeq = useRef<number>(0);
  const drawerAbortController = useRef<AbortController | null>(null);

  // Fetch Anomalies from live API
  const fetchAnomalies = useCallback(async () => {
    const seq = ++anomalyRequestSeq.current;
    anomalyListAbortController.current?.abort();
    const controller = new AbortController();
    anomalyListAbortController.current = controller;
    setAnomaliesLoading(true);
    setAnomaliesError(null);

    try {
      const rawList = await anomalyQueryClient.queryAnomalies(
        { activeOnly: true },
        { signal: controller.signal }
      );
      if (seq === anomalyRequestSeq.current && !controller.signal.aborted) {
        const adaptedList = rawList.map(adaptAnomalySummary);
        setAnomalies(adaptedList);
      }
    } catch (err) {
      if (seq === anomalyRequestSeq.current && !controller.signal.aborted) {
        const msg = err instanceof Error ? err.message : '載入異常資料失敗';
        setAnomaliesError(msg);
      }
    } finally {
      if (seq === anomalyRequestSeq.current && !controller.signal.aborted) {
        setAnomaliesLoading(false);
      }
    }
  }, []);

  // Fetch Import Warning Tasks from live API
  const fetchImportWarnings = useCallback(async () => {
    const seq = ++importWarningRequestSeq.current;
    importWarningListAbortController.current?.abort();
    const controller = new AbortController();
    importWarningListAbortController.current = controller;
    setImportWarningsLoading(true);
    setImportWarningsError(null);

    try {
      const rawTasks = await anomalyQueryClient.queryImportWarningTasks(
        { activeOnly: true },
        { signal: controller.signal }
      );
      if (seq === importWarningRequestSeq.current && !controller.signal.aborted) {
        const adaptedTasks = rawTasks.map(adaptImportWarningTask);
        setImportWarnings(adaptedTasks);
      }
    } catch (err) {
      if (seq === importWarningRequestSeq.current && !controller.signal.aborted) {
        const msg = err instanceof Error ? err.message : '載入匯入警示資料失敗';
        setImportWarningsError(msg);
      }
    } finally {
      if (seq === importWarningRequestSeq.current && !controller.signal.aborted) {
        setImportWarningsLoading(false);
      }
    }
  }, []);

  const closeDrawer = useCallback(() => {
    drawerRequestSeq.current += 1;
    drawerAbortController.current?.abort();
    drawerAbortController.current = null;
    setSelectedAnomaly(null);
    setSelectedWarning(null);
    setAnomalyDetail(null);
    setWarningReferral(null);
    setAnomalyDetailLoading(false);
    setWarningReferralLoading(false);
  }, []);

  const openAnomalyDrawer = useCallback((anomaly: AnomalySummaryViewModel) => {
    const seq = ++drawerRequestSeq.current;
    drawerAbortController.current?.abort();
    const controller = new AbortController();
    drawerAbortController.current = controller;
    setSelectedAnomaly(anomaly);
    setSelectedWarning(null);
    setAnomalyDetail(null);
    setAnomalyDetailError(null);
    setAnomalyDetailLoading(true);
    setWarningReferral(null);
    void anomalyQueryClient
      .queryAnomalyDetail({ fingerprint: anomaly.fingerprint }, { signal: controller.signal })
      .then((detail) => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setAnomalyDetail(adaptAnomalyDetail(detail));
        }
      })
      .catch((err: unknown) => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setAnomalyDetailError(err instanceof Error ? err.message : '後端 typed detail contract 尚未開放');
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

  useEffect(() => {
    fetchAnomalies();
    fetchImportWarnings();
    return () => {
      anomalyRequestSeq.current += 1;
      importWarningRequestSeq.current += 1;
      anomalyListAbortController.current?.abort();
      importWarningListAbortController.current?.abort();
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
        title={selectedAnomaly ? `⚠️ 異常排查與修復處置 — ${selectedAnomaly.code}` : `📥 匯入警示詳情 — ${selectedWarning?.logicalCode ?? ''}`}
        footer={
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85rem', color: '#888' }}>
              💡 依 06_Anomalies_Domain 規範，修復記錄後若根因未除，系統將自動 reopen。
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
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
                  title="[查詢模式] 匯入警示狀態變更尚未開放"
                  style={{ padding: '8px 20px', backgroundColor: '#94a3b8', color: '#fff', border: 'none', borderRadius: '8px', fontWeight: 700, cursor: 'not-allowed' }}
                >
                  狀態變更尚未開放
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

            <div data-surface-id="anomalies.drawer.detail" style={{ border: '1px solid #dec0b6', padding: '16px', borderRadius: '12px', backgroundColor: '#fff' }}>
              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19', marginBottom: '8px' }}>📄 後端異常詳情 (Detail GET)</h4>
              {anomalyDetailLoading && <div className="anomalies-loading">正在載入異常詳情...</div>}
              {!anomalyDetailLoading && (anomalyDetailError || !anomalyDetail) && (
                <div data-surface-id="anomalies.drawer.timeline" style={{ color: '#888' }}>後端 typed detail/recovery contract 尚未開放</div>
              )}
              {!anomalyDetailLoading && anomalyDetail && (
                <>
                  <div data-surface-id="anomalies.drawer.timeline" style={{ color: '#57423b' }}>
                    {anomalyDetail.timelineAvailable
                      ? anomalyDetail.timeline.map((event) => (
                          <div key={`${event.action}-${event.resultingWorkflowVersion}-${event.createdAt}`}>
                            {event.action}：v{event.expectedWorkflowVersion} → v{event.resultingWorkflowVersion}（{event.createdAt}）
                          </div>
                        ))
                      : '後端尚未提供 typed timeline'}
                  </div>
                  <div data-surface-id="anomalies.drawer.evidence" style={{ color: '#888', marginTop: '8px' }}>
                    {anomalyDetail.actionsAvailable ? '後端 recovery action 已存在，但本頁尚未開放變更。' : '後端尚未提供 typed recovery action'}
                  </div>
                </>
              )}
            </div>

            {/* Root Cause Trigger Evidence */}
            <div data-surface-id="anomalies.drawer.root-evidence" style={{ border: '1px solid #dec0b6', padding: '16px', borderRadius: '12px', backgroundColor: '#fff' }}>
              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19', marginBottom: '8px' }}>
                🔍 根事實觸發證據 (Root-Fact Trigger Evidence)：
              </h4>
              <div style={{ backgroundColor: '#1e1b19', color: '#86efac', padding: '12px 14px', borderRadius: '8px', fontFamily: 'monospace', fontSize: '0.82rem', lineHeight: '1.4' }}>
                {`// Canonical Domain Diagnostic Evidence\n${selectedAnomaly.rootEvidence}`}
              </div>
            </div>

            {/* Human-Assisted Recovery Quick Action */}
            <div data-surface-id="anomalies.drawer.recovery" style={{ backgroundColor: '#fff8f6', border: '1px solid #fed9b8', padding: '16px 18px', borderRadius: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 700, color: '#c2410c', fontSize: '0.95rem' }}>🎯 建議引導處置路徑：</div>
                  <div style={{ fontSize: '0.85rem', color: '#74593f', marginTop: '2px' }}>
                    {selectedAnomaly.staffCalendarNavigation
                      ? `排班調度衝突 — 目標日期: ${selectedAnomaly.staffCalendarNavigation.target_date}，月嫂 ID: #${selectedAnomaly.staffCalendarNavigation.staff_id}`
                      : selectedAnomaly.suggestedAction}
                  </div>
                </div>
                {selectedAnomaly.staffCalendarNavigation ? (
                  <a
                    href="#scheduling"
                    style={{
                      display: 'inline-block',
                      padding: '8px 16px',
                      backgroundColor: '#ff7f50',
                      color: '#fff',
                      borderRadius: '8px',
                      fontWeight: 700,
                      fontSize: '0.85rem',
                      textDecoration: 'none',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    前往排班調度 ➔
                  </a>
                ) : (
                  <span style={{ fontSize: '0.82rem', color: '#888' }}>
                    後端 typed detail/recovery contract 尚未開放
                  </span>
                )}
              </div>
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
            <div data-surface-id="anomalies.drawer.recovery" style={{ color: '#888' }}>
              後端 transition／recovery action 尚未開放；本頁僅保留唯讀 referral。
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default AnomaliesPage;
