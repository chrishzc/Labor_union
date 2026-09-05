import { useEffect, useRef, useState, type FC } from 'react';
import {
  contractSigningClient,
  type ContractSigningStatus,
} from '../api/orders/contract_signing_client';
import {
  contractSigningMutationClient,
  type ContractCommandOptions,
} from '../api/orders/contract_signing_mutation_client';

interface OrderClientContractPanelProps {
  caseNo: string;
  onObserved?: () => void;
}

type ReadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: ContractSigningStatus }
  | { status: 'error'; message: string };

type OperationState =
  | { status: 'idle' }
  | { status: 'working' }
  | { status: 'success'; message: string }
  | { status: 'error'; message: string };

type Intent = Pick<ContractCommandOptions, 'idempotencyKey' | 'correlationId'>;

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '客戶契約操作失敗';
}

function identity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function generatedClientDocumentVersion(signing: ContractSigningStatus): number | null {
  const documents = signing.documents
    .filter((document) => (
      document.scope === 'client_contract'
      && document.target_key === 'client-contract'
      && document.role === 'template_generated'
    ))
    .sort((left, right) => right.document_version_id - left.document_version_id);
  return documents[0]?.document_version_id ?? null;
}

function isHttpsUrl(value: string): boolean {
  try {
    return new URL(value).protocol === 'https:';
  } catch {
    return false;
  }
}

export const OrderClientContractPanel: FC<OrderClientContractPanelProps> = ({ caseNo, onObserved }) => {
  const intents = useRef(new Map<string, Intent>());
  const [readState, setReadState] = useState<ReadState>({ status: 'idle' });
  const [downloadUrl, setDownloadUrl] = useState('');
  const [signedFile, setSignedFile] = useState<File | null>(null);
  const [operation, setOperation] = useState<OperationState>({ status: 'idle' });
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const currentIntent = (key: string): Intent => {
    const existing = intents.current.get(key);
    if (existing) return existing;
    const next = {
      idempotencyKey: identity(`beta-client-contract-${key}-idem`),
      correlationId: identity(`beta-client-contract-${key}-corr`),
    };
    intents.current.set(key, next);
    return next;
  };

  const resetIntent = (key: string) => {
    intents.current.delete(key);
  };

  const loadStatus = async () => {
    setReadState({ status: 'loading' });
    try {
      const data = await contractSigningClient.query(caseNo);
      setReadState({ status: 'ready', data });
    } catch (error) {
      setReadState({ status: 'error', message: errorMessage(error) });
    }
  };

  const runOperation = async (
    operationTask: () => Promise<unknown>,
    successMessage: string,
    expectedStatus: 'client_document_sent' | 'client_signed_received',
  ) => {
    setOperation({ status: 'working' });
    try {
      await operationTask();
      const data = await contractSigningClient.query(caseNo);
      if (data.case_no !== caseNo || !data[expectedStatus]) {
        throw new Error('客戶契約回讀尚未觀察到本次操作結果。');
      }
      if (!mounted.current) return;
      setReadState({ status: 'ready', data });
      setOperation({ status: 'success', message: successMessage });
      onObserved?.();
    } catch (error) {
      setOperation({ status: 'error', message: errorMessage(error) });
    }
  };

  const signing = readState.status === 'ready' ? readState.data : null;
  const documentVersion = signing === null ? null : generatedClientDocumentVersion(signing);

  return (
    <section aria-label={`案件 ${caseNo} 客戶契約`}>
      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={() => void loadStatus()}
        disabled={readState.status === 'loading'}
      >
        {readState.status === 'loading' ? '讀取客戶契約狀態中…' : '讀取客戶契約狀態'}
      </button>

      {readState.status === 'error' && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>客戶契約狀態不可用</strong>
          <span>{readState.message}</span>
        </div>
      )}

      {signing !== null && (
        <dl className="order-v2-business-summary" aria-label="客戶契約正式狀態">
          <div><dt>服務承諾</dt><dd>{signing.commitment_id === null ? '尚未建立' : `#${signing.commitment_id}`}</dd></div>
          <div><dt>契約文件</dt><dd>{documentVersion === null ? '尚未產生' : `版本 #${documentVersion}`}</dd></div>
          <div><dt>寄送狀態</dt><dd>{signing.client_document_sent ? '已建立寄送工作' : '尚未寄送'}</dd></div>
          <div><dt>簽回狀態</dt><dd>{signing.client_signed_received ? '已簽回' : '尚未簽回'}</dd></div>
        </dl>
      )}

      {signing !== null && signing.commitment_id === null && !signing.client_signed_received && (
        <div className="order-v2-notice blocked" role="status">
          <strong>尚無有效服務承諾</strong>
          <span>Contract Signing owner 尚未回傳 commitment，不能建立客戶契約寄送工作。</span>
        </div>
      )}

      {signing !== null && signing.commitment_id !== null && !signing.client_document_sent && !signing.client_signed_received && (
        <>
          <label>
            客戶契約受控 HTTPS 文件下載網址
            <input
              type="url"
              value={downloadUrl}
              disabled={operation.status === 'working'}
              onChange={(event) => {
                setDownloadUrl(event.target.value);
                resetIntent('send');
              }}
            />
          </label>
          <button
            type="button"
            className="order-v2-open-drawer"
            disabled={operation.status === 'working' || !isHttpsUrl(downloadUrl)}
            onClick={() => void runOperation(
              () => contractSigningMutationClient.sendClient(
                caseNo,
                downloadUrl,
                currentIntent('send'),
              ),
              '客戶契約寄送工作已建立，並已回讀最新狀態。',
              'client_document_sent',
            )}
          >
            建立客戶契約寄送工作
          </button>
        </>
      )}

      {signing !== null && signing.client_document_sent && !signing.client_signed_received && (
        <>
          <label>
            客戶簽回檔
            <input
              type="file"
              accept=".pdf,.xlsx,.xls,.doc,.docx,image/*"
              disabled={operation.status === 'working'}
              onChange={(event) => {
                setSignedFile(event.target.files?.item(0) ?? null);
                resetIntent('return');
              }}
            />
          </label>
          <button
            type="button"
            className="order-v2-open-drawer"
            disabled={operation.status === 'working' || signedFile === null || documentVersion === null}
            onClick={() => void runOperation(
              () => contractSigningMutationClient.uploadClientSignedReturn(
                caseNo,
                signedFile!,
                documentVersion!,
                currentIntent('return'),
              ),
              '客戶契約簽回已記錄，並已回讀最新狀態。',
              'client_signed_received',
            )}
          >
            記錄客戶契約簽回
          </button>
        </>
      )}

      {operation.status === 'success' && <p role="status">{operation.message}</p>}
      {operation.status === 'error' && <p role="alert">{operation.message}</p>}
    </section>
  );
};

export default OrderClientContractPanel;