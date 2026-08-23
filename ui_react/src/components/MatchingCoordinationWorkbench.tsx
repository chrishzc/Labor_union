/**
 * File: MatchingCoordinationWorkbench.tsx
 * Description: 提供 M3 媒合協調 Query、七種 Preview 與八種 Apply 的 typed 進階操作台。
 */
import React, { useMemo, useState } from 'react';
import {
  matchingCoordinationClient,
} from '../api/matching_coordination/matching_coordination_client';
import type {
  ApplyCaregiverSelectionRequest,
  ApplyCriteriaDiffRequest,
  ApplyCustomerDecisionRequest,
  ApplyInitialCriteriaRequest,
  ApplyLeaveImpactRequest,
  ApplyRematchRequest,
  ApplyServiceDateRematchRequest,
  ApplyZeroCandidateRequest,
  CriteriaDiff,
  LeaveImpactPreviewResponse,
  MatchingCriteriaSnapshot,
  MatchingPackage,
  PreviewCriteriaDiffRequest,
  PreviewInitialCriteriaRequest,
  PreviewLeaveImpactRequest,
  PreviewMatchingPackageRequest,
  PreviewRematchRequest,
  PreviewServiceDateRematchRequest,
  PreviewZeroCandidateRequest,
  ServiceDateRematchPreviewResponse,
  ZeroCandidateAlternative,
} from '../api/matching_coordination/matching_coordination_schemas';
import {
  toMatchingApplyReceiptView,
  toMatchingCoordinationQueryView,
  type MatchingApplyReceiptView,
  type MatchingCoordinationQueryView,
} from '../adapters/matching_coordination/matching_coordination_adapter';

type Operation =
  | 'previewInitialCriteria'
  | 'previewMatchingPackage'
  | 'previewCriteriaDiff'
  | 'previewZeroCandidate'
  | 'previewRematch'
  | 'previewLeaveImpact'
  | 'previewServiceDateRematch'
  | 'applyInitialCriteria'
  | 'applyCriteriaDiff'
  | 'applyCaregiverSelection'
  | 'applyCustomerDecision'
  | 'applyZeroCandidate'
  | 'applyRematch'
  | 'applyLeaveImpact'
  | 'applyServiceDateRematch';

interface PreviewSummary {
  title: string;
  status: string;
  identity: string;
  fingerprint: string | null;
  details: string[];
}

const OPERATIONS: ReadonlyArray<readonly [Operation, string]> = [
  ['previewInitialCriteria', 'Preview｜建立初始條件快照'],
  ['previewMatchingPackage', 'Preview｜建立媒合方案'],
  ['previewCriteriaDiff', 'Preview｜條件差異與重新聯絡'],
  ['previewZeroCandidate', 'Preview｜零候選替代方案'],
  ['previewRematch', 'Preview｜重新媒合'],
  ['previewLeaveImpact', 'Preview｜請假影響'],
  ['previewServiceDateRematch', 'Preview｜服務日期變更'],
  ['applyInitialCriteria', 'Apply｜提交初始條件'],
  ['applyCriteriaDiff', 'Apply｜提交條件差異'],
  ['applyCaregiverSelection', 'Apply｜月嫂意願決定'],
  ['applyCustomerDecision', 'Apply｜客戶媒合決定'],
  ['applyZeroCandidate', 'Apply｜零候選決定'],
  ['applyRematch', 'Apply｜提交重新媒合'],
  ['applyLeaveImpact', 'Apply｜提交請假影響'],
  ['applyServiceDateRematch', 'Apply｜提交服務日期變更'],
];

function operationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function displayMatchingError(caught: unknown, fallback: string): string {
  const message = caught instanceof Error ? caught.message : '';
  if (message.includes('orders_service_dates not_confirmed')) return '案件服務日期尚未確認，請先到訂單管理完成服務日期確認後再查詢。';
  if (message.includes('matching_criteria_snapshot unavailable')) return '本案件尚未建立媒合條件快照；請先執行初始條件 Preview，核對後再提交。';
  if (message.includes('source') && message.includes('unavailable')) return '此案件的媒合來源資料尚未完整，請依錯誤來源補正後重試。';
  return message || fallback;
}

function templateFor(operation: Operation, current: MatchingCoordinationQueryView | null, fingerprint: string | null): string {
  const sourceVersions = current?.sourceVersions ?? { items: [] };
  const snapshotId = current?.snapshot.snapshot_id ?? '';
  const matchingPackage = current?.matchingPackage;
  const packageId = matchingPackage?.package_id ?? '';
  const packageVersion = matchingPackage?.version ?? 0;
  const candidateId = current?.candidates[0]?.candidate_id ?? '';
  const requiredDates = matchingPackage?.required_service_dates ?? [];
  const common = { reason: '工會人員於媒合協調工作台確認', expected_source_versions: sourceVersions };
  const previewFingerprint = fingerprint ?? '';
  switch (operation) {
    case 'previewInitialCriteria': return JSON.stringify(common, null, 2);
    case 'previewMatchingPackage': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, required_service_dates: requiredDates, segments: [] }, null, 2);
    case 'previewCriteriaDiff': return JSON.stringify({ ...common, before_snapshot_id: snapshotId, after_snapshot_id: '' }, null, 2);
    case 'previewZeroCandidate': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, policy_id: '', policy_version: 1, relaxed_criteria: [] }, null, 2);
    case 'previewRematch': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId || null }, null, 2);
    case 'previewLeaveImpact': return JSON.stringify({ ...common, package_id: packageId, criteria_snapshot_id: snapshotId, receipt_key: '', expected_leave_version: 1, original_staff_id: 1 }, null, 2);
    case 'previewServiceDateRematch': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId || null, assignment_id: 1, original_staff_id: 1, original_service_dates: requiredDates, shifted_service_dates: [] }, null, 2);
    case 'applyInitialCriteria': return JSON.stringify({ ...common, preview_fingerprint: previewFingerprint }, null, 2);
    case 'applyCriteriaDiff': return JSON.stringify({ ...common, before_snapshot_id: snapshotId, after_snapshot_id: '', preview_fingerprint: previewFingerprint, recipient_ids: [] }, null, 2);
    case 'applyCaregiverSelection': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId, package_version: packageVersion, candidate_id: candidateId, willingness: 'willing', reason_code: null, affected_criteria: [], preview_fingerprint: previewFingerprint }, null, 2);
    case 'applyCustomerDecision': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId, package_version: packageVersion, candidate_id: candidateId || null, decision: 'accepted', preview_fingerprint: previewFingerprint }, null, 2);
    case 'applyZeroCandidate': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, policy_id: '', policy_version: 1, relaxed_criteria: [], alternative_id: '', preview_fingerprint: previewFingerprint, decision: 'agree' }, null, 2);
    case 'applyRematch': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId || null, preview_fingerprint: previewFingerprint }, null, 2);
    case 'applyLeaveImpact': return JSON.stringify({ ...common, package_id: packageId, leave_reference: '', criteria_snapshot_id: snapshotId, expected_leave_version: 1, original_staff_id: 1, preview_fingerprint: previewFingerprint }, null, 2);
    case 'applyServiceDateRematch': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId || null, assignment_id: 1, original_staff_id: 1, original_service_dates: requiredDates, shifted_service_dates: [], preview_fingerprint: previewFingerprint }, null, 2);
  }
}

function packageSummary(title: string, value: MatchingPackage): PreviewSummary {
  return { title, status: value.state, identity: value.package_id, fingerprint: value.fingerprint, details: [`候選 ${value.candidate_results.length} 人`, `區段 ${value.segments.length} 段`, ...value.blockers, ...value.warnings] };
}

export const MatchingCoordinationWorkbench: React.FC = () => {
  const [caseNo, setCaseNo] = useState('');
  const [operation, setOperation] = useState<Operation>('previewInitialCriteria');
  const [payloadText, setPayloadText] = useState(() => templateFor('previewInitialCriteria', null, null));
  const [query, setQuery] = useState<MatchingCoordinationQueryView | null>(null);
  const [preview, setPreview] = useState<PreviewSummary | null>(null);
  const [receipt, setReceipt] = useState<MatchingApplyReceiptView | null>(null);
  const [lastPreviewFingerprint, setLastPreviewFingerprint] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isApply = operation.startsWith('apply');
  const operationLabel = useMemo(() => OPERATIONS.find(([id]) => id === operation)?.[1] ?? operation, [operation]);

  const loadTemplate = (nextOperation = operation) => {
    setPayloadText(templateFor(nextOperation, query, lastPreviewFingerprint));
    setConfirmed(false);
    setError(null);
  };

  const runQuery = async () => {
    if (!caseNo.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const value = toMatchingCoordinationQueryView(await matchingCoordinationClient.query(caseNo.trim(), { expected_source_versions: null }));
      setQuery(value);
      setPayloadText(templateFor(operation, value, lastPreviewFingerprint));
    } catch (caught: unknown) {
      setError(displayMatchingError(caught, '媒合協調查詢失敗。'));
    } finally {
      setBusy(false);
    }
  };

  const runOperation = async () => {
    if (!caseNo.trim() || (isApply && !confirmed)) return;
    setBusy(true);
    setError(null);
    setPreview(null);
    setReceipt(null);
    try {
      const parsed: unknown = JSON.parse(payloadText);
      const options = { correlationId: operationIdentity(`matching-${operation}`), idempotencyKey: operationIdentity(`matching-${operation}-apply`) };
      let summary: PreviewSummary | null = null;
      let applyReceipt: MatchingApplyReceiptView | null = null;
      switch (operation) {
        case 'previewInitialCriteria': {
          const value: MatchingCriteriaSnapshot = await matchingCoordinationClient.previewInitialCriteria(caseNo.trim(), parsed as PreviewInitialCriteriaRequest, options);
          summary = { title: '初始條件快照', status: 'previewed', identity: value.snapshot_id, fingerprint: value.fingerprint, details: [`條件版本 ${value.criteria_version}`, `條件 ${value.criteria.length} 項`] };
          break;
        }
        case 'previewMatchingPackage': summary = packageSummary('媒合方案', await matchingCoordinationClient.previewMatchingPackage(caseNo.trim(), parsed as PreviewMatchingPackageRequest, options)); break;
        case 'previewCriteriaDiff': {
          const value: CriteriaDiff = await matchingCoordinationClient.previewCriteriaDiff(caseNo.trim(), parsed as PreviewCriteriaDiffRequest, options);
          summary = { title: '條件差異', status: value.resend_eligible ? '可重新聯絡' : '不需重新聯絡', identity: `${value.before_snapshot_id} → ${value.after_snapshot_id}`, fingerprint: value.diff_fingerprint, details: [`新增 ${value.added.length}`, `變更 ${value.changed.length}`, `移除 ${value.removed.length}`, `重新聯絡路由 ${value.refusal_routes.length}`] };
          break;
        }
        case 'previewZeroCandidate': {
          const value: ZeroCandidateAlternative = await matchingCoordinationClient.previewZeroCandidate(caseNo.trim(), parsed as PreviewZeroCandidateRequest, options);
          summary = { title: '零候選替代方案', status: value.candidate_result ? '找到替代候選' : '仍無候選', identity: value.alternative_id, fingerprint: value.preview_fingerprint, details: [`排序 ${value.deterministic_rank}`, ...value.risk_warnings] };
          break;
        }
        case 'previewRematch': summary = packageSummary('重新媒合方案', await matchingCoordinationClient.previewRematch(caseNo.trim(), parsed as PreviewRematchRequest, options)); break;
        case 'previewLeaveImpact': {
          const value: LeaveImpactPreviewResponse = await matchingCoordinationClient.previewLeaveImpact(caseNo.trim(), parsed as PreviewLeaveImpactRequest, options);
          summary = { title: '請假影響', status: value.result_state, identity: value.receipt_key, fingerprint: value.preview_fingerprint, details: [`處理方式 ${value.resolution_type}`, `需重新媒合：${value.rematch_required ? '是' : '否'}`] };
          break;
        }
        case 'previewServiceDateRematch': {
          const value: ServiceDateRematchPreviewResponse = await matchingCoordinationClient.previewServiceDateRematch(caseNo.trim(), parsed as PreviewServiceDateRematchRequest, options);
          const identity = value.availability_confirmation?.intent_id ?? value.reassignment_reference?.queue_reference ?? '—';
          summary = { title: '服務日期變更', status: value.outcome_kind, identity, fingerprint: value.availability_confirmation?.source_fingerprint ?? value.reassignment_reference?.source_fingerprint ?? null, details: [value.outcome_kind === 'availability_confirmation' ? '可確認新日期檔期' : '已建立重新指派參考'] };
          break;
        }
        case 'applyInitialCriteria': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyInitialCriteria(caseNo.trim(), parsed as ApplyInitialCriteriaRequest, options)); break;
        case 'applyCriteriaDiff': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyCriteriaDiff(caseNo.trim(), parsed as ApplyCriteriaDiffRequest, options)); break;
        case 'applyCaregiverSelection': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyCaregiverSelection(caseNo.trim(), parsed as ApplyCaregiverSelectionRequest, options)); break;
        case 'applyCustomerDecision': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyCustomerDecision(caseNo.trim(), parsed as ApplyCustomerDecisionRequest, options)); break;
        case 'applyZeroCandidate': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyZeroCandidate(caseNo.trim(), parsed as ApplyZeroCandidateRequest, options)); break;
        case 'applyRematch': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyRematch(caseNo.trim(), parsed as ApplyRematchRequest, options)); break;
        case 'applyLeaveImpact': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyLeaveImpact(caseNo.trim(), parsed as ApplyLeaveImpactRequest, options)); break;
        case 'applyServiceDateRematch': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyServiceDateRematch(caseNo.trim(), parsed as ApplyServiceDateRematchRequest, options)); break;
      }
      if (summary) {
        setPreview(summary);
        setLastPreviewFingerprint(summary.fingerprint);
      }
      if (applyReceipt) {
        setReceipt(applyReceipt);
        setConfirmed(false);
        await runQuery();
      }
    } catch (caught: unknown) {
      setError(displayMatchingError(caught, `${operationLabel}執行失敗。`));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="gantt-hero-card" data-surface-id="scheduling.matching-coordination">
      <div className="line-section-heading"><div><h2>媒合與正式排班查詢工作台</h2><p>所有結果由 Matching Coordination 後端規則產生；Query／Preview 零寫入，Apply 會重新驗證來源版本。</p></div></div>
      <div className="waiting-lock-control"><label htmlFor="matching-case-no">案件編號</label><input id="matching-case-no" value={caseNo} onChange={(event) => { setCaseNo(event.target.value); setQuery(null); }} /><button type="button" disabled={!caseNo.trim() || busy} onClick={() => void runQuery()}>{busy ? '處理中…' : '查詢媒合根事實'}</button></div>
      {query && <><div className="line-detail-grid"><div><span>條件快照</span><strong>{query.snapshot.snapshot_id}</strong></div><div><span>條件版本</span><strong>{query.snapshot.criteria_version}</strong></div><div><span>媒合方案</span><strong>{query.matchingPackage?.package_id ?? '尚未建立'}</strong></div><div><span>來源版本</span><strong>{query.expectedSourceVersionsMatch ? '一致' : '已變更'}</strong></div><div><span>候選人</span><strong>{query.candidates.length}</strong></div><div><span>拒絕歷史</span><strong>{query.refusalHistory.length}</strong></div></div>{query.candidates.length > 0 && <div className="line-table-scroll"><table className="line-data-table"><thead><tr><th>服務人員</th><th>資格</th><th>意願</th><th>拒絕原因</th></tr></thead><tbody>{query.candidates.map((candidate) => <tr key={candidate.candidate_id}><td>{candidate.staff_name}</td><td>{candidate.eligibility}</td><td>{candidate.willingness}</td><td>{candidate.rejection_reasons.join('、') || '無'}</td></tr>)}</tbody></table></div>}</>}
      <div className="line-action-panel"><label htmlFor="matching-operation">操作</label><select id="matching-operation" value={operation} onChange={(event) => { const next = event.target.value as Operation; setOperation(next); setPayloadText(templateFor(next, query, lastPreviewFingerprint)); setConfirmed(false); }}>{OPERATIONS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select><button type="button" onClick={() => loadTemplate()}>依目前查詢重建欄位模板</button><label htmlFor="matching-payload">Typed request 欄位</label><textarea id="matching-payload" rows={18} spellCheck={false} value={payloadText} onChange={(event) => { setPayloadText(event.target.value); setConfirmed(false); }} />{isApply && <label><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />我已核對 Preview、來源版本與即將提交的決定</label>}<button type="button" disabled={!caseNo.trim() || busy || (isApply && !confirmed)} onClick={() => void runOperation()}>{busy ? '處理中…' : operationLabel}</button></div>
      {preview && <div className="line-preview-result" role="status"><h3>{preview.title}</h3><p>{preview.status}｜{preview.identity}</p>{preview.fingerprint && <p>fingerprint：{preview.fingerprint}</p>}<ul>{preview.details.map((detail, index) => <li key={`${detail}-${index}`}>{detail}</li>)}</ul></div>}
      {receipt && <div className="line-success" role="status"><h3>Apply 已提交</h3><p>{receipt.commandName}｜{receipt.resultState}</p><p>receipt：{receipt.receiptId}</p></div>}
      {error && <div className="line-error" role="alert">{error}</div>}
    </section>
  );
};

export default MatchingCoordinationWorkbench;
