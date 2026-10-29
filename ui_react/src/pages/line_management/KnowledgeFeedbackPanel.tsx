import { applicationFetch } from '../../api/shared/application_fetch';
/** Operational readback for real Knowledge questions, outcomes, and knowledge gaps. */
import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, MessageCircle, Pencil, Plus, RefreshCw, ThumbsDown, ThumbsUp } from 'lucide-react';
import { Drawer } from '../../components/Drawer';
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
  answered: '用戶確認有幫助',
  awaiting_feedback: '等待用戶回饋',
  needs_improvement: '用戶回饋未解決',
  unsupported: '未找到答案',
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

export const KnowledgeFeedbackPanel: React.FC<{
  onOpenQa?: (id: string) => void;
  onCreateQa?: (question: string) => void;
}> = ({ onOpenQa, onCreateQa }) => {
  const [questions, setQuestions] = useState<QuestionObservation[]>([]);
  const [feedback, setFeedback] = useState<FeedbackAggregate | null>(null);
  const [filter, setFilter] = useState<'attention' | 'all' | 'awaiting' | 'gap' | 'answered' | 'unsupported' | 'failed'>('attention');
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedQuestion, setSelectedQuestion] = useState<QuestionObservation | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const requestHeaders = headers();
      const [questionsResponse, feedbackResponse] = await Promise.all([
        applicationFetch('/api/v1/knowledge/questions?limit=200', { headers: requestHeaders, credentials: 'include' }),
        applicationFetch('/api/v1/line/ai-events/feedback/aggregate', { headers: requestHeaders, credentials: 'include' }),
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
    if (filter === 'attention') return ['needs_improvement', 'unsupported', 'failed'].includes(status);
    if (filter === 'awaiting') return status === 'awaiting_feedback';
    if (filter === 'gap') return status === 'needs_improvement';
    if (filter === 'answered') return status === 'answered';
    if (filter === 'unsupported') return status === 'unsupported';
    if (filter === 'failed') return status === 'failed';
    return true;
  }), [filter, questions]);

  const attentionCount = counts.gaps + counts.unsupported + counts.failed;
  const readUnavailable = loading || notice !== null;

  return (
    <div className="knowledge-feedback-panel">
      <div className="studio-feedback-summary">
        <div className="ai-feedback-metric"><span><AlertTriangle aria-hidden="true" />需要查看</span><strong>{readUnavailable ? '—' : attentionCount}</strong><small>含用戶未解決、無答案與系統異常</small></div>
        <div className="ai-feedback-metric"><span><MessageCircle aria-hidden="true" />本次載入提問</span><strong>{readUnavailable ? '—' : questions.length}</strong><small>最多載入 200 筆</small></div>
        <div className="ai-feedback-metric is-positive"><span><ThumbsUp aria-hidden="true" />回饋有幫助</span><strong>{readUnavailable || feedback?.resolved_rate == null ? '—' : `${Math.round(feedback.resolved_rate * 100)}%`}</strong><small>回饋統計 · {readUnavailable ? '—' : feedback?.total_count ?? '—'} 筆回饋</small></div>
      </div>
      <div className="ai-editor-card knowledge-question-section">
        <div className="ai-editor-header"><div><h2>民眾提問與回饋</h2><p className="studio-description">先查看需要處理的問題，再決定補強答案或檢查系統。</p></div><button type="button" className="line-secondary-btn" disabled={loading} onClick={() => void load()}><RefreshCw aria-hidden="true" />重新整理</button></div>
        {notice && <div className="line-warning" role="status">{notice}</div>}
        <div className="studio-feedback-toolbar"><div className="studio-filter-buttons" role="group" aria-label="常用回饋篩選">{([
          ['attention', '需要查看'], ['all', '全部'], ['gap', '用戶未解決'], ['unsupported', '未找到答案'], ['failed', '系統異常'],
        ] as const).map(([value, label]) => <button key={value} type="button" className={filter === value ? 'active' : ''} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div>
          <label><span className="sr-only">篩選結果</span><select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}><option value="attention">需要查看</option><option value="all">全部</option><option value="awaiting">等待用戶回饋</option><option value="gap">用戶回饋未解決</option><option value="answered">用戶確認有幫助</option><option value="unsupported">未找到答案</option><option value="failed">系統異常</option></select></label>
        </div>
        <div className="knowledge-question-list">
          {visibleQuestions.map((item) => {
            const status = displayStatus(item);
            return <article key={item.id} className={`knowledge-question-card studio-feedback-row is-${status}`}><div><strong>{item.question}</strong><p className="studio-description">{new Date(item.created_at_utc).toLocaleString('zh-TW')}</p></div><span className={`qa-lifecycle-badge is-${status}`}>{statusLabels[status]}</span><button type="button" className="studio-text-button" aria-label={`查看提問：${item.question}`} onClick={() => setSelectedQuestion(item)}>查看明細</button></article>;
          })}
          {!loading && !notice && visibleQuestions.length === 0 && <div className="studio-empty" role="status">{questions.length === 0 ? '尚無真實問答紀錄。' : '目前沒有符合篩選條件的問題。'}</div>}
          {loading && <div className="ai-feedback-loading" role="status">載入問題與回饋中…</div>}
        </div>
        <details className="studio-technical"><summary>完整統計與資料範圍</summary><p className="studio-description">提問清單為本次載入資料，最多 200 筆；回饋統計使用後端提供的彙總，範圍可能不同。系統無答案、系統異常及用戶回饋未解決分開計算。</p>
          <div className="ai-feedback-grid knowledge-feedback-metrics">
            <div className="ai-feedback-metric"><span>等待用戶回饋</span><strong>{readUnavailable ? '—' : counts.awaiting}</strong></div><div className="ai-feedback-metric is-positive"><span>用戶確認有幫助</span><strong>{readUnavailable ? '—' : counts.answered}</strong></div><div className="ai-feedback-metric is-negative"><span>用戶回饋未解決</span><strong>{readUnavailable ? '—' : counts.gaps}</strong></div><div className="ai-feedback-metric"><span>未找到答案</span><strong>{readUnavailable ? '—' : counts.unsupported}</strong></div><div className="ai-feedback-metric"><span>系統異常</span><strong>{readUnavailable ? '—' : counts.failed}</strong></div>
          </div>
          <div className="ai-feedback-grid knowledge-feedback-metrics"><div className="ai-feedback-metric"><span>總滿意度回饋</span><strong>{readUnavailable ? '—' : feedback?.total_count ?? '—'}</strong></div><div className="ai-feedback-metric is-positive"><span><ThumbsUp aria-hidden="true" />有幫助</span><strong>{readUnavailable ? '—' : feedback?.resolved_count ?? '—'}</strong></div><div className="ai-feedback-metric is-negative"><span><ThumbsDown aria-hidden="true" />未解決</span><strong>{readUnavailable ? '—' : feedback?.unresolved_count ?? '—'}</strong></div><div className="ai-feedback-metric"><span>滿意度</span><strong>{readUnavailable ? '—' : feedback?.resolved_rate == null ? '尚無回饋' : `${Math.round(feedback.resolved_rate * 100)}%`}</strong></div></div>
        </details>
      </div>
      <Drawer isOpen={selectedQuestion !== null} onClose={() => setSelectedQuestion(null)} title="提問與回答明細" size="normal" closeLabel="關閉提問明細" footer={<div className="line-drawer-footer"><button type="button" className="line-secondary-btn" onClick={() => setSelectedQuestion(null)}>關閉</button>
        {selectedQuestion?.source_identity?.startsWith('line-common-qa:') && onOpenQa && <button type="button" className="line-primary-btn" onClick={() => onOpenQa(qaIdentity(selectedQuestion.source_identity)!)}><Pencil aria-hidden="true" />檢查命中問答</button>}
        {selectedQuestion?.request_status === 'unsupported' && onCreateQa && <button type="button" className="line-primary-btn" onClick={() => onCreateQa(selectedQuestion.question)}><Plus aria-hidden="true" />新增問答草稿</button>}
      </div>}>
        {selectedQuestion && <div className="studio-feedback-detail"><span className={`qa-lifecycle-badge is-${displayStatus(selectedQuestion)}`}>{statusLabels[displayStatus(selectedQuestion)]}</span><p className="studio-description">{new Date(selectedQuestion.created_at_utc).toLocaleString('zh-TW')}</p><h3>民眾提問</h3><p>{selectedQuestion.question}</p><h3>本次回答</h3><p className="studio-answer-text">{selectedQuestion.answer_text || '本次沒有產生答案。'}</p>
          {displayStatus(selectedQuestion) === 'awaiting_feedback' && <p className="knowledge-feedback-waiting">已產生回答；尚未收到用戶回饋，無法判定是否解決問題。</p>}
          {displayStatus(selectedQuestion) === 'needs_improvement' && <p className="knowledge-gap-reason">用戶回饋此回答未解決問題，建議檢查命中題目、答案內容或新增知識。</p>}
          {selectedQuestion.request_status === 'unsupported' && <p className="knowledge-gap-reason">題庫中沒有足夠相符的已發布答案；這是系統結果，不是用戶對回答的回饋。</p>}
          {selectedQuestion.request_status === 'failed' && <p className="knowledge-system-failure">處理失敗：{selectedQuestion.failure_code || '原因待查'}；這不會計入知識缺口。</p>}
          <details className="studio-technical"><summary>命中題目與版本資訊</summary><p>{qaIdentity(selectedQuestion.source_identity) ? `命中題目：${qaIdentity(selectedQuestion.source_identity)} v${selectedQuestion.source_version ?? '—'}` : '沒有命中題目'}</p><p>索引版本：{selectedQuestion.index_version ?? '—'}</p></details>
        </div>}
      </Drawer>
    </div>
  );
};

export default KnowledgeFeedbackPanel;
