/** Operational readback for real Knowledge questions, outcomes, and knowledge gaps. */
import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CircleHelp, RefreshCw, ThumbsDown, ThumbsUp } from 'lucide-react';
import { sessionClient } from '../../api/auth/session_client';

type QuestionStatus = 'pending' | 'processing' | 'answered' | 'unsupported' | 'failed';
type FeedbackOutcome = 'resolved' | 'unresolved' | null;
type QuestionDisplayStatus = QuestionStatus | 'awaiting_feedback' | 'needs_improvement';

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
  feedback_outcome: FeedbackOutcome;
  failure_code: string | null;
}

interface FeedbackAggregate {
  resolved_count: number;
  unresolved_count: number;
  total_count: number;
  resolved_rate: number | null;
}

const statusLabels: Record<QuestionDisplayStatus, string> = {
  pending: '等待處理',
  processing: '處理中',
  answered: '已回答',
  awaiting_feedback: '等待用戶回饋',
  needs_improvement: '待補強',
  unsupported: '未提供答案',
  failed: '系統異常',
};

function displayStatus(item: QuestionObservation): QuestionDisplayStatus {
  if (item.feedback_outcome === 'resolved') return 'answered';
  if (item.feedback_outcome === 'unresolved') return 'needs_improvement';
  if (item.request_status === 'answered') return 'awaiting_feedback';
  return item.request_status;
}

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
  const [filter, setFilter] = useState<'all' | 'awaiting' | 'gap' | 'answered' | 'unsupported' | 'failed'>('all');
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
    awaiting: questions.filter((item) => displayStatus(item) === 'awaiting_feedback').length,
    answered: questions.filter((item) => displayStatus(item) === 'answered').length,
    gaps: questions.filter((item) => displayStatus(item) === 'needs_improvement').length,
    unsupported: questions.filter((item) => displayStatus(item) === 'unsupported').length,
    failed: questions.filter((item) => displayStatus(item) === 'failed').length,
  }), [questions]);

  const visibleQuestions = useMemo(() => questions.filter((item) => {
    const status = displayStatus(item);
    if (filter === 'awaiting') return status === 'awaiting_feedback';
    if (filter === 'gap') return status === 'needs_improvement';
    if (filter === 'answered') return status === 'answered';
    if (filter === 'unsupported') return status === 'unsupported';
    if (filter === 'failed') return status === 'failed';
    return true;
  }), [filter, questions]);

  return (
    <div className="knowledge-feedback-panel">
      <div className="ai-editor-card">
        <div className="ai-editor-header">
          <div>
            <h2><CircleHelp aria-hidden="true" />AI 客服回饋與知識補強</h2>
            <p className="knowledge-feedback-intro">查看民眾實際提問與回答結果；「已回答」與「待補強」只依用戶對該次回答的回饋判定。</p>
          </div>
          <button type="button" className="line-secondary-btn" disabled={loading} onClick={() => void load()}><RefreshCw aria-hidden="true" />重新整理</button>
        </div>

        {notice && <div className="line-warning" role="status">{notice}</div>}
        <div className="ai-feedback-grid knowledge-feedback-metrics">
          <div className="ai-feedback-metric"><span>實際問題</span><strong>{questions.length}</strong></div>
          <div className="ai-feedback-metric"><span>等待用戶回饋</span><strong>{counts.awaiting}</strong></div>
          <div className="ai-feedback-metric is-positive"><span>已回答</span><strong>{counts.answered}</strong></div>
          <div className="ai-feedback-metric is-negative"><span><AlertTriangle aria-hidden="true" />待補強</span><strong>{counts.gaps}</strong></div>
          <div className="ai-feedback-metric"><span>未提供答案</span><strong>{counts.unsupported}</strong></div>
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
              <option value="awaiting">等待用戶回饋</option>
              <option value="gap">待補強</option>
              <option value="answered">已回答</option>
              <option value="unsupported">未提供答案</option>
              <option value="failed">系統異常</option>
            </select>
          </label>
        </div>

        <div className="knowledge-question-list">
          {visibleQuestions.map((item) => {
            const status = displayStatus(item);
            return (
            <article key={item.id} className={`knowledge-question-card is-${status}`}>
              <div className="knowledge-question-heading">
                <strong>{item.question}</strong>
                <span className={`qa-lifecycle-badge is-${status}`}>{statusLabels[status]}</span>
              </div>
              <div className="knowledge-question-meta">
                <span>{new Date(item.created_at_utc).toLocaleString('zh-TW')}</span>
                {qaIdentity(item.source_identity) && <span>命中題目：{qaIdentity(item.source_identity)} v{item.source_version}</span>}
              </div>
              {item.answer_text && <p className="knowledge-question-answer">{item.answer_text}</p>}
              {status === 'awaiting_feedback' && <p className="knowledge-feedback-waiting">回答已送出；收到用戶回饋前，不判定為已回答或待補強。</p>}
              {status === 'needs_improvement' && <p className="knowledge-gap-reason">用戶回饋此回答未解決問題，建議檢查命中題目、答案內容或新增知識。</p>}
              {item.request_status === 'unsupported' && <p className="knowledge-gap-reason">題庫中沒有足夠相符的已發布答案；這是系統結果，不是用戶對回答的回饋。</p>}
              {item.request_status === 'failed' && <p className="knowledge-system-failure">處理失敗：{item.failure_code || '原因待查'}；這不會計入知識缺口。</p>}
            </article>
            );
          })}
          {!loading && visibleQuestions.length === 0 && <div className="line-warning" role="status">{questions.length === 0 ? '尚無真實 Knowledge 問答紀錄。' : '目前沒有符合篩選條件的問題。'}</div>}
          {loading && <div className="ai-feedback-loading" role="status">載入問題與回饋中…</div>}
        </div>
      </div>
    </div>
  );
};

export default KnowledgeFeedbackPanel;
