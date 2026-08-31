/**
 * File: MatchingCoordinationWorkbench.tsx
 * Description: 提供 M3 媒合協調 Query、八種 Preview 與九種 Apply 的 typed 進階操作台。
 */
import React, { useMemo, useRef, useState } from 'react';
import './MatchingCoordinationWorkbench.css';
import {
  matchingCoordinationClient,
} from '../api/matching_coordination/matching_coordination_client';
import {
  ApiNetworkError,
  ApiTimeoutError,
  MatchingCoordinationClientError,
} from '../api/matching_coordination/matching_coordination_errors';
import type {
  ApplyCaregiverSelectionRequest,
  ApplyCriteriaDiffRequest,
  ApplyCustomerDecisionRequest,
  ApplyInitialCriteriaRequest,
  ApplyLeaveImpactRequest,
  ApplyRematchRequest,
  ApplyServiceDateRematchRequest,
  ApplyZeroCandidateRequest,
  ApplyZeroCandidateConfirmationRequest,
  CriteriaDiff,
  LeaveImpactPreviewResponse,
  MatchingCriteriaSnapshot,
  MatchingSourceTuple,
  MatchingPackage,
  PreviewCriteriaDiffRequest,
  PreviewInitialCriteriaRequest,
  PreviewLeaveImpactRequest,
  PreviewMatchingPackageRequest,
  PreviewRematchRequest,
  PreviewServiceDateRematchRequest,
  PreviewZeroCandidateRequest,
  PreviewZeroCandidateConfirmationRequest,
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
  | 'previewZeroCandidateConfirmation'
  | 'previewRematch'
  | 'previewLeaveImpact'
  | 'previewServiceDateRematch'
  | 'applyInitialCriteria'
  | 'applyCriteriaDiff'
  | 'applyCaregiverSelection'
  | 'applyCustomerDecision'
  | 'applyZeroCandidate'
  | 'applyZeroCandidateConfirmation'
  | 'applyRematch'
  | 'applyLeaveImpact'
  | 'applyServiceDateRematch';

interface PreviewSummary {
  title: string;
  status: string;
  identity: string;
  fingerprint: string | null;
  details: string[];
  technicalDetails?: string[];
}

const OPERATION_GROUPS: ReadonlyArray<readonly [string, ReadonlyArray<readonly [Operation, string]>]> = [
  ['一般媒合流程', [
    ['previewInitialCriteria', '1. 試算初始媒合條件'],
    ['applyInitialCriteria', '2. 確認建立媒合條件快照'],
    ['previewMatchingPackage', '3. 試算可推薦月嫂與服務分段'],
    ['applyCaregiverSelection', '4. 確認月嫂意願與推薦組合'],
    ['applyCustomerDecision', '5. 登錄客戶媒合決定'],
  ]],
  ['條件變更與例外處理', [
    ['previewCriteriaDiff', '試算條件差異與重新聯絡'],
    ['applyCriteriaDiff', '確認條件差異處理'],
    ['previewZeroCandidate', '試算零候選替代方案'],
    ['applyZeroCandidate', '確認零候選處理'],
    ['previewZeroCandidateConfirmation', '試算確認目前確實無候選'],
    ['applyZeroCandidateConfirmation', '確認目前確實無候選'],
    ['previewRematch', '試算重新媒合'],
    ['applyRematch', '確認重新媒合'],
    ['previewLeaveImpact', '試算月嫂請假影響'],
    ['applyLeaveImpact', '確認請假影響處理'],
    ['previewServiceDateRematch', '試算服務日期變更'],
    ['applyServiceDateRematch', '確認服務日期變更'],
  ]],
];

const OPERATIONS = OPERATION_GROUPS.flatMap(([, operations]) => operations);

const REQUIRED_PREVIEW: Partial<Record<Operation, Operation>> = {
  applyInitialCriteria: 'previewInitialCriteria',
  applyCaregiverSelection: 'previewMatchingPackage',
  applyCustomerDecision: 'previewMatchingPackage',
  applyCriteriaDiff: 'previewCriteriaDiff',
  applyZeroCandidate: 'previewZeroCandidate',
  applyZeroCandidateConfirmation: 'previewZeroCandidateConfirmation',
  applyRematch: 'previewRematch',
  applyLeaveImpact: 'previewLeaveImpact',
  applyServiceDateRematch: 'previewServiceDateRematch',
};

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

function isOutcomeUnknown(caught: unknown): boolean {
  return caught instanceof ApiNetworkError
    || caught instanceof ApiTimeoutError
    || (
      caught instanceof MatchingCoordinationClientError
      && caught.retryable
      && (caught.category === 'unavailable' || caught.category === 'internal')
    );
}

function templateFor(
  operation: Operation,
  current: MatchingCoordinationQueryView | null,
  fingerprint: string | null,
  initialSourceVersions: MatchingSourceTuple | null = null,
): string {
  const sourceVersions = current?.sourceVersions ?? initialSourceVersions;
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
    case 'previewZeroCandidateConfirmation': return JSON.stringify({ ...common, evidence: ['fresh_pool_query_empty'], criteria_snapshot_id: snapshotId, package_id: packageId, package_version: packageVersion }, null, 2);
    case 'previewRematch': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId || null }, null, 2);
    case 'previewLeaveImpact': return JSON.stringify({ ...common, package_id: packageId, criteria_snapshot_id: snapshotId, receipt_key: '', expected_leave_version: 1, original_staff_id: 1 }, null, 2);
    case 'previewServiceDateRematch': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId || null, assignment_id: 1, original_staff_id: 1, original_service_dates: requiredDates, shifted_service_dates: [] }, null, 2);
    case 'applyInitialCriteria': return JSON.stringify({ ...common, preview_fingerprint: previewFingerprint }, null, 2);
    case 'applyCriteriaDiff': return JSON.stringify({ ...common, before_snapshot_id: snapshotId, after_snapshot_id: '', preview_fingerprint: previewFingerprint, recipient_ids: [] }, null, 2);
    case 'applyCaregiverSelection': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId, package_version: packageVersion, candidate_id: candidateId, willingness: 'willing', reason_code: null, affected_criteria: [], preview_fingerprint: previewFingerprint }, null, 2);
    case 'applyCustomerDecision': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId, package_version: packageVersion, candidate_id: candidateId || null, decision: 'accepted', preview_fingerprint: previewFingerprint }, null, 2);
    case 'applyZeroCandidate': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, policy_id: '', policy_version: 1, relaxed_criteria: [], alternative_id: '', preview_fingerprint: previewFingerprint, decision: 'agree' }, null, 2);
    case 'applyZeroCandidateConfirmation': return JSON.stringify({ ...common, evidence: ['fresh_pool_query_empty'], criteria_snapshot_id: snapshotId, package_id: packageId, package_version: packageVersion, preview_fingerprint: previewFingerprint }, null, 2);
    case 'applyRematch': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId || null, preview_fingerprint: previewFingerprint }, null, 2);
    case 'applyLeaveImpact': return JSON.stringify({ ...common, package_id: packageId, leave_reference: '', criteria_snapshot_id: snapshotId, expected_leave_version: 1, original_staff_id: 1, preview_fingerprint: previewFingerprint }, null, 2);
    case 'applyServiceDateRematch': return JSON.stringify({ ...common, criteria_snapshot_id: snapshotId, package_id: packageId || null, assignment_id: 1, original_staff_id: 1, original_service_dates: requiredDates, shifted_service_dates: [], preview_fingerprint: previewFingerprint }, null, 2);
  }
}

function packageSummary(title: string, value: MatchingPackage): PreviewSummary {
  const statusLabels: Record<MatchingPackage['state'], string> = {
    proposed: '媒合方案待確認',
    candidate_pool_open: '候選名單建立中',
    awaiting_caregiver_willingness: '等待服務人員確認意願',
    awaiting_customer_decision: '等待客戶決定',
    no_candidate: '目前沒有可用候選',
    rematch_required: '需要重新媒合',
  };
  return {
    title,
    status: statusLabels[value.state],
    identity: value.package_id,
    fingerprint: value.fingerprint,
    details: [`候選 ${value.candidate_results.length} 人`, `區段 ${value.segments.length} 段`],
    technicalDetails: [`原始狀態：${value.state}`, ...value.blockers, ...value.warnings],
  };
}

function resultStateLabel(value: string): string {
  const labels: Record<string, string> = {
    criteria_snapshotted: '媒合條件已建立',
    criteria_diff_applied: '條件差異已處理',
    caregiver_selected: '服務人員意願與推薦組合已確認',
    customer_decision_recorded: '客戶媒合決定已登錄',
    zero_candidate_applied: '零候選處理已完成',
    zero_candidate_confirmed: '已確認目前沒有合法候選',
    rematch_applied: '重新媒合已建立',
    leave_impact_applied: '請假影響已處理',
    service_date_rematch_applied: '服務日期變更已處理',
    leave_deferred: '後續指派已延後處理',
    availability_confirmation: '等待確認新日期檔期',
    reassignment_reference: '已建立重新指派參考',
  };
  return labels[value] ?? '處理結果待確認';
}

function eligibilityLabel(value: string): string {
  return value === 'eligible' ? '符合條件' : value === 'ineligible' ? '不符合條件' : '待確認';
}

function willingnessLabel(value: string): string {
  return value === 'willing' ? '願意承接' : value === 'unwilling' ? '不願承接' : '等待確認';
}

export interface MatchingCoordinationWorkbenchProps {
  /** The owning matching drawer supplies its current case; standalone use remains editable. */
  initialCaseNo?: string;
}

export const MatchingCoordinationWorkbench: React.FC<MatchingCoordinationWorkbenchProps> = ({ initialCaseNo = '' }) => {
  const [caseNo, setCaseNo] = useState(initialCaseNo);
  const [operation, setOperation] = useState<Operation>('previewInitialCriteria');
  const [payloadText, setPayloadText] = useState(() => templateFor('previewInitialCriteria', null, null));
  const [query, setQuery] = useState<MatchingCoordinationQueryView | null>(null);
  const [preview, setPreview] = useState<PreviewSummary | null>(null);
  const [receipt, setReceipt] = useState<MatchingApplyReceiptView | null>(null);
  const [lastPreviewFingerprint, setLastPreviewFingerprint] = useState<string | null>(null);
  const [lastPreviewOperation, setLastPreviewOperation] = useState<Operation | null>(null);
  const [initialPreviewSourceVersions, setInitialPreviewSourceVersions] = useState<MatchingSourceTuple | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [outcomeUnknown, setOutcomeUnknown] = useState(false);
  const zeroCandidateConfirmationAttempt = useRef<{
    identity: string;
    correlationId: string;
    idempotencyKey: string;
  } | null>(null);
  const isApply = operation.startsWith('apply');
  const embeddedInOrderWorkflow = initialCaseNo.trim().length > 0;
  const operationLabel = useMemo(() => OPERATIONS.find(([id]) => id === operation)?.[1] ?? operation, [operation]);
  const requiredPreview = REQUIRED_PREVIEW[operation];
  const hasRequiredPreview = !isApply || (
    lastPreviewOperation === requiredPreview && lastPreviewFingerprint !== null
  );

  const invalidateZeroCandidateConfirmationAttempt = () => {
    zeroCandidateConfirmationAttempt.current = null;
    setOutcomeUnknown(false);
  };

  const loadTemplate = (nextOperation = operation) => {
    setPayloadText(templateFor(nextOperation, query, lastPreviewFingerprint, initialPreviewSourceVersions));
    setConfirmed(false);
    setError(null);
    invalidateZeroCandidateConfirmationAttempt();
  };

  const runQuery = async () => {
    if (!caseNo.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const value = toMatchingCoordinationQueryView(await matchingCoordinationClient.query(caseNo.trim(), { expected_source_versions: null }));
      setQuery(value);
      setLastPreviewFingerprint(null);
      setLastPreviewOperation(null);
      invalidateZeroCandidateConfirmationAttempt();
      setPayloadText(templateFor(operation, value, null, initialPreviewSourceVersions));
    } catch (caught: unknown) {
      setError(displayMatchingError(caught, '媒合協調查詢失敗。'));
    } finally {
      setBusy(false);
    }
  };

  const runOperation = async () => {
    if (!caseNo.trim() || (isApply && (!confirmed || !hasRequiredPreview))) return;
    setBusy(true);
    setError(null);
    setPreview(null);
    setReceipt(null);
    try {
      const parsed: unknown = JSON.parse(payloadText);
      const attemptIdentity = `${operation}\n${payloadText}`;
      let options = {
        correlationId: operationIdentity(`matching-${operation}`),
        idempotencyKey: operationIdentity(`matching-${operation}-apply`),
      };
      if (operation === 'applyZeroCandidateConfirmation') {
        if (zeroCandidateConfirmationAttempt.current?.identity !== attemptIdentity) {
          zeroCandidateConfirmationAttempt.current = { identity: attemptIdentity, ...options };
        }
        options = zeroCandidateConfirmationAttempt.current;
      }
      let summary: PreviewSummary | null = null;
      let applyReceipt: MatchingApplyReceiptView | null = null;
      switch (operation) {
        case 'previewInitialCriteria': {
          const value: MatchingCriteriaSnapshot = await matchingCoordinationClient.previewInitialCriteria(caseNo.trim(), parsed as PreviewInitialCriteriaRequest, options);
          setInitialPreviewSourceVersions({ items: value.source_versions });
          summary = { title: '初始條件快照', status: '已完成試算', identity: value.snapshot_id, fingerprint: value.fingerprint, details: [`條件版本 ${value.criteria_version}`, `條件 ${value.criteria.length} 項`] };
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
        case 'previewZeroCandidateConfirmation': {
          const value = await matchingCoordinationClient.previewZeroCandidateConfirmation(caseNo.trim(), parsed as PreviewZeroCandidateConfirmationRequest, options);
          summary = {
            title: '確認目前確實無候選',
            status: 'Step 2 受阻',
            identity: value.package_id,
            fingerprint: value.fingerprint,
            details: [
              '目前沒有合法且願意承接的月嫂',
              '這只記錄目前的受阻事實，不代表異常已解除',
            ],
            technicalDetails: [`原始處置：blocked_no_candidate`, ...value.blockers],
          };
          break;
        }
        case 'previewRematch': summary = packageSummary('重新媒合方案', await matchingCoordinationClient.previewRematch(caseNo.trim(), parsed as PreviewRematchRequest, options)); break;
        case 'previewLeaveImpact': {
          const value: LeaveImpactPreviewResponse = await matchingCoordinationClient.previewLeaveImpact(caseNo.trim(), parsed as PreviewLeaveImpactRequest, options);
          summary = { title: '請假影響', status: resultStateLabel(value.result_state), identity: value.receipt_key, fingerprint: value.preview_fingerprint, details: [`需重新媒合：${value.rematch_required ? '是' : '否'}`], technicalDetails: [`原始處理方式：${value.resolution_type}`] };
          break;
        }
        case 'previewServiceDateRematch': {
          const value: ServiceDateRematchPreviewResponse = await matchingCoordinationClient.previewServiceDateRematch(caseNo.trim(), parsed as PreviewServiceDateRematchRequest, options);
          const identity = value.availability_confirmation?.intent_id ?? value.reassignment_reference?.queue_reference ?? '—';
          summary = { title: '服務日期變更', status: resultStateLabel(value.outcome_kind), identity, fingerprint: value.availability_confirmation?.source_fingerprint ?? value.reassignment_reference?.source_fingerprint ?? null, details: [value.outcome_kind === 'availability_confirmation' ? '可確認新日期檔期' : '已建立重新指派參考'] };
          break;
        }
        case 'applyInitialCriteria': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyInitialCriteria(caseNo.trim(), parsed as ApplyInitialCriteriaRequest, options)); break;
        case 'applyCriteriaDiff': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyCriteriaDiff(caseNo.trim(), parsed as ApplyCriteriaDiffRequest, options)); break;
        case 'applyCaregiverSelection': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyCaregiverSelection(caseNo.trim(), parsed as ApplyCaregiverSelectionRequest, options)); break;
        case 'applyCustomerDecision': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyCustomerDecision(caseNo.trim(), parsed as ApplyCustomerDecisionRequest, options)); break;
        case 'applyZeroCandidate': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyZeroCandidate(caseNo.trim(), parsed as ApplyZeroCandidateRequest, options)); break;
        case 'applyZeroCandidateConfirmation': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyZeroCandidateConfirmation(caseNo.trim(), parsed as ApplyZeroCandidateConfirmationRequest, options)); break;
        case 'applyRematch': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyRematch(caseNo.trim(), parsed as ApplyRematchRequest, options)); break;
        case 'applyLeaveImpact': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyLeaveImpact(caseNo.trim(), parsed as ApplyLeaveImpactRequest, options)); break;
        case 'applyServiceDateRematch': applyReceipt = toMatchingApplyReceiptView(await matchingCoordinationClient.applyServiceDateRematch(caseNo.trim(), parsed as ApplyServiceDateRematchRequest, options)); break;
      }
      if (summary) {
        setPreview(summary);
        setLastPreviewFingerprint(summary.fingerprint);
        setLastPreviewOperation(operation);
      }
      if (applyReceipt) {
        setReceipt(applyReceipt);
        setConfirmed(false);
        invalidateZeroCandidateConfirmationAttempt();
        await runQuery();
      }
    } catch (caught: unknown) {
      if (operation === 'applyZeroCandidateConfirmation' && isOutcomeUnknown(caught)) {
        setOutcomeUnknown(true);
        setError('提交結果目前無法確認。請保留相同內容並安全重試；系統會確認原操作結果，不會重複提交。');
      } else {
        invalidateZeroCandidateConfirmationAttempt();
        setError(displayMatchingError(caught, `${operationLabel}執行失敗。`));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="matching-coordination-workbench" data-surface-id="orders.matching.m3-coordination">
      <header className="matching-coordination-header">
        <div><h2>{embeddedInOrderWorkflow ? '先核對本案媒合條件' : '建立媒合條件與確認決定'}</h2><p>{embeddedInOrderWorkflow ? '先依訂單、服務日期與篩選規則核對；確認後再到下一步查詢可聯繫的月嫂。' : '依目前案件資料試算；確認提交前會再次核對資料版本。'}</p></div>
      </header>
      <div className="matching-coordination-query-row">
        {embeddedInOrderWorkflow ? <p className="matching-coordination-case-context">案件 {caseNo}</p> : <label htmlFor="matching-case-no">案件編號<input id="matching-case-no" value={caseNo} onChange={(event) => { setCaseNo(event.target.value); setQuery(null); setInitialPreviewSourceVersions(null); invalidateZeroCandidateConfirmationAttempt(); }} /></label>}
        <button type="button" disabled={!caseNo.trim() || busy} onClick={() => void runQuery()}>{busy ? '處理中…' : embeddedInOrderWorkflow ? '重新核對案件資料' : '查詢媒合資料'}</button>
      </div>
      {query && <><div className="matching-coordination-facts"><div><span>已讀取的條件版本</span><strong>第 {query.snapshot.criteria_version} 版</strong></div><div><span>媒合方案</span><strong>{query.matchingPackage ? '已建立' : '尚未建立'}</strong></div><div><span>來源版本</span><strong>{query.expectedSourceVersionsMatch ? '一致，可繼續' : '已變更，請重新核對'}</strong></div><div><span>候選人</span><strong>{query.candidates.length}</strong></div><div><span>拒絕歷史</span><strong>{query.refusalHistory.length}</strong></div></div>{!embeddedInOrderWorkflow && <details><summary>技術詳情與資料來源</summary><div>條件快照：{query.snapshot.snapshot_id}</div><div>媒合方案：{query.matchingPackage?.package_id ?? '尚未建立'}</div></details>}{!embeddedInOrderWorkflow && query.candidates.length > 0 && <div className="matching-coordination-table"><table><thead><tr><th>服務人員</th><th>資格</th><th>意願</th><th>拒絕原因</th></tr></thead><tbody>{query.candidates.map((candidate) => <tr key={candidate.candidate_id}><td>{candidate.staff_name}</td><td>{eligibilityLabel(candidate.eligibility)}</td><td>{willingnessLabel(candidate.willingness)}</td><td>{candidate.rejection_reasons.join('、') || '無'}</td></tr>)}</tbody></table></div>}</>}
      {embeddedInOrderWorkflow ? <div className="matching-coordination-business-panel">
        <div><strong>本步要確認什麼？</strong><p>服務日期、服務區域、每日時段、承接天數與料理需求是否可作為候選篩選條件。檔期衝突仍會由下一步的正式 gate 判定。</p></div>
        <button type="button" className="matching-coordination-primary" disabled={!caseNo.trim() || busy} onClick={() => { setOperation('previewInitialCriteria'); loadTemplate('previewInitialCriteria'); void runOperation(); }}>{busy ? '處理中…' : '核對媒合條件'}</button>
        {preview?.title === '初始條件快照' && <div className="matching-coordination-next-step" role="status"><strong>條件已核對</strong><span>{preview.details.join('｜')}</span><span>下一步：在下方「查詢合格月嫂清單」取得符合條件的候選人。</span></div>}
        <details className="matching-coordination-exception"><summary>條件變更、無候選或月嫂請假的處理</summary><p>發生例外時，先在既有媒合步驟更新案件條件或候選資料，再重新核對；不在此直接變更正式指派或契約。</p></details>
      </div> : <div className="matching-coordination-action-panel">
        <label htmlFor="matching-operation">目前要處理的業務<select id="matching-operation" value={operation} onChange={(event) => { const next = event.target.value as Operation; setOperation(next); setPayloadText(templateFor(next, query, lastPreviewFingerprint, initialPreviewSourceVersions)); setConfirmed(false); invalidateZeroCandidateConfirmationAttempt(); }}>{OPERATION_GROUPS.map(([groupLabel, operations]) => <optgroup key={groupLabel} label={groupLabel}>{operations.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</optgroup>)}</select></label>
        <p className="matching-coordination-flow-note">先完成試算，再確認提交；系統會依本次查詢重建欄位。</p>
        <details>
          <summary>技術操作欄位</summary>
          <button type="button" className="matching-coordination-secondary" onClick={() => loadTemplate()}>依目前查詢重建欄位</button>
          <label className="matching-coordination-payload" htmlFor="matching-payload">系統交換欄位<textarea id="matching-payload" rows={12} spellCheck={false} value={payloadText} onChange={(event) => { setPayloadText(event.target.value); setConfirmed(false); invalidateZeroCandidateConfirmationAttempt(); }} /></label>
        </details>
        {isApply && <label className="matching-coordination-confirm"><input type="checkbox" checked={confirmed} disabled={!hasRequiredPreview} onChange={(event) => setConfirmed(event.target.checked)} />我已核對試算結果、來源版本與即將提交的決定</label>}
        {isApply && !hasRequiredPreview && <p className="matching-coordination-flow-note" role="status">請先完成「{REQUIRED_PREVIEW[operation] ? OPERATIONS.find(([id]) => id === REQUIRED_PREVIEW[operation])?.[1] : '對應試算'}」。</p>}
        <button type="button" className="matching-coordination-primary" disabled={!caseNo.trim() || busy || (isApply && (!confirmed || !hasRequiredPreview))} onClick={() => void runOperation()}>{busy ? '處理中…' : outcomeUnknown ? '安全重試原操作' : isApply ? '確認提交此業務決定' : '執行試算'}</button>
      </div>}
      {!embeddedInOrderWorkflow && preview && <div className="matching-coordination-preview" role="status"><h3>{preview.title}</h3><p>{preview.status}</p><ul>{preview.details.map((detail, index) => <li key={`${detail}-${index}`}>{detail}</li>)}</ul><details><summary>技術詳情與資料來源</summary><p>identity：{preview.identity}</p>{preview.fingerprint && <p>fingerprint：{preview.fingerprint}</p>}{preview.technicalDetails?.map((detail, index) => <p key={`${detail}-${index}`}>{detail}</p>)}</details></div>}
      {receipt && <div className="matching-coordination-success" role="status"><h3>媒合決定已完成並回讀</h3><p>{resultStateLabel(receipt.resultState)}</p>{receipt.commandName === 'ApplyZeroCandidateConfirmation' && <><p>目前仍停在步驟 2，沒有合法候選</p><p>本次只完成受阻事實紀錄，不代表異常已解除。</p></>}<details><summary>技術詳情與資料來源</summary><p>{receipt.commandName}｜{receipt.resultState}</p><p>receipt：{receipt.receiptId}</p></details></div>}
      {error && <div className="matching-coordination-error" role="alert">{error}</div>}
    </section>
  );
};

export default MatchingCoordinationWorkbench;
