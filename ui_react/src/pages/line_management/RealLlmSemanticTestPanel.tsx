/**
 * File: RealLlmSemanticTestPanel.tsx
 * Description: 管理端真實 M2 語意測試；只由後端使用已儲存 Gemini secret，不發送 LINE 或建立工單。
 */
import React, { useEffect, useState } from 'react';
import { Brain, Rocket } from 'lucide-react';
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
  if (result.outcome === 'answered') return '已完成真實 Gemini 語意選擇，以下答案來自核准 Knowledge 題庫。';
  if (result.outcome === 'unsupported') return 'Gemini／Knowledge 沒有找到足夠可信的核准答案，正式流程會安全 fallback。';
  if (result.code === 'knowledge_index_unavailable') return 'Knowledge index 尚未建立或沒有 READY 版本，請先完成索引建置。';
  if (result.code === 'knowledge_index_read_failed') return 'READY index 存在，但目前無法讀取 Chroma collection。';
  if (result.code === 'not_configured') return 'Gemini API Key 尚未設定。';
  if (result.code === 'authentication_failed') return 'Gemini API Key 驗證失敗。';
  if (result.code === 'rate_limited') return 'Gemini Free Tier 目前達到配額或速率限制。';
  if (result.code === 'model_unavailable') return '目前設定的 Gemini 模型不可用。';
  if (result.code === 'timeout') return 'Gemini 請求逾時。';
  if (result.code === 'unavailable') return '目前無法連線到 Google Gemini API。';
  return `本次測試未產生答案（${result.code ?? result.outcome}）。`;
}

export const RealLlmSemanticTestPanel: React.FC = () => {
  const [question, setQuestion] = useState('');
  const [quickQuestions, setQuickQuestions] = useState<string[]>([]);
  const [catalogNotice, setCatalogNotice] = useState<string | null>(null);
  const [result, setResult] = useState<LlmSemanticTest | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

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
      setCatalogNotice(publishedQuestions.length === 0 ? '目前沒有已發布的 QA，請先完成審核、發布與索引建置。' : null);
    }).catch(() => {
      setCatalogNotice('無法讀取已發布的 Knowledge QA，不提供可能失敗的快捷測試題。');
    });
  }, []);

  const run = async () => {
    const normalized = question.trim();
    if (!normalized) return;
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
      <div className="ai-editor-header real-llm-header">
        <h3 className="real-llm-title">
          <Brain aria-hidden="true" />Gemini + Knowledge 真實 M2 智能問答工作台
        </h3>
        <span className="real-llm-status">
          {running ? '正在執行連線測試' : result ? `本次結果：${result.outcome}` : '尚未執行連線測試'}
        </span>
      </div>

      <div className="line-warning line-block-spacing-12" role="status">
        本工作台使用後端目前儲存的模型設定與核准知識庫進行測試。執行後才會顯示實際 provider、model 與結果；本頁不代表 LINE 已送達。
      </div>

      {/* 快捷常見問題一鍵填入 */}
      <div className="real-llm-quick-section">
        <small className="real-llm-quick-label">點擊快捷填入民眾常見問題測試：</small>
        <div className="real-llm-quick-list">
          {quickQuestions.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setQuestion(q)}
              className="real-llm-quick-button"
            >
              {q}
            </button>
          ))}
        </div>
        {catalogNotice && <div className="line-warning line-block-spacing-12" role="status">{catalogNotice}</div>}
      </div>

      <div className="sim-input-bar real-llm-input-row">
        <input
          aria-label="Gemini 真實語意測試文字"
          placeholder="請從已發布題目選擇，或輸入民眾的測試提問"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              void run();
            }
          }}
          className="real-llm-input"
        />
        <button
          type="button"
          className="mock-primary-btn"
          onClick={() => void run()}
          disabled={running || !question.trim()}
        >
          <Rocket aria-hidden="true" />{running ? 'Gemini 智能檢索中…' : '執行真實 AI 智能解答'}
        </button>
      </div>

      {notice && <div className={`${result?.outcome === 'answered' ? 'line-success' : 'line-warning'} line-block-spacing-12`} role="status">{notice}</div>}
      {result && (
        <div className={`${result.outcome === 'answered' ? 'line-success' : 'line-warning'} line-block-spacing-12`} role="status">
          {result.answer_text && <div className="real-llm-answer">{result.answer_text}</div>}
          {result.code && <div>fallback code：{result.code}</div>}

          {result.outcome === 'answered' && (
            <div className="sim-feedback-row real-llm-feedback-row">
              <small className="real-llm-feedback-label">回覆滿意度調查：本則回覆是否有解答問題？</small>
              <button
                type="button"
                className="real-llm-feedback-button is-helpful"
                disabled={feedbackStatus?.state === 'submitting'}
                onClick={() => void handleFeedback('helpful')}
              >
                有幫助
              </button>
              <button
                type="button"
                className="real-llm-feedback-button is-unresolved"
                disabled={feedbackStatus?.state === 'submitting'}
                onClick={() => void handleFeedback('unresolved')}
              >
                未解決（通報專人客服）
              </button>
              {feedbackStatus && (
                <span
                  className={`real-llm-feedback-status is-${feedbackStatus.state}`}
                  role={feedbackStatus.state === 'error' ? 'alert' : 'status'}
                >
                  {feedbackStatus.message}
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default RealLlmSemanticTestPanel;
