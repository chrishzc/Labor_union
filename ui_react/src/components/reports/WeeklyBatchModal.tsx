/**
 * File: WeeklyBatchModal.tsx
 * Description: 營運週報批次結算與指標管理彈窗元件 (方案 C 封存機制)
 */
import React, { useEffect, useState } from 'react';
import {
  fetchWeeklyBatches,
  fetchUnclosedCases,
  closeWeeklyBatch,
  updateWeeklyBatch,
  type WeeklyBatchItem,
  type UnclosedCaseItem,
} from '../../api/reports/weekly_report_batch_client';

export interface WeeklyBatchModalProps {
  isOpen: boolean;
  onClose: () => void;
  year: number;
  onBatchClosed: () => void;
}

export const WeeklyBatchModal: React.FC<WeeklyBatchModalProps> = ({
  isOpen,
  onClose,
  year,
  onBatchClosed,
}) => {
  const [batches, setBatches] = useState<WeeklyBatchItem[]>([]);
  const [unclosedCases, setUnclosedCases] = useState<UnclosedCaseItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const [targetWeekCode, setTargetWeekCode] = useState('');
  const [targetPromo, setTargetPromo] = useState('0');
  const [targetInq, setTargetInq] = useState('0');
  const [notes, setNotes] = useState('');
  const [editingMetrics, setEditingMetrics] = useState<Record<number, { promo: number; inq: number }>>({});
  const [savingBatchId, setSavingBatchId] = useState<number | null>(null);

  const loadData = async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const [batchList, unclosedList] = await Promise.all([
        fetchWeeklyBatches(year),
        fetchUnclosedCases(year),
      ]);
      setBatches(batchList);
      setUnclosedCases(unclosedList);
      if (batchList.length > 0) {
        const lastCode = batchList[batchList.length - 1].week_code;
        const match = lastCode.match(/^(\d+)-(\d+)$/);
        if (match) {
          const m = Number(match[1]);
          const w = Number(match[2]);
          setTargetWeekCode(`${m}-${w + 1}`);
        } else {
          setTargetWeekCode(`${new Date().getMonth() + 1}-1`);
        }
      } else {
        setTargetWeekCode(`${new Date().getMonth() + 1}-1`);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '載入資料失敗');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      void loadData();
    }
  }, [isOpen, year]);

  if (!isOpen) return null;

  const handleCloseBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetWeekCode.trim()) {
      setErrorMsg('請輸入週代碼（例如 6-2）');
      return;
    }
    setSubmitting(true);
    setErrorMsg('');
    setSuccessMsg('');
    try {
      await closeWeeklyBatch({
        year,
        week_code: targetWeekCode.trim(),
        promotion_count: Number(targetPromo) || 0,
        inquiry_count: Number(targetInq) || 0,
        notes: notes.trim() || undefined,
      });
      setSuccessMsg(`週次 ${targetWeekCode} 結算成功！已凍結 ${unclosedCases.length} 筆案件。`);
      setTargetPromo('0');
      setTargetInq('0');
      setNotes('');
      await loadData();
      onBatchClosed();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '結算失敗');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdateMetrics = async (batchId: number) => {
    const batch = batches.find((item) => item.id === batchId);
    const current = editingMetrics[batchId] ?? (batch ? { promo: batch.promotion_count, inq: batch.inquiry_count } : null);
    if (!current) return;
    setSavingBatchId(batchId);
    setErrorMsg('');
    setSuccessMsg('');
    try {
      await updateWeeklyBatch(batchId, {
        promotion_count: current.promo,
        inquiry_count: current.inq,
      });
      setSuccessMsg(`週別 ${batch?.week_code || ''} 指標已成功儲存至資料庫！`);
      await loadData();
      onBatchClosed();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '更新失敗');
    } finally {
      setSavingBatchId(null);
    }
  };

  return (
    <div className="reports-modal-overlay" onClick={onClose}>
      <div className="reports-modal" onClick={(e) => e.stopPropagation()}>
        <div className="reports-modal-header">
          <h3>📑 週報結算與指標管理 ({year} 年度)</h3>
          <button type="button" className="reports-modal-close" onClick={onClose} aria-label="關閉">×</button>
        </div>

        {errorMsg && <div className="reports-state error">{errorMsg}</div>}
        {successMsg && <div className="reports-state" style={{ background: '#ecfdf5', borderColor: '#10b981', color: '#065f46' }}>{successMsg}</div>}
        {loading && <div className="reports-state">正在讀取批次資料…</div>}

        <div className="batch-section">
          <h4>📌 結算當期週報 (方案 C 封存機制)</h4>
          <p style={{ fontSize: '0.82rem', color: '#64748b', margin: '0 0 10px 0' }}>
            結算後，當前 <strong>{unclosedCases.length} 筆</strong> 待結算新進案件將全數凍結歸屬至本期週次。結算後新建立之訂單將自動順延至下一期。
          </p>
          <form onSubmit={handleCloseBatch}>
            <div className="batch-form-grid">
              <label>
                週代碼 (如 6-2)
                <input
                  type="text"
                  required
                  placeholder="例如 6-2"
                  value={targetWeekCode}
                  onChange={(e) => setTargetWeekCode(e.target.value)}
                />
              </label>
              <label>
                本週推廣次數
                <input
                  type="number"
                  min="0"
                  value={targetPromo}
                  onChange={(e) => setTargetPromo(e.target.value)}
                />
              </label>
              <label>
                本週詢問人次
                <input
                  type="number"
                  min="0"
                  value={targetInq}
                  onChange={(e) => setTargetInq(e.target.value)}
                />
              </label>
              <label>
                備註說明 (選填)
                <input
                  type="text"
                  placeholder="備註"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </label>
            </div>
            <button type="submit" className="batch-btn-primary" disabled={submitting}>
              {submitting ? '結算中…' : `確認出具並結算 ${targetWeekCode || ''} 週報`}
            </button>
          </form>
        </div>

        <div className="batch-section">
          <h4>⏳ 待結算新進案件池 ({unclosedCases.length} 筆)</h4>
          {unclosedCases.length === 0 ? (
            <p style={{ fontSize: '0.82rem', color: '#64748b' }}>目前沒有待結算案件，所有案件皆已歸入過往週報批次。</p>
          ) : (
            <div style={{ maxHeight: '160px', overflowY: 'auto' }}>
              <table className="batch-table">
                <thead>
                  <tr>
                    <th>案號</th>
                    <th>申請人</th>
                    <th>訂單成立時間</th>
                    <th>狀態</th>
                    <th>預計服務天數</th>
                  </tr>
                </thead>
                <tbody>
                  {unclosedCases.map((c) => (
                    <tr key={c.case_no}>
                      <td>{c.case_no}</td>
                      <td>{c.applicant_name}</td>
                      <td>{c.created_at ? c.created_at.replace('T', ' ').slice(0, 16) : '—'}</td>
                      <td>{c.order_status || '—'}</td>
                      <td>{c.service_days ? `${c.service_days} 天` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="batch-section">
          <h4>📊 已結算週次指標清單 ({batches.length} 週)</h4>
          <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
            <table className="batch-table">
              <thead>
                <tr>
                  <th>週別</th>
                  <th>封存時間</th>
                  <th>綁定案件數</th>
                  <th>推廣次數</th>
                  <th>詢問人次</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => {
                  const edit = editingMetrics[b.id] ?? { promo: b.promotion_count, inq: b.inquiry_count };
                  const isDirty = edit.promo !== b.promotion_count || edit.inq !== b.inquiry_count;
                  return (
                    <tr key={b.id}>
                      <td style={{ fontWeight: 'bold' }}>{b.week_code}</td>
                      <td>{b.cutoff_at.replace('T', ' ').slice(0, 16)}</td>
                      <td>{b.case_count} 案</td>
                      <td>
                        <input
                          type="number"
                          style={{ width: '70px', textAlign: 'center', padding: '2px 4px' }}
                          value={edit.promo}
                          onChange={(e) =>
                            setEditingMetrics({
                              ...editingMetrics,
                              [b.id]: { ...edit, promo: Number(e.target.value) },
                            })
                          }
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          style={{ width: '70px', textAlign: 'center', padding: '2px 4px' }}
                          value={edit.inq}
                          onChange={(e) =>
                            setEditingMetrics({
                              ...editingMetrics,
                              [b.id]: { ...edit, inq: Number(e.target.value) },
                            })
                          }
                        />
                      </td>
                      <td>
                        <button
                          type="button"
                          disabled={savingBatchId === b.id}
                          style={{
                            padding: '4px 10px',
                            fontSize: '0.8rem',
                            borderRadius: '4px',
                            cursor: savingBatchId === b.id ? 'not-allowed' : 'pointer',
                            background: '#2563eb',
                            color: '#fff',
                            border: 'none',
                            fontWeight: 600,
                          }}
                          onClick={() => void handleUpdateMetrics(b.id)}
                        >
                          {savingBatchId === b.id ? '儲存中…' : '儲存'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
