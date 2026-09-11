/**
 * File: ServiceBeforeReplacementActions.tsx
 * Description: 呈現服務前換人人工 Query／Preview／確認／Apply，以及同鍵結果對帳與代班轉介。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createServiceBeforeReplacementCommandIdentity,
  isServiceBeforeReplacementOutcomeUnknown,
  serviceBeforeReplacementClient,
  type ServiceBeforeReplacementApplyRequest,
  type ServiceBeforeReplacementApplyResult,
  type ServiceBeforeReplacementCommandIdentity,
  type ServiceBeforeReplacementPreview,
  type ServiceBeforeReplacementQuery,
  type ServiceBeforeReplacementScenario,
} from '../api/orders/service_before_replacement_client';

export interface ServiceBeforeReplacementActionsProps {
  caseNo: string;
  initialScenario?: ServiceBeforeReplacementScenario;
  onCommitted?: (result: ServiceBeforeReplacementApplyResult) => Promise<void> | void;
  onSubstitutionReferral?: (query: ServiceBeforeReplacementQuery) => Promise<void> | void;
}

type UiState =
  | { type: 'querying' }
  | { type: 'ready' }
  | { type: 'previewing' }
  | { type: 'preview_ready'; preview: ServiceBeforeReplacementPreview; confirmed: boolean }
  | { type: 'applying' }
  | { type: 'outcome_unknown'; request: ServiceBeforeReplacementApplyRequest; identity: ServiceBeforeReplacementCommandIdentity; message: string }
  | { type: 'observed'; result: ServiceBeforeReplacementApplyResult }
  | { type: 'error'; message: string };

const scenarioLabels: Record<ServiceBeforeReplacementScenario, string> = {
  'R-01': '候選月嫂尚未定案',
  'R-02': '客戶已接受推薦月嫂',
  'R-03': '已保留檔期或簽署契約',
  'R-04': '已安排月嫂，尚未開始服務',
  'R-07': '重新媒合後仍沒有合適人選',
};

const stepLabels = {
  step_2: '重新挑選候選月嫂',
  step_3: '從已確認的候選月嫂繼續媒合',
  step_4: '依已確認的推薦結果繼續安排',
} as const;

function canonicalEvidence(value: string): string[] {
  return [...new Set(value.split('\n').map((item) => item.trim()).filter(Boolean))].sort();
}

function blockerLabel(code: string): string {
  const labels: Record<string, string> = {
    actual_service_exists: '已開始服務，請改由請假代班處理。',
    replacement_actual_service_exists: '已開始服務，請改由請假代班處理。',
    actual_service_proof_unavailable: '尚無法確認已服務日期，請先核對服務紀錄。',
    replacement_successor_exists: '此筆更換已完成，請重新查詢案件。',
    candidate_pool_reuse_unbound: '候選月嫂資料已變更，請重新確認人選。',
    successor_round_stale: '媒合進度已更新，請重新查詢。',
  };
  return labels[code] ?? '更換所需資料尚未完整或已變更，請核對案件後重新查詢。';
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function buildApplyRequest(preview: ServiceBeforeReplacementPreview): ServiceBeforeReplacementApplyRequest | null {
  if (preview.outcome !== 'ready'
    || preview.prior_generation_identity === null
    || preview.prior_event_identity === null
    || preview.prior_aggregate_identity === null) return null;
  return {
    scenario: preview.scenario,
    reason: preview.reason,
    evidence: preview.evidence,
    expected_generation_version: preview.expected_generation_version,
    expected_event_version: preview.expected_event_version,
    expected_aggregate_version: preview.expected_aggregate_version,
    prior_generation_identity: preview.prior_generation_identity,
    prior_event_identity: preview.prior_event_identity,
    prior_aggregate_identity: preview.prior_aggregate_identity,
    preview_fingerprint: preview.preview_fingerprint,
  };
}

export function ServiceBeforeReplacementActions({
  caseNo,
  initialScenario,
  onCommitted,
  onSubstitutionReferral,
}: ServiceBeforeReplacementActionsProps) {
  const [scenario, setScenario] = useState<ServiceBeforeReplacementScenario | ''>(initialScenario ?? '');
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState<ServiceBeforeReplacementQuery | null>(null);
  const [reason, setReason] = useState('');
  const [evidenceText, setEvidenceText] = useState('');
  const [uiState, setUiState] = useState<UiState>({ type: 'querying' });
  const operationGeneration = useRef(0);
  const expandedCaseNo = useRef<string | null>(null);
  const queryController = useRef<AbortController | null>(null);
  const previewController = useRef<AbortController | null>(null);
  const applyController = useRef<AbortController | null>(null);

  const busy = ['querying', 'previewing', 'applying'].includes(uiState.type);

  const runQuery = useCallback(async (selectedScenario: ServiceBeforeReplacementScenario) => {
    queryController.current?.abort();
    previewController.current?.abort();
    applyController.current?.abort();
    const controller = new AbortController();
    queryController.current = controller;
    const generation = operationGeneration.current + 1;
    operationGeneration.current = generation;
    const requestedCaseNo = caseNo;
    setUiState({ type: 'querying' });
    setQuery(null);
    try {
      const next = await serviceBeforeReplacementClient.query(requestedCaseNo, selectedScenario, controller.signal);
      if (operationGeneration.current !== generation || requestedCaseNo !== caseNo) return;
      setQuery(next);
      setUiState({ type: 'ready' });
    } catch (error) {
      if (operationGeneration.current !== generation || requestedCaseNo !== caseNo) return;
      setUiState({ type: 'error', message: errorMessage(error, '無法取得更換條件。') });
    }
  }, [caseNo]);

  useEffect(() => {
    setScenario(initialScenario ?? '');
    expandedCaseNo.current = null;
    setExpanded(false);
  }, [caseNo, initialScenario]);

  useEffect(() => {
    setReason('');
    setEvidenceText('');
    if (!expanded || expandedCaseNo.current !== caseNo || scenario === '') {
      setQuery(null);
      setUiState({ type: 'ready' });
      return undefined;
    }
    void runQuery(scenario);
    return () => {
      operationGeneration.current += 1;
      queryController.current?.abort();
      previewController.current?.abort();
      applyController.current?.abort();
    };
  }, [caseNo, expanded, runQuery, scenario]);

  const preview = async () => {
    const trimmedReason = reason.trim();
    const evidence = canonicalEvidence(evidenceText);
    if (!trimmedReason || evidence.length === 0) {
      setUiState({ type: 'error', message: '請填寫換人原因，並至少提供一筆證據。' });
      return;
    }
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    const generation = operationGeneration.current + 1;
    operationGeneration.current = generation;
    const requestedCaseNo = caseNo;
    if (scenario === '') return;
    const requestedScenario = scenario;
    setUiState({ type: 'previewing' });
    try {
      const next = await serviceBeforeReplacementClient.preview(requestedCaseNo, {
        scenario: requestedScenario,
        reason: trimmedReason,
        evidence,
      }, controller.signal);
      if (operationGeneration.current !== generation || requestedCaseNo !== caseNo || requestedScenario !== scenario) return;
      setQuery(next);
      setUiState({ type: 'preview_ready', preview: next, confirmed: false });
    } catch (error) {
      if (operationGeneration.current !== generation || requestedCaseNo !== caseNo || requestedScenario !== scenario) return;
      setUiState({ type: 'error', message: errorMessage(error, '服務前換人預覽失敗。') });
    }
  };

  const apply = async (
    request: ServiceBeforeReplacementApplyRequest,
    identity: ServiceBeforeReplacementCommandIdentity,
  ) => {
    applyController.current?.abort();
    const controller = new AbortController();
    applyController.current = controller;
    const generation = operationGeneration.current + 1;
    operationGeneration.current = generation;
    const requestedCaseNo = caseNo;
    const requestedScenario = request.scenario;
    setUiState({ type: 'applying' });
    let result: ServiceBeforeReplacementApplyResult;
    try {
      result = await serviceBeforeReplacementClient.apply(requestedCaseNo, request, identity, controller.signal);
      if (operationGeneration.current !== generation || requestedCaseNo !== caseNo || requestedScenario !== scenario) return;
    } catch (error) {
      if (operationGeneration.current !== generation || requestedCaseNo !== caseNo || requestedScenario !== scenario) return;
      if (isServiceBeforeReplacementOutcomeUnknown(error)) {
        setUiState({
          type: 'outcome_unknown',
          request,
          identity,
          message: '提交結果尚未確認。系統會沿用原操作安全地確認結果，不會重複建立換人。',
        });
        return;
      }
      setUiState({ type: 'error', message: errorMessage(error, '服務前換人提交失敗。') });
      return;
    }
    setUiState({ type: 'observed', result });
    try {
      await onCommitted?.(result);
    } catch {
      // Apply response already contains the canonical post-commit readback.
    }
  };

  const startApply = async () => {
    if (uiState.type !== 'preview_ready' || !uiState.confirmed) return;
    const request = buildApplyRequest(uiState.preview);
    if (request === null) {
      setUiState({ type: 'error', message: '更換資料尚未完整，請重新查詢後再預覽。' });
      return;
    }
    await apply(request, createServiceBeforeReplacementCommandIdentity());
  };

  return (
    <section aria-label="服務前換人操作" style={{ display: 'grid', gap: '12px' }}>
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => {
          const next = !value;
          expandedCaseNo.current = next ? caseNo : null;
          return next;
        })}
      >
        {expanded ? '收合換人' : '換人'}
      </button>

      {expanded && <div style={{ display: 'grid', gap: '16px', maxWidth: '760px' }}>
        <header>
          <h3 style={{ margin: 0 }}>服務前更換月嫂</h3>
          <p style={{ margin: '4px 0 0' }}>案件 {caseNo}。先確認更換影響；原月嫂的歷史紀錄會保留。</p>
        </header>

      <label style={{ display: 'grid', gap: '4px', maxWidth: '420px' }}>
        目前進度
        <select
          value={scenario}
          disabled={busy || uiState.type === 'outcome_unknown'}
          onChange={(event) => setScenario(event.target.value as ServiceBeforeReplacementScenario | '')}
        >
          <option value="">請選擇案件目前進度</option>
          {Object.entries(scenarioLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>

      {scenario === '' && <div role="status">請依案件實際進度選擇，接著查看可辦理的更換方式。</div>}

      {query && (
        <section aria-label="更換條件" style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px' }}>
          <strong>{query.outcome === 'ready'
            ? '可以辦理更換'
            : query.blockers.includes('replacement_successor_exists')
              ? '已辦理更換，請勿重複提交'
              : query.outcome === 'blocked'
                ? '目前不可換人'
                : '已有實際服務，必須改走請假代班'}</strong>
          <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '4px 12px' }}>
            <dt>更換後下一步</dt><dd>{stepLabels[query.resume_step]}</dd>
            <dt>已服務天數</dt><dd>{query.actual_service_day_count} 日</dd>
          </dl>
          {query.actual_service_dates.length > 0 && <p>已服務日期：{query.actual_service_dates.join('、')}</p>}
          {query.blockers.length > 0 && <ul>{[...new Set(query.blockers.map(blockerLabel))].map((message) => <li key={message}>{message}</li>)}</ul>}
          {query.outcome === 'substitution_referral' && (
            onSubstitutionReferral
              ? <button type="button" onClick={() => void onSubstitutionReferral(query)}>前往請假代班</button>
              : <a href="#scheduling">前往請假代班</a>
          )}
        </section>
      )}

      {query?.outcome === 'ready' && !['observed', 'outcome_unknown'].includes(uiState.type) && (
        <section aria-label="服務前換人操作資料" style={{ display: 'grid', gap: '8px' }}>
          <label style={{ display: 'grid', gap: '4px' }}>
            換人原因
            <textarea value={reason} maxLength={500} disabled={busy} onChange={(event) => {
              setReason(event.target.value);
              if (uiState.type === 'preview_ready') setUiState({ type: 'ready' });
            }} />
          </label>
          <label style={{ display: 'grid', gap: '4px' }}>
            聯繫紀錄或更換依據
            <span style={{ fontSize: '0.875rem' }}>請填寫實際聯繫日期、回覆內容或相關紀錄編號；多筆紀錄請分行填寫。</span>
            <textarea aria-label="聯繫紀錄或更換依據" value={evidenceText} disabled={busy} onChange={(event) => {
              setEvidenceText(event.target.value);
              if (uiState.type === 'preview_ready') setUiState({ type: 'ready' });
            }} />
          </label>
          <button type="button" disabled={busy || !reason.trim() || canonicalEvidence(evidenceText).length === 0} onClick={() => void preview()}>
            預覽換人影響
          </button>
        </section>
      )}

      {uiState.type === 'preview_ready' && (
        <section aria-label="服務前換人預覽" style={{ border: '1px solid #f2a27b', borderRadius: '10px', padding: '12px' }}>
          <strong>{uiState.preview.outcome === 'ready' ? '預覽完成，尚未寫入' : '此預覽不可套用'}</strong>
          <p>更換後下一步：{stepLabels[uiState.preview.resume_step]}</p>
          <p>確認後將依目前進度更新月嫂安排，原有紀錄保留供查閱。</p>
          {uiState.preview.blockers.length > 0 && <ul>{[...new Set(uiState.preview.blockers.map(blockerLabel))].map((message) => <li key={message}>{message}</li>)}</ul>}
          {uiState.preview.outcome === 'ready' && (
            <>
              <label>
                <input
                  type="checkbox"
                  checked={uiState.confirmed}
                  onChange={(event) => setUiState({ ...uiState, confirmed: event.target.checked })}
                />
                我已確認更換原因、聯繫紀錄及影響
              </label>
              <button type="button" disabled={!uiState.confirmed} onClick={() => void startApply()}>確認更換</button>
            </>
          )}
        </section>
      )}

      {(uiState.type === 'querying' || uiState.type === 'previewing' || uiState.type === 'applying') && <div role="status">正在處理服務前換人資料…</div>}
      {uiState.type === 'error' && (
        <div role="alert">
          <div>{uiState.message}</div>
          <button type="button" disabled={scenario === ''} onClick={() => scenario !== '' && void runQuery(scenario)}>重新查詢</button>
        </div>
      )}
      {uiState.type === 'outcome_unknown' && (
        <div role="alert">
          <div>{uiState.message}</div>
          <button type="button" onClick={() => void apply(uiState.request, uiState.identity)}>重新確認原操作結果</button>
        </div>
      )}
      {uiState.type === 'observed' && (
        <div role="status">
          <strong>已完成更換（{uiState.result.status === 'replayed' ? '已確認既有結果' : '已套用'}）</strong>
          <div>案件已更新。請依下方下一步繼續處理。</div>
          <div>若本案另有待處理異常，請回到異常處理頁確認。</div>
          <div>下一步：{stepLabels[uiState.result.readback.resume_step]}</div>
          <div>可用候選月嫂：{uiState.result.readback.candidate_count}</div>
          {uiState.result.readback.zero_candidate_disposition === 'blocked_no_candidate' ? (
            <div role="status">
              <strong>目前沒有可用候選月嫂</strong>
              <div>更換已登記，仍需重新尋找合適月嫂；不會自動恢復原月嫂。</div>
            </div>
          ) : null}
        </div>
      )}
      </div>}
    </section>
  );
}
