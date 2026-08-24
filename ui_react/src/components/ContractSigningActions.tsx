/**
 * File: ContractSigningActions.tsx
 * Description: 在 Orders 工作台顯示契約寄送與簽回文件操作；外送只建立 durable task，簽回必須鎖定已寄送版本。
 */
import { useRef, useState } from 'react';
import { contractSigningClient, type ContractSigningStatus } from '../api/orders/contract_signing_client';
import {
  contractSigningMutationClient,
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
    ? '未建立 LINE 寄送任務。'
    : `已建立 durable LINE 寄送任務 #${receipt.line_delivery_task_id}。`;
  return `文件版本 #${receipt.document_version_id}、簽署事件 #${receipt.signing_event_id}；${delivery}`;
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
    try {
      const receipt = await operation();
      setState('success');
      setResult(receiptText(receipt));
      await onCommitted();
    } catch (error) {
      setState('error');
      setResult(message(error));
    }
  };

  return (
    <section className="line-action-panel" aria-label="契約寄送與簽回文件操作" data-control-id="orders.contract-signing.actions">
      <h3>契約寄送與簽回文件</h3>
      <p>目前 API 的寄送命令沒有獨立 Preview endpoint；此處顯示 server status snapshot 作送出前檢核。確認後只建立 durable delivery task，並不直接傳送 LINE。</p>
      <label htmlFor="contract-signing-download-url">受控 HTTPS 文件下載網址</label>
      <input
        id="contract-signing-download-url"
        type="url"
        value={downloadUrl}
        placeholder="https://…"
        disabled={state === 'working'}
        onChange={(event) => {
          setDownloadUrl(event.target.value);
          for (const segment of signing.staff_segments) resetIntent(`staff-send-${segment.segment_id}`);
          resetIntent('client-send');
          setState('idle');
          setResult(null);
        }}
      />
      {!validDownloadUrl && <p>寄送前須填寫 HTTPS 文件下載網址；本機網址不可送入 LINE 任務。</p>}

      <section aria-label="已封存契約文件版本">
        <h4>已封存契約文件版本</h4>
        <p>下載會經由案件、角色與文件版本授權，並寫入稽核紀錄；PDF 文件將原樣匯出，不在瀏覽器重新轉檔。</p>
        {signing.documents.length === 0 ? <p>目前尚無已封存契約文件版本。</p> : signing.documents.map((document) => (
          <article key={document.document_version_id} className="contract-signing-action-row">
            <strong>版本 #{document.document_version_id}（v{document.version_number}）</strong>
            <p>{document.scope}／{document.role}／{document.mime_type}／{document.file_size.toLocaleString()} bytes</p>
            <button
              type="button"
              disabled={state === 'working'}
              onClick={() => void downloadDocument(document.document_version_id)}
            >
              下載／匯出此文件
            </button>
          </article>
        ))}
      </section>

      <h4>月嫂分段</h4>
      {signing.staff_segments.length === 0 ? <p>尚無正式月嫂分段，不能寄送或收錄月嫂簽回。</p> : signing.staff_segments.map((segment) => {
        const version = sentDocumentVersion(signing, 'staff_segment', `staff-segment:${segment.segment_id}`);
        const file = staffFiles[segment.segment_id] ?? null;
        return (
          <article key={segment.segment_id} className="contract-signing-action-row">
            <strong>分段 #{segment.segment_id}／月嫂 #{segment.staff_id}</strong>
            <p>{segment.signed_received ? '已簽回。' : segment.sent ? `已寄送，等待簽回（sent 文件版本 #${version ?? '待重新查詢'}）。` : '尚未寄送。'}</p>
            {!segment.sent && (
              <button type="button" disabled={state === 'working' || !validDownloadUrl} onClick={() => void run(() =>
                contractSigningMutationClient.sendStaff(caseNo, segment.segment_id, downloadUrl, currentIntent(`staff-send-${segment.segment_id}`))
              )}>確認建立月嫂契約寄送任務</button>
            )}
            {segment.sent && !segment.signed_received && (
              <>
                <label htmlFor={`contract-signing-staff-file-${segment.segment_id}`}>月嫂簽回檔</label>
                <input id={`contract-signing-staff-file-${segment.segment_id}`} type="file" accept=".pdf,.xlsx,.xls,.doc,.docx,image/*" disabled={state === 'working'} onChange={(event) => {
                  const next = event.target.files?.item(0) ?? null;
                  setStaffFiles((current) => ({ ...current, [segment.segment_id]: next }));
                  resetIntent(`staff-return-${segment.segment_id}`);
                }} />
                <button type="button" disabled={state === 'working' || !file || version === null} onClick={() => void run(() =>
                  contractSigningMutationClient.uploadStaffSignedReturn(caseNo, segment.segment_id, file!, version!, currentIntent(`staff-return-${segment.segment_id}`))
                )}>確認記錄月嫂簽回</button>
              </>
            )}
          </article>
        );
      })}

      <h4>客戶契約</h4>
      {(() => {
        const version = sentDocumentVersion(signing, 'client_contract', 'client-contract');
        return (
          <article className="contract-signing-action-row">
            <p>{signing.client_signed_received ? '客戶契約已簽回。' : signing.client_document_sent ? `已寄送，等待客戶簽回（sent 文件版本 #${version ?? '待重新查詢'}）。` : signing.commitment_id === null ? '尚未建立有效服務承諾，不能寄送客戶契約。' : '可建立客戶契約寄送任務。'}</p>
            {!signing.client_document_sent && (
              <button type="button" disabled={state === 'working' || !validDownloadUrl || signing.commitment_id === null} onClick={() => void run(() =>
                contractSigningMutationClient.sendClient(caseNo, downloadUrl, currentIntent('client-send'))
              )}>確認建立客戶契約寄送任務</button>
            )}
            {signing.client_document_sent && !signing.client_signed_received && (
              <>
                <label htmlFor="contract-signing-client-file">客戶簽回檔</label>
                <input id="contract-signing-client-file" type="file" accept=".pdf,.xlsx,.xls,.doc,.docx,image/*" disabled={state === 'working'} onChange={(event) => {
                  setClientFile(event.target.files?.item(0) ?? null);
                  resetIntent('client-return');
                }} />
                <button type="button" disabled={state === 'working' || !clientFile || version === null} onClick={() => void run(() =>
                  contractSigningMutationClient.uploadClientSignedReturn(caseNo, clientFile!, version!, currentIntent('client-return'))
                )}>確認記錄客戶簽回並完成契約</button>
              </>
            )}
          </article>
        );
      })()}
      {state === 'working' && <div role="status">正在提交契約簽署命令…</div>}
      {result && <div className={state === 'error' ? 'line-error' : 'line-success'} role={state === 'error' ? 'alert' : 'status'}>{result}</div>}
    </section>
  );
}
