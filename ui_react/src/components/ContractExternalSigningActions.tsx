/**
 * File: ContractExternalSigningActions.tsx
 * Description: 呈現外部簽約 successor closed states、完成回報與最終 PDF 確認、Apply、receipt/readback。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  contractExternalSigningClient,
  createExternalSigningCommandIdentity,
  type ContractExternalSigningQuery,
  type ExternalSigningCommandIdentity,
  type ExternalSigningConfirmationMethod,
  type ExternalSigningReceipt,
  type FinalDocumentPreview,
  type FinalDocumentReadback,
} from '../api/orders/contract_external_signing_client';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../api/shared/typed_errors';

export interface ContractExternalSigningActionsProps {
  caseNo: string;
  onCommitted?: () => Promise<void> | void;
}

type WorkingOperation = 'query' | 'download' | 'staff_report' | 'client_report' | 'final_preview' | 'final_apply' | 'receipt' | 'readback';

export type ContractExternalSigningUiState =
  | { type: 'querying' }
  | { type: 'ready' }
  | { type: 'working'; operation: WorkingOperation }
  | { type: 'preview_ready'; preview: FinalDocumentPreview; confirmed: boolean }
  | { type: 'receipt_committed'; receipt: ExternalSigningReceipt; message: string }
  | { type: 'outcome_unknown'; identity: ExternalSigningCommandIdentity; message: string }
  | { type: 'observed'; receipt: ExternalSigningReceipt; readback: FinalDocumentReadback }
  | { type: 'error'; message: string };

const unsafePublicText = /https?:\/\/|[A-Za-z]:\\|\\\\|\/(?:mnt|Volumes|private|var)\/|[0-9a-f]{64}|preview[_ -]?fingerprint|storage[_ -]?locator|raw[_ -]?cursor/i;

function safeErrorMessage(error: unknown): string {
  const fallback = '外部簽約操作失敗，請重新查詢目前狀態。';
  const message = error instanceof Error ? error.message : fallback;
  if (unsafePublicText.test(message)) return fallback;
  if (error instanceof ApiHttpError) return `${error.code}：${message}`;
  return message || fallback;
}

function outcomeCouldBeUnknown(error: unknown): boolean {
  return error instanceof ApiTimeoutError
    || error instanceof ApiNetworkError
    || (error instanceof ApiHttpError && error.retryable);
}

function stateLabel(query: ContractExternalSigningQuery): string {
  switch (query.state) {
    case 'staff_reporting': return '等待月嫂完成回報';
    case 'staff_reports_complete': return '月嫂回報完成，等待客戶回報';
    case 'client_reported_final_pdf_pending': return '最終簽署 PDF 待回收';
    case 'completed': return '契約完成';
    case 'superseded': return '此簽約工作已被新版取代';
  }
}

function currentIdentity(
  identities: Map<string, ExternalSigningCommandIdentity>,
  key: string,
): ExternalSigningCommandIdentity {
  const existing = identities.get(key);
  if (existing) return existing;
  const created = createExternalSigningCommandIdentity(key);
  identities.set(key, created);
  return created;
}

export function ContractExternalSigningActions({ caseNo, onCommitted }: ContractExternalSigningActionsProps) {
  const identities = useRef(new Map<string, ExternalSigningCommandIdentity>());
  const requestGeneration = useRef(0);
  const [query, setQuery] = useState<ContractExternalSigningQuery | null>(null);
  const [uiState, setUiState] = useState<ContractExternalSigningUiState>({ type: 'querying' });
  const [notice, setNotice] = useState<string | null>(null);
  const [staffReasons, setStaffReasons] = useState<Record<number, string>>({});
  const [clientReason, setClientReason] = useState('');
  const [confirmationMethod, setConfirmationMethod] = useState<ExternalSigningConfirmationMethod>('verified_other');
  const [finalFile, setFinalFile] = useState<File | null>(null);

  const loadQuery = useCallback(async (signal?: AbortSignal): Promise<ContractExternalSigningQuery> => {
    const generation = ++requestGeneration.current;
    setUiState({ type: 'querying' });
    const value = await contractExternalSigningClient.query(caseNo, { signal });
    if (generation !== requestGeneration.current) return value;
    setQuery(value);
    setUiState({ type: 'ready' });
    return value;
  }, [caseNo]);

  useEffect(() => {
    const controller = new AbortController();
    setQuery(null);
    setNotice(null);
    setFinalFile(null);
    identities.current.clear();
    void loadQuery(controller.signal).then(async (value) => {
      if (controller.signal.aborted || value.state !== 'completed') return;
      try {
        setUiState({ type: 'working', operation: 'readback' });
        const readback = await contractExternalSigningClient.getFinalDocumentReadback(caseNo, controller.signal);
        if (!controller.signal.aborted) {
          setNotice(`最終 PDF 第 ${readback.version_number} 版已完成 readback，完整性驗證通過。`);
          setUiState({ type: 'ready' });
        }
      } catch (error) {
        if (!controller.signal.aborted) setUiState({ type: 'error', message: safeErrorMessage(error) });
      }
    }).catch((error) => {
      if (!controller.signal.aborted) setUiState({ type: 'error', message: safeErrorMessage(error) });
    });
    return () => {
      requestGeneration.current += 1;
      controller.abort();
    };
  }, [caseNo, loadQuery]);

  const downloadUnsigned = async (documentVersionId: number, targetLabel: string) => {
    if (!query?.unsigned_document) return;
    setUiState({ type: 'working', operation: 'download' });
    setNotice(null);
    try {
      const artifact = await contractExternalSigningClient.downloadUnsignedPdf(
        caseNo,
        documentVersionId,
      );
      const url = URL.createObjectURL(artifact.blob);
      try {
        const link = document.createElement('a');
        link.href = url;
        link.download = artifact.filename;
        link.click();
      } finally {
        URL.revokeObjectURL(url);
      }
      setNotice(`${targetLabel}未簽契約 PDF「${artifact.filename}」已下載。`);
      setUiState({ type: 'ready' });
    } catch (error) {
      setUiState({ type: 'error', message: safeErrorMessage(error) });
    }
  };

  const runReport = async (
    key: string,
    operation: (identity: ExternalSigningCommandIdentity) => Promise<ExternalSigningReceipt>,
  ) => {
    const identity = currentIdentity(identities.current, key);
    setNotice(null);
    setUiState({ type: 'working', operation: key.startsWith('staff') ? 'staff_report' : 'client_report' });
    try {
      const receipt = await operation(identity);
      identities.current.delete(key);
      setNotice(receipt.replayed ? '完成回報已安全重播，正在重新查詢。' : '完成回報已記錄，正在重新查詢。');
      await loadQuery();
    } catch (error) {
      if (outcomeCouldBeUnknown(error)) {
        setUiState({ type: 'outcome_unknown', identity, message: '完成回報結果未明；只可用原命令識別查詢 receipt。' });
      } else {
        setUiState({ type: 'error', message: safeErrorMessage(error) });
      }
    }
  };

  const previewFinalDocument = async () => {
    if (!query || !finalFile) return;
    const identity = currentIdentity(identities.current, 'final-stage');
    setNotice(null);
    setUiState({ type: 'working', operation: 'final_preview' });
    try {
      const staged = await contractExternalSigningClient.stageFinalDocument(caseNo, finalFile, identity);
      const preview = await contractExternalSigningClient.previewFinalDocument(caseNo, {
        staging_id: staged.staging_id,
        expected_status_version: query.status_version,
      });
      identities.current.delete('final-stage');
      identities.current.delete('final-apply');
      setUiState({ type: 'preview_ready', preview, confirmed: false });
    } catch (error) {
      setUiState({ type: 'error', message: safeErrorMessage(error) });
    }
  };

  const observeFinalReceipt = async (receipt: ExternalSigningReceipt) => {
    setUiState({ type: 'receipt_committed', receipt, message: 'Apply receipt 已提交；正在核對最終文件 readback。' });
    try {
      const readback = await contractExternalSigningClient.getFinalDocumentReadback(caseNo);
      if (receipt.final_document_id !== readback.final_document_id || receipt.session_id !== readback.session_id) {
        throw new Error('最終 PDF receipt 與 readback identity 不一致。');
      }
      setUiState({ type: 'observed', receipt, readback });
      setNotice(`契約完成，最終 PDF 已完成 readback（第 ${readback.version_number} 版，完整性驗證通過）。`);
      await onCommitted?.();
    } catch (error) {
      setUiState({
        type: 'receipt_committed',
        receipt,
        message: `Apply receipt 已提交，但 readback 尚未確認；不要重送 Apply。${safeErrorMessage(error)}`,
      });
    }
  };

  const applyFinalDocument = async () => {
    if (!query || uiState.type !== 'preview_ready' || !uiState.confirmed || !uiState.preview.can_apply) return;
    const preview = uiState.preview;
    const identity = currentIdentity(identities.current, 'final-apply');
    setUiState({ type: 'working', operation: 'final_apply' });
    try {
      const receipt = await contractExternalSigningClient.applyFinalDocument(caseNo, {
        staging_id: preview.staging_id,
        expected_staging_version: preview.expected_staging_version,
        preview_token: preview.preview_token,
        expected_status_version: query.status_version,
      }, identity);
      identities.current.delete('final-apply');
      await observeFinalReceipt(receipt);
    } catch (error) {
      if (outcomeCouldBeUnknown(error)) {
        setUiState({ type: 'outcome_unknown', identity, message: '最終 PDF Apply 結果未明；不得重送，只能以原命令查 receipt。' });
      } else {
        setUiState({ type: 'error', message: safeErrorMessage(error) });
      }
    }
  };

  const reconcileUnknown = async () => {
    if (uiState.type !== 'outcome_unknown') return;
    const identity = uiState.identity;
    setUiState({ type: 'working', operation: 'receipt' });
    try {
      const receipt = await contractExternalSigningClient.getReceipt(caseNo, identity.receiptId);
      if (receipt.command_type === 'apply_final_signed_contract') {
        identities.current.delete('final-apply');
        await observeFinalReceipt(receipt);
      } else {
        await loadQuery();
      }
    } catch (error) {
      setUiState({
        type: 'outcome_unknown',
        identity,
        message: `receipt 尚未可觀察；請稍後仍以原命令查詢。${safeErrorMessage(error)}`,
      });
    }
  };

  const retryReadback = async () => {
    if (uiState.type !== 'receipt_committed') return;
    const receipt = uiState.receipt;
    setUiState({ type: 'working', operation: 'readback' });
    await observeFinalReceipt(receipt);
  };

  const busy = uiState.type === 'working';

  return (
    <section aria-label="外部平台簽約與最終 PDF" data-control-id="orders.contract-external-signing.actions" style={{ display: 'grid', gap: '14px' }}>
      <header>
        <h3 style={{ margin: 0 }}>📄 外部平台簽約與最終 PDF</h3>
        <p style={{ margin: '6px 0 0', color: '#74593f', fontSize: '0.84rem' }}>
          系統只保存完成回報與受控最終文件；外部平台狀態、LINE 已送達或畫面提示都不等於契約完成。
        </p>
      </header>

      {query && (
        <div role="status" style={{ padding: '10px 12px', border: '1px solid #fed7aa', borderRadius: '10px', background: '#fff8f6' }}>
          <strong>{stateLabel(query)}</strong>
          <div style={{ fontSize: '0.8rem', color: '#74593f' }}>狀態版本 {query.status_version}</div>
        </div>
      )}

      {query?.unsigned_document && (
        <section aria-label="未簽契約 PDF" style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px' }}>
          <strong>未簽契約 PDF</strong>
          <div style={{ fontSize: '0.82rem', margin: '5px 0' }}>
            {query.unsigned_document.filename}｜{query.unsigned_document.size_bytes.toLocaleString()} bytes
          </div>
          <div style={{ display: 'grid', gap: '6px' }}>
            {query.staff_targets.map((target) => (
              <button
                key={target.matching_segment_id}
                type="button"
                disabled={busy}
                onClick={() => void downloadUnsigned(target.document_version_id, `月嫂 ${target.staff_subject_reference} `)}
              >
                下載月嫂 {target.staff_subject_reference} 未簽契約 PDF
              </button>
            ))}
            <button
              type="button"
              disabled={busy}
              onClick={() => void downloadUnsigned(
                query.client_target.document_version_id,
                `客戶 ${query.client_target.client_subject_reference} `,
              )}
            >
              下載客戶 {query.client_target.client_subject_reference} 未簽契約 PDF
            </button>
          </div>
        </section>
      )}

      {query?.staff_targets.map((target) => (
        <section key={target.matching_segment_id} aria-label={`月嫂 ${target.staff_subject_reference} 外部簽署回報`} style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px' }}>
          <strong>月嫂 {target.staff_subject_reference}</strong>
          <div style={{ fontSize: '0.82rem', margin: '5px 0' }}>{target.reported ? '完成回報已記錄' : '尚待外部簽署完成回報'}</div>
          {!target.reported && query.state === 'staff_reporting' && (
            <>
              <label style={{ display: 'grid', gap: '4px' }}>
                月嫂完成證據
                <input
                  value={staffReasons[target.matching_segment_id] ?? ''}
                  disabled={busy}
                  maxLength={500}
                  onChange={(event) => {
                    setStaffReasons((current) => ({ ...current, [target.matching_segment_id]: event.target.value }));
                    identities.current.delete(`staff-${target.matching_segment_id}`);
                  }}
                />
              </label>
              <button
                type="button"
                disabled={busy || !(staffReasons[target.matching_segment_id] ?? '').trim()}
                onClick={() => void runReport(`staff-${target.matching_segment_id}`, (identity) =>
                  contractExternalSigningClient.recordStaffCompletionReport(caseNo, target.matching_segment_id, {
                    expected_status_version: query.status_version,
                    expected_document_version_id: target.document_version_id,
                    confirmation_method: confirmationMethod,
                    reason: staffReasons[target.matching_segment_id] ?? '',
                  }, identity))}
              >
                記錄月嫂 {target.staff_subject_reference} 完成回報
              </button>
            </>
          )}
        </section>
      ))}

      {query && (
        <label style={{ display: 'grid', gap: '4px', maxWidth: '320px' }}>
          受控人工確認方式
          <select value={confirmationMethod} disabled={busy} onChange={(event) => {
            setConfirmationMethod(event.target.value as ExternalSigningConfirmationMethod);
            identities.current.clear();
          }}>
            <option value="phone">電話確認</option>
            <option value="paper">紙本確認</option>
            <option value="in_person">當面確認</option>
            <option value="verified_other">其他已驗證方式</option>
          </select>
        </label>
      )}

      {query?.state === 'staff_reports_complete' && !query.client_target.reported && query.commitment_id !== null && (
        <section aria-label="客戶外部簽署回報" style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px' }}>
          <strong>客戶 {query.client_target.client_subject_reference}</strong>
          <label style={{ display: 'grid', gap: '4px' }}>
            客戶完成證據
            <input value={clientReason} disabled={busy} maxLength={500} onChange={(event) => {
              setClientReason(event.target.value);
              identities.current.delete('client-report');
            }} />
          </label>
          <button
            type="button"
            disabled={busy || !clientReason.trim()}
            onClick={() => void runReport('client-report', (identity) =>
              contractExternalSigningClient.recordClientCompletionReport(caseNo, {
                expected_status_version: query.status_version,
                expected_document_version_id: query.client_target.document_version_id,
                expected_commitment_id: query.commitment_id!,
                confirmation_method: confirmationMethod,
                reason: clientReason,
              }, identity))}
          >
            記錄客戶完成回報
          </button>
        </section>
      )}

      {query?.state === 'client_reported_final_pdf_pending' && (
        <section aria-label="最終簽署 PDF 納管" style={{ border: '1px solid #dec0b6', borderRadius: '10px', padding: '12px', display: 'grid', gap: '8px' }}>
          <strong>最終簽署 PDF 待回收</strong>
          <label style={{ display: 'grid', gap: '4px' }}>
            最終簽署 PDF
            <input
              type="file"
              accept="application/pdf,.pdf"
              disabled={busy}
              onChange={(event) => {
                setFinalFile(event.target.files?.item(0) ?? null);
                identities.current.delete('final-stage');
                identities.current.delete('final-apply');
                setUiState({ type: 'ready' });
              }}
            />
          </label>
          <button type="button" disabled={busy || !finalFile} onClick={() => void previewFinalDocument()}>
            建立最終 PDF 預覽
          </button>
          {uiState.type === 'preview_ready' && (
            <div style={{ padding: '10px', background: '#f0fdf4', borderRadius: '8px' }}>
              <div>{uiState.preview.filename}｜{uiState.preview.size_bytes.toLocaleString()} bytes</div>
              <div>PDF 類型與完整性已由後端驗證；完整 digest 與 Preview fingerprint 不顯示於一般 UI。</div>
              {uiState.preview.blockers.length > 0 && (
                <ul>{uiState.preview.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
              )}
              <label>
                <input
                  type="checkbox"
                  checked={uiState.confirmed}
                  onChange={(event) => setUiState({ ...uiState, confirmed: event.target.checked })}
                />
                我已核對案件、檔名、PDF 類型與版本
              </label>
              <button
                type="button"
                disabled={!uiState.confirmed || !uiState.preview.can_apply}
                onClick={() => void applyFinalDocument()}
              >
                確認套用最終簽署 PDF
              </button>
            </div>
          )}
        </section>
      )}

      {uiState.type === 'working' && <div role="status">正在處理外部簽約命令…</div>}
      {uiState.type === 'error' && <div role="alert">{uiState.message}</div>}
      {uiState.type === 'outcome_unknown' && (
        <div role="alert">
          <div>{uiState.message}</div>
          <button type="button" onClick={() => void reconcileUnknown()}>以原命令查詢 receipt</button>
        </div>
      )}
      {uiState.type === 'receipt_committed' && (
        <div role="status">
          <div>{uiState.message}</div>
          <button type="button" onClick={() => void retryReadback()}>重新查詢最終 PDF readback</button>
        </div>
      )}
      {notice && <div role="status">{notice}</div>}
    </section>
  );
}
