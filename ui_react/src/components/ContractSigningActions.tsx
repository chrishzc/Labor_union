/**
 * File: ContractSigningActions.tsx
 * Description: 顯示契約寄送、簽回及人工簽約操作，保留已提交 receipt 並區分後續 readback 失敗。
 */
import { useRef, useState } from 'react';
import { contractSigningClient, type ContractSigningStatus } from '../api/orders/contract_signing_client';
import {
  contractSigningMutationClient,
  type ManualAttestationPreview,
  type ManualConfirmationMethod,
  type ContractSigningReceipt,
} from '../api/orders/contract_signing_mutation_client';
import { ApiHttpError } from '../api/shared/typed_errors';

interface ContractSigningActionsProps {
  caseNo: string;
  signing: ContractSigningStatus;
  onCommitted: () => Promise<void> | void;
}

type OperationState = 'idle' | 'working' | 'success' | 'error';
type Intent = { idempotencyKey: string; correlationId: string };
type ManualAttestationDraft = {
  file: File | null;
  confirmationMethod: ManualConfirmationMethod;
  reason: string;
  preview: ManualAttestationPreview | null;
};

const defaultManualAttestationDraft = (): ManualAttestationDraft => ({
  file: null,
  confirmationMethod: 'phone',
  reason: '',
  preview: null,
});

function identity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function message(error: unknown): string {
  if (error instanceof ApiHttpError && typeof error.raw === 'object' && error.raw !== null) {
    const payload = error.raw as { detail?: { error?: { code?: unknown; message?: unknown; domain_blockers?: unknown } }; error?: { code?: unknown; message?: unknown; domain_blockers?: unknown } };
    const typed = payload.detail?.error ?? payload.error;
    if (typed?.code && typed?.message) {
      const blockers = Array.isArray(typed.domain_blockers) && typed.domain_blockers.length
        ? `；阻擋：${typed.domain_blockers.join('、')}`
        : '';
      return `${String(typed.code)}：${String(typed.message)}${blockers}`;
    }
  }
  return error instanceof Error ? error.message : '契約簽署操作失敗，請重新查詢後再試。';
}

function receiptText(receipt: ContractSigningReceipt): string {
  const delivery = receipt.line_delivery_task_id === null
    ? '未建立 LINE 寄送工作。'
    : '已排入 LINE 寄送佇列，尚未代表對方已收到。';
  return `簽署紀錄已建立；${delivery}`;
}

function sentDocumentVersion(signing: ContractSigningStatus, scope: string, targetKey: string): number | null {
  const documents = signing.documents
    .filter((document) => document.scope === scope && document.target_key === targetKey && document.role === 'template_generated')
    .sort((left, right) => right.document_version_id - left.document_version_id);
  return documents[0]?.document_version_id ?? null;
}

export function ContractSigningActions({ caseNo, signing, onCommitted }: ContractSigningActionsProps) {
  const intents = useRef(new Map<string, Intent>());
  const [downloadUrl, setDownloadUrl] = useState('');
  const [staffFiles, setStaffFiles] = useState<Record<number, File | null>>({});
  const [clientFile, setClientFile] = useState<File | null>(null);
  const [staffManualDrafts, setStaffManualDrafts] = useState<Record<number, ManualAttestationDraft>>({});
  const [clientManualDraft, setClientManualDraft] = useState<ManualAttestationDraft>(defaultManualAttestationDraft);
  const [state, setState] = useState<OperationState>('idle');
  const [result, setResult] = useState<string | null>(null);

  const downloadDocument = async (documentVersionId: number) => {
    setState('working');
    setResult(null);
    try {
      const artifact = await contractSigningClient.downloadDocument(caseNo, documentVersionId);
      const objectUrl = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = artifact.filename;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
      setState('success');
      setResult(`已下載不可變契約文件版本 #${documentVersionId}（${artifact.mimeType}）。`);
    } catch (error) {
      setState('error');
      setResult(message(error));
    }
  };

  const currentIntent = (key: string): Intent => {
    const existing = intents.current.get(key);
    if (existing) return existing;
    const next = { idempotencyKey: identity(`contract-${key}-idem`), correlationId: identity(`contract-${key}-corr`) };
    intents.current.set(key, next);
    return next;
  };

  const resetIntent = (key: string): void => { intents.current.delete(key); };
  const validDownloadUrl = (() => {
    try { return new URL(downloadUrl).protocol === 'https:'; } catch { return false; }
  })();
  const run = async (operation: () => Promise<ContractSigningReceipt>) => {
    setState('working');
    setResult(null);
    let receipt: ContractSigningReceipt;
    try {
      receipt = await operation();
    } catch (error) {
      setState('error');
      setResult(message(error));
      return;
    }

    setState('success');
    setResult(receiptText(receipt));
    try {
      await onCommitted();
    } catch (error) {
      setResult(`${receiptText(receipt)} 重新載入結果失敗，可再按查詢確認；不需重複送出：${message(error)}`);
    }
  };
  const previewManual = async (operation: () => Promise<ManualAttestationPreview>, onPreview: (preview: ManualAttestationPreview) => void) => {
    setState('working');
    setResult(null);
    try {
      const preview = await operation();
      onPreview(preview);
      setState('success');
      setResult(`人工簽約證據已完成送出前檢查（${preview.confirmation_method}）；未建立 LINE 寄送任務。請確認後再套用。`);
    } catch (error) {
      setState('error');
      setResult(message(error));
    }
  };

  return (
    <section className="contract-signing-panel" aria-label="契約寄送與簽回文件操作" data-control-id="orders.contract-signing.actions">
      <div className="contract-signing-header">
        <h3 className="contract-signing-title">📦 契約寄送與簽回文件操作</h3>
        <p className="contract-signing-desc">
          寄送前會核對目前契約狀態。確認後只建立待寄送工作，並不代表 LINE 已送達。人工簽約證據必須先檢查內容、由人員確認後才可補登，且不會建立 LINE 寄送工作。
        </p>
        <div className="contract-signing-url-box">
          <label htmlFor="contract-signing-download-url">受控 HTTPS 文件下載網址</label>
          <input
            id="contract-signing-download-url"
            className="contract-signing-url-input"
            type="url"
            value={downloadUrl}
            placeholder="請輸入受控 HTTPS 下載網址 (例如：https://storage.labor-union.org/cases/...)"
            disabled={state === 'working'}
            onChange={(event) => {
              setDownloadUrl(event.target.value);
              for (const segment of signing.staff_segments) resetIntent(`staff-send-${segment.segment_id}`);
              resetIntent('client-send');
              setState('idle');
              setResult(null);
            }}
          />
          {!validDownloadUrl && (
            <p className="contract-signing-hint">
              ⚠️ 寄送前須填寫 HTTPS 文件下載網址；本機網址不可送入 LINE 任務。
            </p>
          )}
        </div>
      </div>

      {/* 已封存契約文件版本 */}
      <section className="contract-signing-section" aria-label="已封存契約文件版本">
        <h4 className="contract-signing-section-title">📁 已封存契約文件版本</h4>
        <p style={{ margin: 0, fontSize: '0.82rem', color: '#74593f' }}>
          下載會經由案件、角色與文件版本授權，並寫入稽核紀錄；PDF 文件將原樣匯出，不在瀏覽器重新轉檔。
        </p>
        {signing.documents.length === 0 ? (
          <p className="contract-signing-empty-text">目前尚無已封存契約文件版本。</p>
        ) : (
          <div className="contract-signing-doc-list">
            {signing.documents.map((document) => (
              <article key={document.document_version_id} className="contract-signing-action-row">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong>契約第 {document.version_number} 版</strong>
                  <span style={{ fontSize: '0.75rem', background: '#fff0eb', color: '#ea580c', padding: '2px 8px', borderRadius: '6px', fontWeight: 700 }}>
                    {document.mime_type}
                  </span>
                </div>
                <p>
                  已封存文件，可依案件與簽署角色授權下載。
                </p>
                <button
                  type="button"
                  className="contract-btn-secondary"
                  disabled={state === 'working'}
                  onClick={() => void downloadDocument(document.document_version_id)}
                >
                  📥 下載／匯出此文件
                </button>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* 月嫂分段 */}
      <section className="contract-signing-section">
        <h4 className="contract-signing-section-title">👩‍🍼 月嫂分段契約</h4>
        {signing.staff_segments.length === 0 ? (
          <p className="contract-signing-empty-text">尚無正式月嫂分段，不能寄送或收錄月嫂簽回。</p>
        ) : (
          signing.staff_segments.map((segment) => {
            const version = sentDocumentVersion(signing, 'staff_segment', `staff-segment:${segment.segment_id}`);
            const file = staffFiles[segment.segment_id] ?? null;
            const manual = staffManualDrafts[segment.segment_id] ?? defaultManualAttestationDraft();
            const updateManual = (next: Partial<ManualAttestationDraft>) => setStaffManualDrafts((current) => ({
              ...current,
              [segment.segment_id]: { ...manual, ...next, preview: next.preview === undefined ? null : next.preview },
            }));
            return (
              <article key={segment.segment_id} className="contract-signing-action-row">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong>分段 #{segment.segment_id}／月嫂 #{segment.staff_id}</strong>
                  <span className={`contract-status-pill ${segment.signed_received ? 'success' : segment.sent ? 'pending' : 'pending'}`}>
                    {segment.signed_received ? '🟢 已簽回' : segment.sent ? '🟡 等待簽回' : '⚪ 尚未寄送'}
                  </span>
                </div>
                <p>
                  {segment.signed_received
                    ? '已簽回。'
                    : segment.sent
                    ? '已建立寄送工作，等待簽回；這不代表 LINE 已送達。'
                    : '尚未寄送。'}
                </p>
                {!segment.sent && (
                  <div>
                    <button
                      type="button"
                      className="contract-btn-primary"
                      disabled={state === 'working' || !validDownloadUrl}
                      onClick={() => void run(() =>
                        contractSigningMutationClient.sendStaff(caseNo, segment.segment_id, downloadUrl, currentIntent(`staff-send-${segment.segment_id}`))
                      )}
                    >
                      🚀 確認建立月嫂契約寄送任務
                    </button>
                  </div>
                )}
                {segment.sent && !segment.signed_received && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px' }}>
                    <div className="contract-signing-field">
                      <label htmlFor={`contract-signing-staff-file-${segment.segment_id}`}>月嫂簽回檔</label>
                      <input
                        id={`contract-signing-staff-file-${segment.segment_id}`}
                        type="file"
                        accept=".pdf,.xlsx,.xls,.doc,.docx,image/*"
                        disabled={state === 'working'}
                        onChange={(event) => {
                          const next = event.target.files?.item(0) ?? null;
                          setStaffFiles((current) => ({ ...current, [segment.segment_id]: next }));
                          resetIntent(`staff-return-${segment.segment_id}`);
                        }}
                      />
                    </div>
                    <button
                      type="button"
                      className="contract-btn-primary"
                      disabled={state === 'working' || !file || version === null}
                      onClick={() => void run(() =>
                        contractSigningMutationClient.uploadStaffSignedReturn(caseNo, segment.segment_id, file!, version!, currentIntent(`staff-return-${segment.segment_id}`))
                      )}
                    >
                      📤 確認記錄月嫂簽回
                    </button>
                  </div>
                )}
                {!segment.sent && !segment.signed_received && (
                  <section className="contract-signing-manual-panel" aria-label={`月嫂 #${segment.staff_id} 人工簽約證據`}>
                    <h5>📝 人工簽約證據（不建立 LINE 寄送任務）</h5>
                    <p style={{ margin: 0, fontSize: '0.8rem', color: '#8b7169' }}>
                      僅在已取得實際簽約證據並由工會人工確認時使用；這不是任意修改狀態。
                    </p>
                    <div className="contract-signing-manual-grid">
                      <div className="contract-signing-field">
                        <label htmlFor={`contract-signing-staff-manual-file-${segment.segment_id}`}>人工月嫂簽約證據檔</label>
                        <input
                          id={`contract-signing-staff-manual-file-${segment.segment_id}`}
                          type="file"
                          accept=".pdf,.xlsx,.xls,.doc,.docx,image/*"
                          disabled={state === 'working'}
                          onChange={(event) => {
                            updateManual({ file: event.target.files?.item(0) ?? null });
                            resetIntent(`staff-manual-${segment.segment_id}`);
                          }}
                        />
                      </div>
                      <div className="contract-signing-field">
                        <label htmlFor={`contract-signing-staff-manual-method-${segment.segment_id}`}>月嫂人工確認方式</label>
                        <select
                          id={`contract-signing-staff-manual-method-${segment.segment_id}`}
                          value={manual.confirmationMethod}
                          disabled={state === 'working'}
                          onChange={(event) => {
                            updateManual({ confirmationMethod: event.target.value as ManualConfirmationMethod });
                            resetIntent(`staff-manual-${segment.segment_id}`);
                          }}
                        >
                          <option value="phone">電話確認</option>
                          <option value="paper">紙本確認</option>
                          <option value="in_person">當面確認</option>
                          <option value="verified_other">其他已驗證方式</option>
                        </select>
                      </div>
                      <div className="contract-signing-field" style={{ gridColumn: '1 / -1' }}>
                        <label htmlFor={`contract-signing-staff-manual-reason-${segment.segment_id}`}>月嫂人工確認依據</label>
                        <input
                          id={`contract-signing-staff-manual-reason-${segment.segment_id}`}
                          value={manual.reason}
                          disabled={state === 'working'}
                          placeholder="請輸入人工確認之完整依據與電話/紙本記錄"
                          onChange={(event) => {
                            updateManual({ reason: event.target.value });
                            resetIntent(`staff-manual-${segment.segment_id}`);
                          }}
                        />
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '6px' }}>
                      <button
                        type="button"
                        className="contract-btn-secondary"
                        disabled={state === 'working' || !manual.file || !manual.reason.trim()}
                        onClick={() => void previewManual(
                          () => contractSigningMutationClient.previewManualStaffAttestation(caseNo, segment.segment_id, manual.confirmationMethod, manual.reason, currentIntent(`staff-manual-${segment.segment_id}`)),
                          (preview) => updateManual({ preview }),
                        )}
                      >
                        🔍 預覽人工月嫂簽約證據
                      </button>
                      <button
                        type="button"
                        className="contract-btn-primary"
                        disabled={state === 'working' || !manual.file || manual.preview === null}
                        onClick={() => void run(() =>
                          contractSigningMutationClient.recordManualStaffAttestation(caseNo, segment.segment_id, manual.file!, manual.confirmationMethod, manual.reason, manual.preview!.preview_fingerprint, currentIntent(`staff-manual-${segment.segment_id}`))
                        )}
                      >
                        ✅ 確認記錄人工月嫂簽約
                      </button>
                    </div>
                    {manual.preview && (
                      <p style={{ margin: 0, fontSize: '0.8rem', color: '#166534', fontWeight: 600 }}>
                        ✨ 人工簽署補登內容已完成檢查，請核對簽署人、證據檔案與確認方式。
                      </p>
                    )}
                  </section>
                )}
              </article>
            );
          })
        )}
      </section>

      {/* 客戶契約 */}
      <section className="contract-signing-section">
        <h4 className="contract-signing-section-title">👥 產婦客戶契約</h4>
        {(() => {
          const version = sentDocumentVersion(signing, 'client_contract', 'client-contract');
          const updateClientManual = (next: Partial<ManualAttestationDraft>) => setClientManualDraft((current) => ({
            ...current,
            ...next,
            preview: next.preview === undefined ? null : next.preview,
          }));
          return (
            <article className="contract-signing-action-row">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong>客戶正式服務契約</strong>
                <span className={`contract-status-pill ${signing.client_signed_received ? 'success' : signing.client_document_sent ? 'pending' : 'pending'}`}>
                  {signing.client_signed_received ? '🟢 已簽回' : signing.client_document_sent ? '🟡 等待簽回' : '⚪ 尚未寄送'}
                </span>
              </div>
              <p>
                {signing.client_signed_received
                  ? '客戶契約已簽回。'
                  : signing.client_document_sent
                  ? '已建立寄送工作，等待客戶簽回；這不代表 LINE 已送達。'
                  : signing.commitment_id === null
                  ? '尚未建立有效服務承諾，不能寄送客戶契約。'
                  : '可建立客戶契約寄送任務。'}
              </p>
              {!signing.client_document_sent && (
                <div>
                  <button
                    type="button"
                    className="contract-btn-primary"
                    disabled={state === 'working' || !validDownloadUrl || signing.commitment_id === null}
                    onClick={() => void run(() =>
                      contractSigningMutationClient.sendClient(caseNo, downloadUrl, currentIntent('client-send'))
                    )}
                  >
                    🚀 確認建立客戶契約寄送任務
                  </button>
                </div>
              )}
              {signing.client_document_sent && !signing.client_signed_received && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px' }}>
                  <div className="contract-signing-field">
                    <label htmlFor="contract-signing-client-file">客戶簽回檔</label>
                    <input
                      id="contract-signing-client-file"
                      type="file"
                      accept=".pdf,.xlsx,.xls,.doc,.docx,image/*"
                      disabled={state === 'working'}
                      onChange={(event) => {
                        setClientFile(event.target.files?.item(0) ?? null);
                        resetIntent('client-return');
                      }}
                    />
                  </div>
                  <button
                    type="button"
                    className="contract-btn-primary"
                    disabled={state === 'working' || !clientFile || version === null}
                    onClick={() => void run(() =>
                      contractSigningMutationClient.uploadClientSignedReturn(caseNo, clientFile!, version!, currentIntent('client-return'))
                    )}
                  >
                    📤 確認記錄客戶簽回並完成契約
                  </button>
                </div>
              )}
              {signing.commitment_id !== null && !signing.client_document_sent && !signing.client_signed_received && (
                <section className="contract-signing-manual-panel" aria-label="客戶人工簽約證據">
                  <h5>📝 人工簽約證據（不建立 LINE 寄送任務）</h5>
                  <p style={{ margin: 0, fontSize: '0.8rem', color: '#8b7169' }}>
                    僅在已取得實際簽約證據並由工會人工確認時使用；這不是任意修改狀態。
                  </p>
                  <div className="contract-signing-manual-grid">
                    <div className="contract-signing-field">
                      <label htmlFor="contract-signing-client-manual-file">人工客戶簽約證據檔</label>
                      <input
                        id="contract-signing-client-manual-file"
                        type="file"
                        accept=".pdf,.xlsx,.xls,.doc,.docx,image/*"
                        disabled={state === 'working'}
                        onChange={(event) => {
                          updateClientManual({ file: event.target.files?.item(0) ?? null });
                          resetIntent('client-manual');
                        }}
                      />
                    </div>
                    <div className="contract-signing-field">
                      <label htmlFor="contract-signing-client-manual-method">客戶人工確認方式</label>
                      <select
                        id="contract-signing-client-manual-method"
                        value={clientManualDraft.confirmationMethod}
                        disabled={state === 'working'}
                        onChange={(event) => {
                          updateClientManual({ confirmationMethod: event.target.value as ManualConfirmationMethod });
                          resetIntent('client-manual');
                        }}
                      >
                        <option value="phone">電話確認</option>
                        <option value="paper">紙本確認</option>
                        <option value="in_person">當面確認</option>
                        <option value="verified_other">其他已驗證方式</option>
                      </select>
                    </div>
                    <div className="contract-signing-field" style={{ gridColumn: '1 / -1' }}>
                      <label htmlFor="contract-signing-client-manual-reason">客戶人工確認依據</label>
                      <input
                        id="contract-signing-client-manual-reason"
                        value={clientManualDraft.reason}
                        disabled={state === 'working'}
                        placeholder="請輸入人工確認之完整依據與電話/紙本記錄"
                        onChange={(event) => {
                          updateClientManual({ reason: event.target.value });
                          resetIntent('client-manual');
                        }}
                      />
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '6px' }}>
                    <button
                      type="button"
                      className="contract-btn-secondary"
                      disabled={state === 'working' || !clientManualDraft.file || !clientManualDraft.reason.trim()}
                      onClick={() => void previewManual(
                        () => contractSigningMutationClient.previewManualClientAttestation(caseNo, clientManualDraft.confirmationMethod, clientManualDraft.reason, currentIntent('client-manual')),
                        (preview) => updateClientManual({ preview }),
                      )}
                    >
                      🔍 預覽人工客戶簽約證據
                    </button>
                    <button
                      type="button"
                      className="contract-btn-primary"
                      disabled={state === 'working' || !clientManualDraft.file || clientManualDraft.preview === null}
                      onClick={() => void run(() =>
                        contractSigningMutationClient.recordManualClientAttestation(caseNo, clientManualDraft.file!, clientManualDraft.confirmationMethod, clientManualDraft.reason, clientManualDraft.preview!.preview_fingerprint, currentIntent('client-manual'))
                      )}
                    >
                      ✅ 確認記錄人工客戶簽約並完成契約
                    </button>
                  </div>
                  {clientManualDraft.preview && (
                    <p style={{ margin: 0, fontSize: '0.8rem', color: '#166534', fontWeight: 600 }}>
                      ✨ 人工簽署補登內容已完成檢查，請核對簽署人、證據檔案與確認方式。
                    </p>
                  )}
                </section>
              )}
            </article>
          );
        })()}
      </section>

      {state === 'working' && (
        <div className="contract-status-working" role="status">
          ⏳ 正在提交契約簽署命令…
        </div>
      )}
      {result && (
        <div className={state === 'error' ? 'line-error' : 'line-success'} role={state === 'error' ? 'alert' : 'status'}>
          {result}
        </div>
      )}
    </section>
  );
}
