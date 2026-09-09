/** Operational readback for real Knowledge questions, outcomes, and knowledge gaps. */
import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CircleHelp, RefreshCw, ThumbsDown, ThumbsUp } from 'lucide-react';
import { sessionClient } from '../../api/auth/session_client';

type QuestionStatus = 'pending' | 'processing' | 'answered' | 'unsupported' | 'failed';

interface QuestionObservation {
  id: number;
  question: string;
  request_status: QuestionStatus;
  created_at_utc: string;
  completed_at_utc: string | null;
  answer_text: string | null;
  index_version: number | null;
  source_identity: string | null;
  source_version: number | null;
  failure_code: string | null;
}

interface FeedbackAggregate {
  resolved_count: number;
  unresolved_count: number;
  total_count: number;
  resolved_rate: number | null;
}

const statusLabels: Record<QuestionStatus, string> = {
  pending: '等待處理',
  processing: '處理中',
  answered: '已回答',
  unsupported: '待補強知識',
  failed: '系統異常',
};

function headers(): Record<string, string> {
  const result: Record<string, string> = {};
  const token = sessionClient.getToken();
  if (token) result.Authorization = `Bearer ${token}`;
  return result;
}

function qaIdentity(sourceIdentity: string | null): string | null {
  if (!sourceIdentity) return null;
  return sourceIdentity.startsWith('line-common-qa:')
    ? sourceIdentity.slice('line-common-qa:'.length)
    : sourceIdentity;
}

export const KnowledgeFeedbackPanel: React.FC = () => {
  const [questions, setQuestions] = useState<QuestionObservation[]>([]);
  const [feedback, setFeedback] = useState<FeedbackAggregate | null>(null);
  const [filter, setFilter] = useState<'all' | 'gap' | 'answered' | 'failed'>('all');
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const requestHeaders = headers();
      const [questionsResponse, feedbackResponse] = await Promise.all([
        fetch('/api/v1/knowledge/questions?limit=200', { headers: requestHeaders, credentials: 'include' }),
        fetch('/api/v1/line/ai-events/feedback/aggregate', { headers: requestHeaders, credentials: 'include' }),
      ]);
      if (!questionsResponse.ok || !feedbackResponse.ok) throw new Error('feedback_observation_read_failed');
      const questionRows = await questionsResponse.json() as QuestionObservation[];
      const feedbackEnvelope = await feedbackResponse.json() as { data?: FeedbackAggregate };
      if (!feedbackEnvelope.data) throw new Error('feedback_aggregate_missing');
      setQuestions(questionRows);
      setFeedback(feedbackEnvelope.data);
      setNotice(null);
    } catch {
      setNotice('無法讀取 AI 客服回饋與問題觀測，請稍後重試。');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const counts = useMemo(() => ({
    answered: questions.filter((item) => item.request_status === 'answered').length,
    gaps: questions.filter((item) => item.request_status === 'unsupported').length,
    failed: questions.filter((item) => item.request_status === 'failed').length,
  }), [questions]);

  const visibleQuestions = useMemo(() => questions.filter((item) => {
    if (filter === 'gap') return item.request_status === 'unsupported';
    if (filter === 'answered') return item.request_status === 'answered';
    if (filter === 'failed') return item.request_status === 'failed';
    return true;
  }), [filter, questions]);

  return (
    <div className="knowledge-feedback-panel">
      <div className="ai-editor-card">
        <div className="ai-editor-header">
          <div>
            <h2><CircleHelp aria-hidden="true" />AI 客服回饋與知識補強</h2>
            <p className="knowledge-feedback-intro">查看民眾實際提問與回答結果；只有「待補強知識」代表題庫沒有足夠的核准答案。</p>
          </div>
          <button type="button" className="line-secondary-btn" disabled={loading} onClick={() => void load()}><RefreshCw aria-hidden="true" />重新整理</button>
        </div>

        {notice && <div className="line-warning" role="status">{notice}</div>}
        <div className="ai-feedback-grid knowledge-feedback-metrics">
          <div className="ai-feedback-metric"><span>實際問題</span><strong>{questions.length}</strong></div>
          <div className="ai-feedback-metric is-positive"><span>已回答</span><strong>{counts.answered}</strong></div>
          <div className="ai-feedback-metric is-negative"><span><AlertTriangle aria-hidden="true" />待補強知識</span><strong>{counts.gaps}</strong></div>
          <div className="ai-feedback-metric"><span>系統異常</span><strong>{counts.failed}</strong></div>
        </div>

        <div className="ai-feedback-grid knowledge-feedback-metrics">
          <div className="ai-feedback-metric"><span>總滿意度回饋</span><strong>{feedback?.total_count ?? '—'}</strong></div>
          <div className="ai-feedback-metric is-positive"><span><ThumbsUp aria-hidden="true" />有幫助</span><strong>{feedback?.resolved_count ?? '—'}</strong></div>
          <div className="ai-feedback-metric is-negative"><span><ThumbsDown aria-hidden="true" />未解決</span><strong>{feedback?.unresolved_count ?? '—'}</strong></div>
          <div className="ai-feedback-metric is-rate"><span>滿意度</span><strong>{feedback?.resolved_rate == null ? '尚無回饋' : `${Math.round(feedback.resolved_rate * 100)}%`}</strong></div>
        </div>
      </div>

      <div className="ai-editor-card knowledge-question-section">
        <div className="knowledge-question-toolbar">
          <h3>民眾實際提問</h3>
          <label>篩選結果
            <select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}>
              <option value="all">全部</option>
              <option value="gap">待補強知識</option>
              <option value="answered">已回答</option>
              <option value="failed">系統異常</option>
            </select>
          </label>
        </div>

        <div className="knowledge-question-list">
          {visibleQuestions.map((item) => (
            <article key={item.id} className={`knowledge-question-card is-${item.request_status}`}>
              <div className="knowledge-question-heading">
                <strong>{item.question}</strong>
                <span className={`qa-lifecycle-badge is-${item.request_status}`}>{statusLabels[item.request_status]}</span>
              </div>
              <div className="knowledge-question-meta">
                <span>{new Date(item.created_at_utc).toLocaleString('zh-TW')}</span>
                {qaIdentity(item.source_identity) && <span>命中題目：{qaIdentity(item.source_identity)} v{item.source_version}</span>}
              </div>
              {item.answer_text && <p className="knowledge-question-answer">{item.answer_text}</p>}
              {item.request_status === 'unsupported' && <p className="knowledge-gap-reason">題庫中沒有足夠相符的已發布答案，建議整理成新 QA 或補強現有題目。</p>}
              {item.request_status === 'failed' && <p className="knowledge-system-failure">處理失敗：{item.failure_code || '原因待查'}；這不會計入知識缺口。</p>}
            </article>
          ))}
          {!loading && visibleQuestions.length === 0 && <div className="line-warning" role="status">{questions.length === 0 ? '尚無真實 Knowledge 問答紀錄。' : '目前沒有符合篩選條件的問題。'}</div>}
          {loading && <div className="ai-feedback-loading" role="status">載入問題與回饋中…</div>}
        </div>
      </div>
    </div>
  );
};

export default KnowledgeFeedbackPanel;
