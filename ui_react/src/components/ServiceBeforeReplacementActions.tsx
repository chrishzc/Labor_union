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
  'R-01': 'R-01 候選月嫂尚未定案',
  'R-02': 'R-02 已接受媒合方案',
  'R-03': 'R-03 已鎖檔／承諾／簽回',
  'R-04': 'R-04 已指派但尚未服務',
  'R-07': 'R-07 新一輪暫無候選人',
};

const stepLabels = {
  step_2: '步驟 2：重新建立候選池',
  step_3: '步驟 3：沿用已驗證候選池',
  step_4: '步驟 4：沿用已驗證接受結果',
} as const;

function canonicalEvidence(value: string): string[] {
  return [...new Set(value.split('\n').map((item) => item.trim()).filter(Boolean))].sort();
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
  const [query, setQuery] = useState<ServiceBeforeReplacementQuery | null>(null);
  const [reason, setReason] = useState('');
  const [evidenceText, setEvidenceText] = useState('');
  const [uiState, setUiState] = useState<UiState>({ type: 'querying' });
  const operationGeneration = useRef(0);
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
      setUiState({ type: 'error', message: errorMessage(error, '無法取得服務前換人根事實。') });
    }
  }, [caseNo]);

  useEffect(() => {
    setScenario(initialScenario ?? '');
  }, [caseNo, initialScenario]);

  useEffect(() => {
    setReason('');
    setEvidenceText('');
    if (scenario === '') {
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
  }, [runQuery, scenario]);

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
          message: '提交結果尚未確認。系統不會建立新命令，只能用原內容與原 Idempotency-Key 對帳。',
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
      setUiState({ type: 'error', message: '後端預覽尚未提供可執行的完整版本與根事實。' });
      return;
    }
    await apply(request, createServiceBeforeReplacementCommandIdentity());
  };

  return (
    <section aria-label="服務前換人人工修復" style={{ display: 'grid', gap: '12px' }}>
      <header>
        <h3 style={{ margin: 0 }}>服務前換人人工修復</h3>
        <p style={{ margin: '4px 0 0' }}>案件 {caseNo}。修復只建立新版 successor，不會改寫舊月嫂歷史。</p>
      </header>

      <label style={{ display: 'grid', gap: '4px', maxWidth: '420px' }}>
        異常情境
        <select
          value={scenario}
          disabled={busy || uiState.type === 'outcome_unknown'}
          onChange={(event) => setScenario(event.target.value as ServiceBeforeReplacementScenario | '')}
        >
          <option value="">請選擇 RPRE 異常情境</option>
          {Object.entries(scenarioLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>

      {scenario === '' && <div role="status">請依異常事件的正式 binding 或實際案件狀況明確選擇情境；系統不會猜測 R-01。</div>}

      {query && (
        <section aria-label="服務前換人根事實" style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px' }}>
          <strong>{query.outcome === 'ready' ? '可以建立換人 successor' : query.outcome === 'blocked' ? '目前不可換人' : '已有實際服務，必須改走請假代班'}</strong>
          <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '4px 12px' }}>
            <dt>後端決定的續跑位置</dt><dd>{stepLabels[query.resume_step]}</dd>
            <dt>正式服務日</dt><dd>{query.actual_service_day_count} 日</dd>
            <dt>受影響根事實</dt><dd>{query.impacted_roots.length} 筆</dd>
            <dt>保留歷史</dt><dd>{query.retained_roots.length} 筆</dd>
          </dl>
          {query.actual_service_proof && (
            <div>正式服務 proof：{query.actual_service_proof.source_identity}，版本 {query.actual_service_proof.source_version}</div>
          )}
          {query.candidate_pool_reuse_proof && (
            <div>
              候選池 reuse proof：{query.candidate_pool_reuse_proof.pool_identity}／{query.candidate_pool_reuse_proof.round_identity}；
              coverage {query.candidate_pool_reuse_proof.coverage_version}、availability {query.candidate_pool_reuse_proof.availability_version}、willingness {query.candidate_pool_reuse_proof.willingness_version}；
              generation {query.candidate_pool_reuse_proof.generation_version}、event {query.candidate_pool_reuse_proof.event_version}；
              candidate {query.candidate_pool_reuse_proof.candidate_identity}；{query.candidate_pool_reuse_proof.fresh ? 'fresh' : 'not fresh'}；
              fingerprint {query.candidate_pool_reuse_proof.fingerprint}
            </div>
          )}
          <details>
            <summary>檢視 root identities</summary>
            <strong>受影響 roots</strong>
            <ul>{query.impacted_roots.map((root) => <li key={root.root_id}>{root.kind}｜{root.root_id}</li>)}</ul>
            <strong>保留 roots</strong>
            <ul>{query.retained_roots.map((root) => <li key={root.root_id}>{root.kind}｜{root.root_id}</li>)}</ul>
          </details>
          {query.actual_service_dates.length > 0 && <p>已服務日期：{query.actual_service_dates.join('、')}</p>}
          {query.blockers.length > 0 && <ul>{query.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>}
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
            證據（每行一筆）
            <textarea value={evidenceText} disabled={busy} onChange={(event) => {
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
          <p>後端續跑位置：{stepLabels[uiState.preview.resume_step]}</p>
          <p>將停用目前關聯 {uiState.preview.superseded_roots.length} 筆，建立 successor 根事實 {uiState.preview.created_roots.length} 筆。</p>
          <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '4px 12px' }}>
            <dt>Prior generation／event／aggregate</dt>
            <dd>{uiState.preview.prior_generation_identity ?? '—'}／{uiState.preview.prior_event_identity ?? '—'}／{uiState.preview.prior_aggregate_identity ?? '—'}</dd>
            <dt>Replacement generation／event</dt>
            <dd>{uiState.preview.replacement_generation_identity}／{uiState.preview.replacement_event_identity}</dd>
            <dt>Successor round</dt><dd>{uiState.preview.successor_round_identity}</dd>
            <dt>Generation version</dt><dd>expected {uiState.preview.expected_generation_version}／resulting {uiState.preview.resulting_generation_version}</dd>
            <dt>Event version</dt><dd>expected {uiState.preview.expected_event_version}／resulting {uiState.preview.resulting_event_version}</dd>
            <dt>Aggregate version</dt><dd>expected {uiState.preview.expected_aggregate_version}／resulting {uiState.preview.resulting_aggregate_version}</dd>
            <dt>Projection kind</dt><dd>{uiState.preview.projection_kind}</dd>
            <dt>Preview fingerprint</dt><dd>{uiState.preview.preview_fingerprint}</dd>
          </dl>
          {uiState.preview.actual_service_proof ? (
            <div>
              Actual-service proof：{uiState.preview.actual_service_proof.source_identity}，版本 {uiState.preview.actual_service_proof.source_version}；
              日期 {uiState.preview.actual_service_proof.service_dates.join('、') || '無'}；fingerprint {uiState.preview.actual_service_proof.fingerprint}
            </div>
          ) : <div>Actual-service proof：無</div>}
          {uiState.preview.candidate_pool_reuse_proof ? (
            <div>
              Candidate reuse proof：pool {uiState.preview.candidate_pool_reuse_proof.pool_identity}／round {uiState.preview.candidate_pool_reuse_proof.round_identity}／
              successor {uiState.preview.candidate_pool_reuse_proof.successor_round_identity}／candidate {uiState.preview.candidate_pool_reuse_proof.candidate_identity}；
              coverage {uiState.preview.candidate_pool_reuse_proof.coverage_version}／availability {uiState.preview.candidate_pool_reuse_proof.availability_version}／willingness {uiState.preview.candidate_pool_reuse_proof.willingness_version}／
              generation {uiState.preview.candidate_pool_reuse_proof.generation_version}／event {uiState.preview.candidate_pool_reuse_proof.event_version}；
              same-round {String(uiState.preview.candidate_pool_reuse_proof.same_round)}／coverage-valid {String(uiState.preview.candidate_pool_reuse_proof.coverage_valid)}／
              availability-valid {String(uiState.preview.candidate_pool_reuse_proof.availability_valid)}／willingness-valid {String(uiState.preview.candidate_pool_reuse_proof.willingness_valid)}／
              fresh {String(uiState.preview.candidate_pool_reuse_proof.fresh)}／accepted {String(uiState.preview.candidate_pool_reuse_proof.accepted_candidate)}；
              fingerprint {uiState.preview.candidate_pool_reuse_proof.fingerprint}
            </div>
          ) : <div>Candidate reuse proof：無</div>}
          {uiState.preview.successor_round ? (
            <div>
              Successor proof：{uiState.preview.successor_round.round_identity}／{uiState.preview.successor_round.generation_identity}／{uiState.preview.successor_round.event_identity}；
              generation {uiState.preview.successor_round.generation_version}／event {uiState.preview.successor_round.event_version}／candidates {uiState.preview.successor_round.candidate_count}／
              disposition {uiState.preview.successor_round.zero_candidate_disposition ?? '—'}；fingerprint {uiState.preview.successor_round.fingerprint}
            </div>
          ) : <div>Successor proof：無</div>}
          <details open>
            <summary>完整 Preview roots</summary>
            {([
              ['retained', uiState.preview.retained_roots],
              ['superseded', uiState.preview.superseded_roots],
              ['created', uiState.preview.created_roots],
            ] as const).map(([label, roots]) => (
              <div key={label}>
                <strong>{label} roots</strong>
                <ul>{roots.map((root) => <li key={root.root_id}>{root.kind}｜{root.root_id}｜current {String(root.current)}｜caregiver-bound {String(root.caregiver_bound)}</li>)}</ul>
              </div>
            ))}
          </details>
          {uiState.preview.blockers.length > 0 && <ul>{uiState.preview.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>}
          {uiState.preview.outcome === 'ready' && (
            <>
              <label>
                <input
                  type="checkbox"
                  checked={uiState.confirmed}
                  onChange={(event) => setUiState({ ...uiState, confirmed: event.target.checked })}
                />
                我已核對案件、情境、原因、證據與影響範圍
              </label>
              <button type="button" disabled={!uiState.confirmed} onClick={() => void startApply()}>確認建立換人 successor</button>
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
          <button type="button" onClick={() => void apply(uiState.request, uiState.identity)}>以原命令對帳 receipt／readback</button>
        </div>
      )}
      {uiState.type === 'observed' && (
        <div role="status">
          <strong>換人 successor 已完成 owner readback（{uiState.result.status === 'replayed' ? '既有結果已對帳' : '已套用'}）</strong>
          <div>本次 Apply 已由後端完成 post-commit owner readback；若要處理另一種情境，請重新選擇情境後查詢。</div>
          <div>Active anomaly：Apply readback 未提供 occurrence active 欄位，UI 不會以 receipt 或 blocker 假推定。</div>
          <div>Generation／event／aggregate：{uiState.result.readback.generation_version}／{uiState.result.readback.event_version}／{uiState.result.readback.aggregate_version}</div>
          <div>後端完成位置：{stepLabels[uiState.result.readback.resume_step]}</div>
          <div>Successor 候選數：{uiState.result.readback.candidate_count}</div>
          {uiState.result.readback.zero_candidate_disposition === 'blocked_no_candidate' ? (
            <div role="status">
              <strong>目前仍停在 Step 2：沒有可用候選（blocked_no_candidate）</strong>
              <div>這次只完成換人 lineage 記錄，不代表異常已解除，也不會復活舊月嫂。</div>
            </div>
          ) : null}
          <div>Generation identity：{uiState.result.readback.generation_identity}</div>
          <div>Event identity：{uiState.result.readback.event_identity}</div>
          <div>Successor round：{uiState.result.readback.successor_round_identity}</div>
          <div>Outbox：{uiState.result.readback.outbox_identity}</div>
          <div>Readback complete：{uiState.result.readback.complete ? 'true' : 'false'}</div>
          <div>Matching package lineage／event：{uiState.result.readback.matching_package_lineage_id ?? '—'}／{uiState.result.readback.matching_event_id ?? '—'}</div>
          <div>Receipt：{uiState.result.receipt.receipt_identity}</div>
          <div>Command fingerprint：{uiState.result.receipt.command_fingerprint}</div>
          <div>Preview fingerprint：{uiState.result.receipt.preview_fingerprint}</div>
          <details>
            <summary>完整 receipt／readback roots 與 digests</summary>
            {(['retained', 'superseded', 'created'] as const).map((kind, index) => (
              <div key={kind}>
                <strong>{kind}</strong>
                <div>digest：{uiState.result.readback.root_set_digests[index]}</div>
                <div>count：{uiState.result.readback.root_set_counts[index]}</div>
                <ul>{uiState.result.readback[`${kind}_root_ids`].map((identity) => <li key={identity}>{identity}</li>)}</ul>
              </div>
            ))}
          </details>
        </div>
      )}
    </section>
  );
}
