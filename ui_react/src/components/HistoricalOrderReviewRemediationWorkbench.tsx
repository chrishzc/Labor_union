/**
 * File: HistoricalOrderReviewRemediationWorkbench.tsx
 * Description: 歷史訂單 review 的單列更正工作台；先 Query、再 Preview、最後明確 Confirm／Apply。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  historicalReviewRemediationClient,
  HistoricalReviewRemediationWorkbookSnapshot,
  type HistoricalReviewRemediationApplyOptions,
  type HistoricalReviewRemediationClient,
} from '../api/orders/historical_review_remediation/client';
import { mapHistoricalReviewRemediationApplyError, mapHistoricalReviewRemediationError } from '../api/orders/historical_review_remediation/errors';
import type {
  HistoricalReviewApply,
  HistoricalReviewContext,
  HistoricalReviewIssue,
  HistoricalReviewPreview,
} from '../api/orders/historical_review_remediation/schemas';

export interface HistoricalOrderReviewRemediationWorkbenchProps {
  reviewIdentity: string;
  client?: HistoricalReviewRemediationClient;
  onResolved?: (result: HistoricalReviewApply) => void;
}

function commandId(prefix: string): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return `${prefix}-${globalThis.crypto.randomUUID()}`;
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function errorMessage(error: unknown): string {
  const typed = mapHistoricalReviewRemediationError(error);
  if (typed.status === 401) return '登入狀態已失效，請重新登入後再操作。';
  if (typed.status === 403) return '目前帳號沒有處理歷史訂單欄位衝突的權限。';
  if (typed.status === 404) return '找不到這筆歷史訂單待確認案件，請返回清單重新查詢。';
  if (typed.status === 409) return '案件資料已變更，請重新查詢並再次預覽。';
  if (typed.status === 422) return '更正資料未通過檢核，請依欄位衝突修正後再預覽。';
  if (typed.retryable) return '結果尚未確認；請先重新查詢，再以相同操作安全重試。';
  return '歷史訂單欄位衝突目前無法完成，請稍後再試。';
}

function dispositionLabel(disposition: HistoricalReviewApply['disposition'] | HistoricalReviewPreview['outcome']): string {
  return disposition === 'corrected_source_adopted'
    ? '更正資料可採用'
    : '仍有欄位需要後續確認';
}

function renderIssues(issues: HistoricalReviewIssue[], title: string): React.ReactNode {
  return <div aria-label={title}>
    <h4>{title}</h4>
    {issues.length === 0 ? <p>沒有剩餘欄位衝突。</p> : <ul>
      {issues.map((issue) => <li key={`${issue.issue_code}:${issue.field_path}`}>
        <strong>{issue.field_label}</strong>
        <div>來源值：{issue.masked_source_value || '（空白）'}｜目前值：{issue.masked_current_value || '（空白）'}</div>
        <div>規則：{issue.rule}</div>
        <div>可採用值：{issue.allowed_values.length ? issue.allowed_values.join('、') : '依規則判定'}</div>
        <div>流程阻擋：{issue.process_blocker}</div>
        <details><summary>技術詳情</summary><p>欄位：{issue.field_path}｜問題類型：{issue.issue_code}</p></details>
      </li>)}
    </ul>}
  </div>;
}

export const HistoricalOrderReviewRemediationWorkbench: React.FC<HistoricalOrderReviewRemediationWorkbenchProps> = ({
  reviewIdentity,
  client = historicalReviewRemediationClient,
  onResolved,
}) => {
  const [context, setContext] = useState<HistoricalReviewContext | null>(null);
  const [preview, setPreview] = useState<HistoricalReviewPreview | null>(null);
  const [snapshot, setSnapshot] = useState<HistoricalReviewRemediationWorkbookSnapshot | null>(null);
  const [fileName, setFileName] = useState('');
  const [reason, setReason] = useState('');
  const [evidence, setEvidence] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [applyResult, setApplyResult] = useState<HistoricalReviewApply | null>(null);
  const [unknownOutcome, setUnknownOutcome] = useState(false);
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const requestSequence = useRef(0);
  const applyCommand = useRef<{ fingerprint: string; idempotencyKey: string; correlationId: string } | null>(null);

  const readOwner = useCallback(async (): Promise<HistoricalReviewContext | null> => {
    const sequence = ++requestSequence.current;
    setLoading(true);
    setQueryError(null);
    try {
      const next = await client.query(reviewIdentity);
      if (sequence !== requestSequence.current) return null;
      setContext(next);
      return next;
    } catch (caught) {
      if (sequence === requestSequence.current) setQueryError(errorMessage(caught));
      return null;
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [client, reviewIdentity]);

  useEffect(() => {
    void readOwner();
    return () => { requestSequence.current += 1; };
  }, [readOwner]);

  const inputKey = useMemo(() => JSON.stringify({
    reviewIdentity,
    fileDigest: snapshot?.sha256 ?? null,
    reason: reason.trim(),
    evidence: evidence.trim(),
    reviewVersion: context?.review_version ?? null,
    remediationVersion: context?.remediation_version ?? null,
  }), [context?.remediation_version, context?.review_version, evidence, reason, reviewIdentity, snapshot?.sha256]);
  const previewCurrent = preview !== null && previewKey === inputKey;
  const canPreview = !!context && !!snapshot && !!reason.trim() && !!evidence.trim() && !busy;

  const invalidate = (change: () => void) => {
    change();
    setPreview(null);
    setPreviewKey(null);
    setConfirmed(false);
    setApplyResult(null);
    setUnknownOutcome(false);
    setNotice(null);
    applyCommand.current = null;
  };

  const selectWorkbook = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    invalidate(() => { setSnapshot(null); setFileName(file?.name ?? ''); });
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const next = await HistoricalReviewRemediationWorkbookSnapshot.fromFile(file);
      setSnapshot(next);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const previewAction = async () => {
    if (!canPreview || !context || !snapshot) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    setPreview(null);
    setPreviewKey(null);
    setConfirmed(false);
    try {
      const next = await client.preview(snapshot, {
        prior_review_identity: context.review_identity,
        expected_review_version: context.review_version,
        expected_remediation_version: context.remediation_version,
        reason: reason.trim(),
        evidence: evidence.trim(),
      });
      setPreview(next);
      setPreviewKey(inputKey);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const applyAction = async () => {
    if (!previewCurrent || !preview || !snapshot || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    if (applyCommand.current?.fingerprint !== preview.preview_fingerprint) {
      applyCommand.current = {
        fingerprint: preview.preview_fingerprint,
        idempotencyKey: commandId('historical-review-remediation'),
        correlationId: commandId('historical-review-command'),
      };
    }
    const options: HistoricalReviewRemediationApplyOptions = {
      idempotencyKey: applyCommand.current.idempotencyKey,
      correlationId: applyCommand.current.correlationId,
    };
    try {
      const result = await client.apply(snapshot, {
        prior_review_identity: preview.prior_review_identity,
        expected_review_version: preview.review_version,
        expected_remediation_version: preview.remediation_version,
        preview_fingerprint: preview.preview_fingerprint,
        reason: reason.trim(),
        evidence: evidence.trim(),
      }, options);
      setApplyResult(result);
      setUnknownOutcome(false);
      setPreview(null);
      setPreviewKey(null);
      setConfirmed(false);
      applyCommand.current = null;
      const fresh = await readOwner();
      if (fresh?.prior_alert_active === true) {
        setNotice('更正已提交；異常投影仍在重新檢核，原警示會保留到 readback 確認解除。');
      } else {
        setApplyResult({ ...result, prior_alert_active: false, readback: { ...result.readback, prior_alert_active: false } });
        onResolved?.(result);
        setNotice(result.replayed ? '已讀回原 remediation receipt；原警示已解除。' : '更正已套用並由 owner readback 確認原警示解除。');
      }
    } catch (caught) {
      setUnknownOutcome(true);
      const fresh = await readOwner();
      if (fresh?.prior_alert_active === false) setNotice('結果已由 owner readback 確認，原警示已解除。');
      else setError(errorMessage(mapHistoricalReviewRemediationApplyError(caught)));
    } finally {
      setBusy(false);
    }
  };

  const reconcileProjection = async () => {
    if (!applyResult || busy) return;
    setBusy(true);
    setError(null);
    const fresh = await readOwner();
    if (fresh?.prior_alert_active === false) {
      const resolved = {
        ...applyResult,
        prior_alert_active: false,
        readback: { ...applyResult.readback, prior_alert_active: false, remediation_version: fresh.remediation_version },
      };
      setApplyResult(resolved);
      setNotice('異常重新檢核完成，原警示已解除。');
      onResolved?.(resolved);
    } else {
      setNotice('異常仍在重新檢核；根事實未確認解除前會繼續保留警示。');
    }
    setBusy(false);
  };

  if (loading && !context) return <section aria-label="歷史訂單 review 更正"><p>正在讀取歷史訂單 review 根事實…</p></section>;
  if (queryError && !context) return <section aria-label="歷史訂單 review 更正"><p role="alert">{queryError}</p><button type="button" onClick={() => void readOwner()}>重新查詢</button></section>;
  if (!context) return null;

  return <section aria-label="歷史訂單 review 更正" data-review-identity={context.review_identity}>
    <h3>歷史訂單欄位衝突更正</h3>
    <p>案件：{context.masked_case_identity}</p>
    <p>完成條件：{context.completion_condition}</p>
    {renderIssues(context.issues, '目前欄位衝突')}
    <div aria-label="更正檔案要求">
      <h4>更正檔案要求</h4>
      <p>請上傳單列 .{context.workbook_contract.file_extension}，欄位需包含：{context.workbook_contract.required_columns.join('、')}。</p>
    </div>
    <details><summary>技術詳情與資料來源</summary>
      <p>待確認案件識別：{context.review_identity}</p>
      <p>待確認版本：{context.review_version}｜更正版本：{context.remediation_version}</p>
      <p>檔案契約：{context.workbook_contract.contract_key} v{context.workbook_contract.contract_version}</p>
    </details>
    {applyResult ? <div role="status">
      <h4>{applyResult.prior_alert_active ? '更正已提交，等待異常重新檢核' : '原警示已解除'}</h4>
      <p>處理結果：{dispositionLabel(applyResult.disposition)}</p>
      <details><summary>技術操作紀錄</summary>
        <p>更正紀錄：{applyResult.receipt.remediation_receipt_identity}</p>
        <p>來源摘要：{applyResult.receipt.source_content_digest}</p>
        <p>預覽核對值：{applyResult.receipt.preview_fingerprint}</p>
        <p>更正版本：{applyResult.receipt.resulting_remediation_version}</p>
      </details>
      {applyResult.prior_alert_active && renderIssues(
        applyResult.readback.remaining_issues,
        '原 review 尚未解除的欄位衝突',
      )}
      {applyResult.prior_alert_active && <button type="button" onClick={() => void reconcileProjection()} disabled={busy}>重新檢核異常狀態</button>}
      {applyResult.successor ? <div>{renderIssues(applyResult.successor.issues, `後續 review：${applyResult.successor.masked_case_identity}`)}<p>請使用後續 review 的新修正入口。</p></div> : <p>後續流程可繼續推進；原 review 僅保留於歷史紀錄。</p>}
    </div> : <>
      <label>單列更正 .xlsx（必須符合上述契約）<input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => void selectWorkbook(event)} disabled={busy} /></label>
      {fileName && <><p>已選檔案：{fileName}</p>{snapshot && <details><summary>檔案技術詳情</summary><p>內容摘要：{snapshot.sha256}</p></details>}</>}
      <label>處理原因（必填）<textarea value={reason} onChange={(event) => invalidate(() => setReason(event.target.value))} /></label>
      <label>佐證（必填，可填電話或紙本紀錄索引）<textarea value={evidence} onChange={(event) => invalidate(() => setEvidence(event.target.value))} /></label>
      <div><button type="button" onClick={() => void previewAction()} disabled={!canPreview}>{busy ? '處理中…' : 'Preview 更正結果'}</button></div>
      {previewCurrent && preview && <div aria-label="更正 Preview">
        <h4>Preview 結果</h4>
        <p>預計處理：{dispositionLabel(preview.outcome)}</p>
        {renderIssues(preview.remaining_issues, '套用後剩餘欄位衝突')}
        <details><summary>預覽技術詳情</summary>
          <p>來源摘要：{preview.source_content_digest}</p>
          <p>預覽核對值：{preview.preview_fingerprint}</p>
          <p>待確認版本：{preview.review_version}｜更正版本：{preview.remediation_version}</p>
        </details>
        <label><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />我已確認檔案、原因、佐證與 Preview 結果，明確確認套用</label>
        <button type="button" onClick={() => void applyAction()} disabled={!confirmed || busy}>確認套用更正</button>
      </div>}
    </>}
    {unknownOutcome && <div role="alert"><p>套用結果尚未確認；原操作已保留，可先重新查詢再安全重試。</p><button type="button" onClick={() => void readOwner()} disabled={busy}>重新查詢結果</button>{previewCurrent && <button type="button" onClick={() => void applyAction()} disabled={!confirmed || busy}>安全重試原操作</button>}</div>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
    {queryError && <p role="alert">{queryError}</p>}
  </section>;
};

export default HistoricalOrderReviewRemediationWorkbench;
