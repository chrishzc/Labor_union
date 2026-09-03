import { useState, type FC } from 'react';
import {
  candidateContactPoolClient,
  type CandidateContactPool,
} from '../api/scheduling/candidate_contact_pool_client';

interface OrderCandidateContactStatusPanelProps {
  caseNo: string;
}

type ContactStatusState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: CandidateContactPool }
  | { status: 'error'; message: string };

type CandidateContact = CandidateContactPool['candidates'][number];

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '候選聯絡狀態查詢失敗';
}

function deliveryStatus(
  delivery: CandidateContact['information']['1'] | CandidateContact['information']['2'],
): string {
  if (delivery === null) return '尚無紀錄';
  return `${delivery.status} · ${delivery.sent_at}`;
}

export const OrderCandidateContactStatusPanel: FC<OrderCandidateContactStatusPanelProps> = ({ caseNo }) => {
  const [state, setState] = useState<ContactStatusState>({ status: 'idle' });

  const loadStatus = () => {
    setState({ status: 'loading' });
    void candidateContactPoolClient.query(caseNo)
      .then((data) => setState({ status: 'ready', data }))
      .catch((error) => setState({ status: 'error', message: errorMessage(error) }));
  };

  return (
    <section aria-label={`案件 ${caseNo} 候選聯絡狀態`}>
      <button
        type="button"
        className="order-v2-open-drawer"
        onClick={loadStatus}
        disabled={state.status === 'loading'}
      >
        {state.status === 'loading' ? '讀取候選聯絡狀態中…' : '讀取候選聯絡狀態'}
      </button>

      {state.status === 'error' && (
        <div className="order-v2-notice blocked" role="alert">
          <strong>候選聯絡狀態不可用</strong>
          <span>{state.message}</span>
        </div>
      )}

      {state.status === 'ready' && state.data.candidates.length === 0 && (
        <div className="order-v2-notice blocked" role="status">
          <strong>候選聯絡池為空</strong>
          <span>目前沒有 server 回傳的候選聯絡紀錄。</span>
        </div>
      )}

      {state.status === 'ready' && state.data.candidates.length > 0 && (
        <>
          <div className="order-v2-case-meta">
            <span>Pool：{state.data.pool_id === null ? '尚未建立' : `#${state.data.pool_id}`}</span>
            <span>候選：{state.data.candidates.length}</span>
          </div>
          <div className="order-v2-business-summary" aria-label="候選聯絡正式狀態">
            {state.data.candidates.map((candidate) => (
              <div key={candidate.id}>
                <dt>{candidate.staff_name} · 月嫂 #{candidate.staff_id}</dt>
                <dd>候選狀態：{candidate.status}</dd>
                <dd>回覆／意願：{candidate.willingness}</dd>
                <dd>回覆原因：{candidate.reason ?? '—'}</dd>
                <dd>聯絡資訊 1：{deliveryStatus(candidate.information['1'])}</dd>
                <dd>聯絡資訊 2：{deliveryStatus(candidate.information['2'])}</dd>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
};

export default OrderCandidateContactStatusPanel;
