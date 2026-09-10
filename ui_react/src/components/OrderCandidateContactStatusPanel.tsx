import { useEffect, useRef, useState, type FC } from 'react';
import {
  candidateContactPoolClient,
  type CandidateContactPool,
  type CandidateWillingnessResult,
  type CandidateInformationPreview,
} from '../api/scheduling/candidate_contact_pool_client';

interface OrderCandidateContactStatusPanelProps {
  caseNo: string;
  onObserved?: () => void;
  onPreviewInformation?: (kind: 1 | 2) => void;
  revision?: number;
}

type ContactStatusState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: CandidateContactPool }
  | { status: 'error'; message: string };

type WillingnessMutationState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'success'; result: CandidateWillingnessResult }
  | { status: 'error'; message: string };

type CandidateContact = CandidateContactPool['candidates'][number];

function CandidateInformationSend({ caseNo, candidateId, kind, onClose, onSent }: {
  caseNo: string; candidateId: number; kind: 1 | 2; onClose: () => void; onSent: () => void;
}) {
  const [preview, setPreview] = useState<CandidateInformationPreview | null>(null);
  const [status, setStatus] = useState('loading');
  const [message, setMessage] = useState('');
  const [eventKey] = useState(() => `candidate-info-${candidateId}-${kind}-${crypto.randomUUID()}`);
  useEffect(() => {
    let current = true;
    candidateContactPoolClient.previewInformation(caseNo, candidateId, kind)
      .then((data) => { if (current) { setPreview(data); setStatus('ready'); } })
      .catch((error) => { if (current) { setMessage(errorMessage(error)); setStatus('error'); } });
    return () => { current = false; };
  }, [caseNo, candidateId, kind]);
  const send = async () => {
    if (!preview || status !== 'ready') return;
    setStatus('sending');
    try {
      await candidateContactPoolClient.sendInformation(caseNo, candidateId, kind, preview.preview_fingerprint, eventKey);
      setStatus('sent');
      setMessage('已排入寄送佇列，尚不代表月嫂已收到。請由聯絡紀錄查看投遞狀態。');
      onSent();
    } catch (error) {
      setStatus('error');
      setMessage(`${errorMessage(error)} 請先重新讀取聯絡紀錄確認結果，不要直接重複寄送。`);
    }
  };
  return <section className="order-case-review-note" aria-label="寄送前確認">
    <h4>寄送訂單資訊－{kind}</h4>
    {status === 'loading' && <p role="status">正在讀取寄送內容…</p>}
    {preview && <><p>收件月嫂：{preview.staff_name}；案件：{preview.case_no}</p><pre style={{ whiteSpace: 'pre-wrap', font: 'inherit' }}>{preview.text}</pre></>}
    {message && <p role={status === 'error' ? 'alert' : 'status'}>{message}</p>}
    <button type="button" disabled={status !== 'ready'} onClick={() => void send()}>{status === 'sending' ? '建立寄送任務中…' : '確認寄送'}</button>
    <button type="button" disabled={status === 'sending'} onClick={onClose}>關閉</button>
  </section>;
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '候選聯絡狀態查詢失敗';
}

function deliveryStatus(
  delivery: CandidateContact['information']['1'] | CandidateContact['information']['2'],
): string {
  if (delivery === null) return '尚無紀錄';
  const labels = { queued: '等待發送', pending: '處理中', sent: '已發送', manually_confirmed: '已人工確認', retryable_failed: '發送未完成', failed: '發送失敗', cancelled: '已取消發送' };
  return `${labels[delivery.status]} · ${delivery.sent_at}`;
}

export const OrderCandidateContactStatusPanel: FC<OrderCandidateContactStatusPanelProps> = ({ caseNo, onObserved, revision = 0 }) => {
  const [state, setState] = useState<ContactStatusState>({ status: 'idle' });
  const [sendPreview, setSendPreview] = useState<{ candidateId: number; kind: 1 | 2 } | null>(null);
  const [reasonDrafts, setReasonDrafts] = useState<Record<number, string>>({});
  const [mutationStates, setMutationStates] = useState<Record<number, WillingnessMutationState>>({});
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    void candidateContactPoolClient.query(caseNo, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setState({ status: 'ready', data }); })
      .catch((error) => { if (!controller.signal.aborted) setState({ status: 'error', message: errorMessage(error) }); });
    return () => controller.abort();
  }, [caseNo, revision]);

  const loadStatus = () => {
    setState({ status: 'loading' });
    void candidateContactPoolClient.query(caseNo)
      .then((data) => setState({ status: 'ready', data }))
      .catch((error) => setState({ status: 'error', message: errorMessage(error) }));
  };

  const recordWillingness = (
    candidateId: number,
    willingness: 'willing' | 'unwilling',
  ) => {
    const currentCandidate = state.status === 'ready'
      ? state.data.candidates.find((candidate) => candidate.id === candidateId)
      : undefined;
    if (currentCandidate?.willingness === willingness) return;

    setMutationStates((current) => ({
      ...current,
      [candidateId]: { status: 'submitting' },
    }));
    void candidateContactPoolClient.recordWillingness(
      caseNo,
      candidateId,
      willingness,
      reasonDrafts[candidateId] ?? '',
    )
      .then(async (result) => {
        const readback = await candidateContactPoolClient.query(caseNo);
        const readbackCandidates = readback.candidates.filter((candidate) => candidate.id === candidateId);
        if (readback.case_no !== caseNo || readbackCandidates.length !== 1 || readbackCandidates[0]!.willingness !== willingness) {
          throw new Error('人工意願回讀與本次寫入不一致。');
        }
        setState({ status: 'ready', data: readback });
        setMutationStates((current) => ({
          ...current,
          [candidateId]: { status: 'success', result },
        }));
        if (mounted.current) onObserved?.();
      })
      .catch((error) => {
        setMutationStates((current) => ({
          ...current,
          [candidateId]: { status: 'error', message: errorMessage(error) },
        }));
      });
  };

  return (
    <section className="order-candidate-list" aria-label={`案件 ${caseNo} 候選聯絡狀態`}>
      <header className="order-candidate-list-heading"><div><h3>候選月嫂</h3><p>人選、聯絡紀錄與回覆集中在這裡，不必切換不同候選池。</p></div>
      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={loadStatus}
        disabled={state.status === 'loading' || sendPreview !== null}
      >
        {state.status === 'loading' ? '讀取中…' : '重新讀取候選清單'}
      </button>
      </header>
      {state.status === 'idle' && <div className="order-case-empty"><h4>查看已加入的人選</h4><p>讀取候選清單以查看意願與聯絡紀錄；要加入人選，請切換「新增候選月嫂」。</p></div>}

      {state.status === 'error' && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>候選聯絡狀態不可用</strong>
          <span>{state.message}</span>
        </div>
      )}

      {state.status === 'ready' && state.data.candidates.length === 0 && (
        <div className="order-v2-notice blocked" role="status">
          <strong>尚未加入候選月嫂</strong>
          <span>請先從「新增候選月嫂」查詢並選擇人選。</span>
        </div>
      )}

      {state.status === 'ready' && state.data.candidates.length > 0 && (
        <>
          <div className="order-v2-case-meta">
            <span>共 {state.data.candidates.length} 位人選</span>
          </div>
          <div className="order-candidate-cards" aria-label="候選聯絡正式狀態">
            {state.data.candidates.map((candidate) => {
              const mutationState = mutationStates[candidate.id] ?? { status: 'idle' as const };
              const submitting = mutationState.status === 'submitting';
              return (
                <article className="order-candidate-card" key={candidate.id}>
                  <header><h4>{candidate.staff_name}</h4><span className={`order-candidate-willingness ${candidate.willingness}`}>{candidate.status === 'withdrawn' ? '已退出' : candidate.status === 'selected' ? '已選定' : ({ pending: '待回覆', willing: '願意承接', unwilling: '不願承接' })[candidate.willingness]}</span></header>
                  <p>{candidate.service_start_date} ～ {candidate.service_end_date}</p>
                  {candidate.reason && <p>回覆說明：{candidate.reason}</p>}
                  <dl className="order-candidate-delivery"><div><dt>訂單資訊－1</dt><dd>{deliveryStatus(candidate.information['1'])}</dd></div><div><dt>訂單資訊－2</dt><dd>{deliveryStatus(candidate.information['2'])}</dd></div></dl>
                  <div className="order-case-action-row">
                    <button type="button" disabled={candidate.status !== 'active' || sendPreview !== null} onClick={() => setSendPreview({ candidateId: candidate.id, kind: 1 })}>寄送訂單資訊－1</button>
                    <button type="button" disabled={candidate.status !== 'active' || sendPreview !== null} onClick={() => setSendPreview({ candidateId: candidate.id, kind: 2 })}>寄送訂單資訊－2</button>
                  </div>
                  {sendPreview?.candidateId === candidate.id && <CandidateInformationSend
                    key={`${caseNo}:${candidate.id}:${sendPreview.kind}`} caseNo={caseNo} candidateId={candidate.id} kind={sendPreview.kind}
                    onClose={() => setSendPreview(null)} onSent={() => { setSendPreview(null); loadStatus(); onObserved?.(); }} />}
                  <details>
                    <summary>記錄電話或現場詢問結果</summary>
                    <label htmlFor={`candidate-${candidate.id}-willingness-reason`}>
                      詢問結果備註（{candidate.staff_name}）
                    </label>
                    <input
                      id={`candidate-${candidate.id}-willingness-reason`}
                      value={reasonDrafts[candidate.id] ?? ''}
                      maxLength={500}
                      onChange={(event) => setReasonDrafts((current) => ({
                        ...current,
                        [candidate.id]: event.target.value,
                      }))}
                      placeholder="無意願時必填；願意可留空"
                    />
                    <div className="order-case-action-row">
                      <button
                        type="button"
                        className="order-v2-open-drawer"
                        aria-label={`記錄 ${candidate.staff_name} 願意`}
                        disabled={submitting || candidate.status !== 'active' || candidate.willingness === 'willing'}
                        onClick={() => recordWillingness(candidate.id, 'willing')}
                      >
                        記錄願意
                      </button>
                      <button
                        type="button"
                        className="order-v2-open-drawer"
                        aria-label={`記錄 ${candidate.staff_name} 無意願`}
                        disabled={submitting || candidate.status !== 'active' || candidate.willingness === 'unwilling'}
                        onClick={() => recordWillingness(candidate.id, 'unwilling')}
                      >
                        記錄無意願
                      </button>
                    </div>
                    {mutationState.status === 'submitting' && <p role="status">記錄人工意願中…</p>}
                    {mutationState.status === 'success' && (
                      <p role="status">
                        已記錄意願並重新確認。
                      </p>
                    )}
                    {mutationState.status === 'error' && (
                      <p className="order-v2-drawer-error" role="alert">{mutationState.message}</p>
                    )}
                  </details>
                </article>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
};

export default OrderCandidateContactStatusPanel;
