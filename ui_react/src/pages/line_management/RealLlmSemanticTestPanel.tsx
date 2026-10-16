/**
 * File: RealLlmSemanticTestPanel.tsx
 * Description: 管理端真實 M2 語意測試；只由後端使用已儲存 Gemini secret，不發送 LINE 或建立工單。
 */
import React, { useEffect, useState } from 'react';
import { CircleHelp, Pencil, Plus, Send } from 'lucide-react';
import { sessionClient } from '../../api/auth/session_client';
import {
  testLlmSemantics,
  type LlmSemanticTest,
} from '../../api/system/llm_configuration_client';
import {
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../../api/shared/typed_errors';


function safeErrorMessage(error: unknown): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return '管理員 Session 已失效，請重新登入。';
    if (error.status === 403) return '目前帳號沒有 AI 模型測試權限。';
    if (error.status === 404) return '後端尚未載入 Gemini 語意測試 API，請重新啟動 FastAPI。';
    return `Gemini 語意測試失敗（HTTP ${error.status} / ${error.code}）。`;
  }
  if (error instanceof ApiTimeoutError) return 'Gemini 語意測試逾時。';
  if (error instanceof ApiNetworkError) return '無法連線到後端 API。';
  return 'Gemini 語意測試失敗。';
}

function resultMessage(result: LlmSemanticTest): string {
  if (result.outcome === 'answered') return '已找到核准答案。';
  if (result.outcome === 'unsupported') return '未找到足夠相符的核准答案，請檢查問法或補強問答。';
  if (result.code === 'knowledge_index_unavailable') return '問答搜尋資料尚未就緒，請先至常見問答更新。';
  if (result.code === 'knowledge_index_read_failed') return '目前無法讀取問答搜尋資料，請稍後重試。';
  if (result.code === 'not_configured') return 'Gemini API Key 尚未設定。';
  if (result.code === 'authentication_failed') return 'Gemini API Key 驗證失敗。';
  if (result.code === 'rate_limited') return 'Gemini Free Tier 目前達到配額或速率限制。';
  if (result.code === 'model_unavailable') return '目前設定的 Gemini 模型不可用。';
  if (result.code === 'timeout') return 'Gemini 請求逾時。';
  if (result.code === 'unavailable') return '目前無法連線到 Google Gemini API。';
  return `本次測試未產生答案（${result.code ?? result.outcome}）。`;
}

export const RealLlmSemanticTestPanel: React.FC<{
  onOpenQa?: (id: string) => void;
  onCreateQa?: (question: string) => void;
}> = ({ onOpenQa, onCreateQa }) => {
  const [question, setQuestion] = useState('');
  const [quickQuestions, setQuickQuestions] = useState<string[]>([]);
  const [catalogNotice, setCatalogNotice] = useState<string | null>(null);
  const [result, setResult] = useState<LlmSemanticTest | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [testedQuestion, setTestedQuestion] = useState('');

  useEffect(() => {
    const headers: Record<string, string> = {};
    const token = sessionClient.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    void fetch('/api/v1/knowledge/items?limit=100&lifecycle_status=published', {
      headers,
      credentials: 'include',
    }).then(async (response) => {
      if (!response.ok) throw new Error('published_knowledge_read_failed');
      const items = await response.json() as Array<{ content: string }>;
      const publishedQuestions = items.flatMap((item) => {
        try {
          const content = JSON.parse(item.content) as { schema?: string; question?: string; answer?: string };
          return content.schema === 'line.common_qa.v1' && content.question?.trim() && content.answer?.trim()
            ? [content.question.trim()]
            : [];
        } catch {
          return [];
        }
      });
      setQuickQuestions(publishedQuestions);
      setQuestion((current) => current || publishedQuestions[0] || '');
      setCatalogNotice(publishedQuestions.length === 0 ? '目前沒有已發布的問答，請先儲存草稿、發布並完成搜尋資料更新。' : null);
    }).catch(() => {
      setCatalogNotice('無法讀取已發布的 Knowledge QA，不提供可能失敗的快捷測試題。');
    });
  }, []);

  const run = async () => {
    const normalized = question.trim();
    if (running || !normalized) return;
    setTestedQuestion(normalized);
    setFeedbackStatus(null);
    setRunning(true);
    setResult(null);
    setNotice(null);
    try {
      const next = await testLlmSemantics(normalized);
      setResult(next);
      setNotice(resultMessage(next));
    } catch (error: unknown) {
      setNotice(safeErrorMessage(error));
    } finally {
      setRunning(false);
    }
  };

  const [feedbackStatus, setFeedbackStatus] = useState<{ state: 'submitting' | 'success' | 'error'; message: string } | null>(null);

  const handleFeedback = async (choice: 'helpful' | 'unresolved') => {
    setFeedbackStatus({ state: 'submitting', message: '正在送出回覆滿意度…' });
    try {
      const response = await fetch('/api/v1/line/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_response_id: `m2-test-${result?.qa_id || Date.now()}`,
          outcome: choice === 'helpful' ? 'resolved' : 'unresolved',
          response_revision: 1,
          catalog_revision: 1,
          idempotency_key: `m2-test-feedback:${Date.now()}:${choice}`,
          correlation_id: `m2-test-feedback:${Date.now()}`,
          development_line_user_id: import.meta.env.VITE_LINE_DEVELOPMENT_USER_ID || 'U99c2e4a3629eb284d19ab0491d356839',
        }),
      });
      if (!response.ok) throw new Error(`feedback_http_${response.status}`);
      setFeedbackStatus({
        state: 'success',
        message: choice === 'helpful'
          ? '感謝回饋，已記錄為有效解答。'
          : '已記錄為未解決，後續處理狀態請至客服工單確認。',
      });
    } catch {
      setFeedbackStatus({ state: 'error', message: '回饋尚未送出，請確認連線後再試一次。' });
    }
  };

  return (
    <div className="ai-editor-card real-llm-panel">
      <div className="studio-test-content">
        <div className="ai-editor-header real-llm-header"><h2>試試客服怎麼回答</h2><span className="studio-muted-badge">真實 AI 測試</span></div>
        <p className="studio-description">輸入民眾可能提出的問題，檢視答案是否清楚、合適。</p>
        <label className="studio-field-label" htmlFor="semantic-test-question">測試問題</label>
        <textarea id="semantic-test-question" aria-label="測試問題" placeholder="請從已發布題目選擇，或輸入民眾的測試提問" value={question} disabled={running} onChange={(event) => setQuestion(event.target.value)} rows={4} className="real-llm-input" />
        <div className="studio-test-actions"><p className="studio-description"><CircleHelp aria-hidden="true" />使用目前模型設定與核准知識庫；執行會呼叫 AI，不代表 LINE 已送達。</p><button type="button" className="line-primary-btn" onClick={() => void run()} disabled={running || !question.trim()}><Send aria-hidden="true" />{running ? '測試中…' : '測試回答'}</button></div>
        <div className="real-llm-quick-section"><small className="real-llm-quick-label">快速試試</small><div className="real-llm-quick-list">{quickQuestions.slice(0, 3).map((q) => <button key={q} type="button" disabled={running} onClick={() => setQuestion(q)} className="real-llm-quick-button">{q}</button>)}</div>
          {quickQuestions.length > 3 && <details className="studio-example-picker"><summary>選擇其他已發布題目（{quickQuestions.length} 題）</summary><label htmlFor="semantic-example" className="sr-only">選擇已發布題目</label><select id="semantic-example" value="" disabled={running} onChange={(event) => { if (event.target.value) setQuestion(event.target.value); }}><option value="">選擇一個問題</option>{quickQuestions.map((q) => <option key={q} value={q}>{q}</option>)}</select></details>}
          {catalogNotice && <div className="line-warning line-block-spacing-12" role="status">{catalogNotice}</div>}
        </div>
        {running && <p className="studio-test-pending" role="status">正在測試回答，請稍候…</p>}
        {notice && <section className={`studio-test-result ${result?.outcome === 'answered' ? 'is-answered' : 'is-warning'}`} aria-label="回答測試結果">
          <header className="studio-result-heading">
            <h3>測試結果</h3>
            <p className="studio-result-status" role="status">{notice}</p>
          </header>
          <div className="studio-tested-question"><h4>本次問題</h4><p>{testedQuestion}</p></div>
          {result?.answer_text && <section className="studio-approved-answer" aria-label="客服回答"><h4>客服回答</h4><div className="real-llm-answer">{result.answer_text}</div></section>}
          {result && <>
          {((result.qa_id && onOpenQa) || (result.outcome === 'unsupported' && onCreateQa)) && <div className="studio-result-actions">
            <h4>後續操作</h4>
            {result.qa_id && onOpenQa && <button type="button" className="line-secondary-btn" onClick={() => onOpenQa(result.qa_id!)}><Pencil aria-hidden="true" />編輯命中問答</button>}
            {result.outcome === 'unsupported' && onCreateQa && <button type="button" className="line-secondary-btn" onClick={() => onCreateQa(testedQuestion)}><Plus aria-hidden="true" />以此問題新增草稿</button>}
          </div>}
          <div className="studio-result-secondary">
          <details className="studio-technical"><summary>模型與詳細結果</summary><dl className="studio-facts"><dt>供應商</dt><dd>{result.provider}</dd><dt>模型</dt><dd>{result.model}</dd><dt>結果類型</dt><dd>{result.outcome}</dd><dt>命中題目</dt><dd>{result.qa_id ?? '—'}</dd><dt>索引版本</dt><dd>{result.index_version ?? '—'}</dd>{result.code && <><dt>結果代碼</dt><dd>{result.code}</dd></>}</dl></details>
          {result.outcome === 'answered' && <details className="studio-technical"><summary>回饋操作（會正式送出）</summary><p className="studio-description">此操作會記錄回饋；選擇未解決會進入專人客服處理流程。</p><div className="sim-feedback-row real-llm-feedback-row"><small className="real-llm-feedback-label">本則回覆是否有解答問題？</small><button type="button" className="real-llm-feedback-button is-helpful" disabled={feedbackStatus?.state === 'submitting'} onClick={() => void handleFeedback('helpful')}>有幫助</button><button type="button" className="real-llm-feedback-button is-unresolved" disabled={feedbackStatus?.state === 'submitting'} onClick={() => void handleFeedback('unresolved')}>未解決（通報專人客服）</button>{feedbackStatus && <span className={`real-llm-feedback-status is-${feedbackStatus.state}`} role={feedbackStatus.state === 'error' ? 'alert' : 'status'}>{feedbackStatus.message}</span>}</div></details>}
          </div>
          </>}
        </section>}
        {!running && !notice && <p className="studio-test-placeholder">輸入問題後，回答會顯示在這裡。</p>}
      </div>
    </div>
  );
};

export default RealLlmSemanticTestPanel;
