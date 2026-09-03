import { useRef, useState, type FC } from 'react';
import {
  contractSigningClient,
  type ContractSigningStatus,
} from '../api/orders/contract_signing_client';
import {
  contractSigningMutationClient,
  type ContractCommandOptions,
} from '../api/orders/contract_signing_mutation_client';

interface OrderCaregiverContractPanelProps {
  caseNo: string;
}

type ReadState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: ContractSigningStatus }
  | { status: 'error'; message: string };

type SegmentOperationState =
  | { status: 'idle' }
  | { status: 'working' }
  | { status: 'success'; message: string }
  | { status: 'error'; message: string };

type Intent = Pick<ContractCommandOptions, 'idempotencyKey' | 'correlationId'>;

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '月嫂契約操作失敗';
}

function identity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function generatedDocumentVersion(signing: ContractSigningStatus, segmentId: number): number | null {
  const targetKey = `staff-segment:${segmentId}`;
  const documents = signing.documents
    .filter((document) => (
      document.scope === 'staff_segment'
      && document.target_key === targetKey
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

export const OrderCaregiverContractPanel: FC<OrderCaregiverContractPanelProps> = ({ caseNo }) => {
  const intents = useRef(new Map<string, Intent>());
  const [readState, setReadState] = useState<ReadState>({ status: 'idle' });
  const [downloadUrls, setDownloadUrls] = useState<Record<number, string>>({});
  const [signedFiles, setSignedFiles] = useState<Record<number, File | null>>({});
  const [operations, setOperations] = useState<Record<number, SegmentOperationState>>({});

  const currentIntent = (key: string): Intent => {
    const existing = intents.current.get(key);
    if (existing) return existing;
    const next = {
      idempotencyKey: identity(`beta-caregiver-contract-${key}-idem`),
      correlationId: identity(`beta-caregiver-contract-${key}-corr`),
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

  const runSegmentOperation = async (
    segmentId: number,
    operation: () => Promise<unknown>,
    successMessage: string,
  ) => {
    setOperations((current) => ({ ...current, [segmentId]: { status: 'working' } }));
    try {
      await operation();
      const data = await contractSigningClient.query(caseNo);
      setReadState({ status: 'ready', data });
      setOperations((current) => ({
        ...current,
        [segmentId]: { status: 'success', message: successMessage },
      }));
    } catch (error) {
      setOperations((current) => ({
        ...current,
        [segmentId]: { status: 'error', message: errorMessage(error) },
      }));
    }
  };

  return (
    <section aria-label={`案件 ${caseNo} 月嫂契約`}>
      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={() => void loadStatus()}
        disabled={readState.status === 'loading'}
      >
        {readState.status === 'loading' ? '讀取月嫂契約狀態中…' : '讀取月嫂契約狀態'}
      </button>

      {readState.status === 'error' && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>月嫂契約狀態不可用</strong>
          <span>{readState.message}</span>
        </div>
      )}

      {readState.status === 'ready' && readState.data.staff_segments.length === 0 && (
        <div className="order-v2-notice blocked" role="status">
          <strong>尚無正式月嫂契約分段</strong>
          <span>目前 Contract Signing owner 沒有 server 回傳的月嫂分段。</span>
        </div>
      )}

      {readState.status === 'ready' && readState.data.staff_segments.length > 0 && (
        <div className="order-v2-business-summary" aria-label="月嫂契約正式狀態">
          {readState.data.staff_segments.map((segment) => {
            const operation = operations[segment.segment_id] ?? { status: 'idle' as const };
            const documentVersion = generatedDocumentVersion(readState.data, segment.segment_id);
            const downloadUrl = downloadUrls[segment.segment_id] ?? '';
            const signedFile = signedFiles[segment.segment_id] ?? null;
            const sendIntentKey = `send-${segment.segment_id}`;
            const returnIntentKey = `return-${segment.segment_id}`;
            return (
              <div key={segment.segment_id}>
                <dt>月嫂 #{segment.staff_id} · 分段 #{segment.segment_id}</dt>
                <dd>契約文件：{documentVersion === null ? '尚未產生' : `版本 #${documentVersion}`}</dd>
                <dd>寄送狀態：{segment.sent ? '已建立寄送工作' : '尚未寄送'}</dd>
                <dd>簽回狀態：{segment.signed_received ? '已簽回' : '尚未簽回'}</dd>

                {!segment.sent && !segment.signed_received && (
                  <>
                    <label>
                      受控 HTTPS 文件下載網址
                      <input
                        type="url"
                        value={downloadUrl}
                        disabled={operation.status === 'working'}
                        onChange={(event) => {
                          setDownloadUrls((current) => ({
                            ...current,
                            [segment.segment_id]: event.target.value,
                          }));
                          resetIntent(sendIntentKey);
                        }}
                      />
                    </label>
                    <button
                      type="button"
                      className="order-v2-open-drawer"
                      disabled={operation.status === 'working' || !isHttpsUrl(downloadUrl)}
                      onClick={() => void runSegmentOperation(
                        segment.segment_id,
                        () => contractSigningMutationClient.sendStaff(
                          caseNo,
                          segment.segment_id,
                          downloadUrl,
                          currentIntent(sendIntentKey),
                        ),
                        '月嫂契約寄送工作已建立，並已回讀最新狀態。',
                      )}
                    >
                      建立月嫂契約寄送工作
                    </button>
                  </>
                )}

                {segment.sent && !segment.signed_received && (
                  <>
                    <label>
                      月嫂簽回檔
                      <input
                        type="file"
                        accept=".pdf,.xlsx,.xls,.doc,.docx,image/*"
                        disabled={operation.status === 'working'}
                        onChange={(event) => {
                          setSignedFiles((current) => ({
                            ...current,
                            [segment.segment_id]: event.target.files?.item(0) ?? null,
                          }));
                          resetIntent(returnIntentKey);
                        }}
                      />
                    </label>
                    <button
                      type="button"
                      className="order-v2-open-drawer"
                      disabled={operation.status === 'working' || signedFile === null || documentVersion === null}
                      onClick={() => void runSegmentOperation(
                        segment.segment_id,
                        () => contractSigningMutationClient.uploadStaffSignedReturn(
                          caseNo,
                          segment.segment_id,
                          signedFile!,
                          documentVersion!,
                          currentIntent(returnIntentKey),
                        ),
                        '月嫂契約簽回已記錄，並已回讀最新狀態。',
                      )}
                    >
                      記錄月嫂契約簽回
                    </button>
                  </>
                )}

                {operation.status === 'success' && <p role="status">{operation.message}</p>}
                {operation.status === 'error' && <p role="alert">{operation.message}</p>}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};

export default OrderCaregiverContractPanel;
