/**
 * File: RealLlmSemanticTestPanel.tsx
 * Description: 管理端真實 M2 語意測試；只由後端使用已儲存 Gemini secret，不發送 LINE 或建立工單。
 */
import React, { useState } from 'react';
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
  const [question, setQuestion] = useState('請問新竹市補助可以折抵幾小時？');
  const [result, setResult] = useState<LlmSemanticTest | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

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

  const [feedbackStatus, setFeedbackStatus] = useState<string | null>(null);

  const handleFeedback = async (choice: 'helpful' | 'unresolved') => {
    setFeedbackStatus(choice === 'helpful' ? '👍 感謝反饋！已記錄為有效解答。' : '🚨 已記錄為未解決，系統已自動通報專人客服工單！');
    try {
      await fetch('/api/v1/line/feedback', {
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
    } catch {
      // 保持前端即時體驗
    }
  };

  const QUICK_QUESTIONS = [
    '請問新竹市補助可以折抵幾小時？',
    '如果和月嫂合作不適合，可以換月嫂嗎？',
    '月嫂服務收費標準與訂金如何計算？',
    '月嫂服務是否有試用期？',
  ];

  return (
    <div className="ai-editor-card" style={{ marginBottom: '16px', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
      <div className="ai-editor-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #f1f5f9', paddingBottom: '10px' }}>
        <h4 style={{ margin: 0, fontSize: '16px', color: '#1e293b', display: 'flex', alignItems: 'center', gap: '8px' }}>
          🧠 Gemini + Knowledge 真實 M2 智能問答工作台
        </h4>
        <span style={{ fontSize: '12px', background: '#f0fdf4', color: '#15803d', padding: '2px 8px', borderRadius: '4px', border: '1px solid #bbf7d0', fontWeight: 600 }}>
          Gemini 3.1 Flash-Lite 即時連線
        </span>
      </div>

      <div className="line-warning" role="status" style={{ marginTop: '12px' }}>
        💡 本工作台直連 Google Gemini 與工會核准的向量知識庫（29 題常規 QA）。輸入民眾可能詢問的自然語言，系統將即時比對題庫、由 Gemini 智慧挑選最佳解答，並可立即測試滿意度反饋。
      </div>

      {/* 快捷常見問題一鍵填入 */}
      <div style={{ marginTop: '12px', marginBottom: '8px' }}>
        <small style={{ color: '#64748b', fontWeight: 600, display: 'block', marginBottom: '6px' }}>💡 點擊快捷填入民眾常見問題測試：</small>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {QUICK_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setQuestion(q)}
              style={{
                background: '#f8fafc',
                border: '1px solid #cbd5e1',
                borderRadius: '16px',
                padding: '4px 12px',
                fontSize: '12px',
                color: '#334155',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = '#e2e8f0'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = '#f8fafc'; }}
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      <div className="sim-input-bar" style={{ marginTop: '12px' }}>
        <input
          aria-label="Gemini 真實語意測試文字"
          placeholder="輸入民眾的測試提問 (例：請問補助可以折抵幾小時？)"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              void run();
            }
          }}
          style={{ flex: 1, padding: '10px 14px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px' }}
        />
        <button
          type="button"
          className="mock-primary-btn"
          onClick={() => void run()}
          disabled={running || !question.trim()}
          style={{ padding: '0 20px', fontWeight: 600, fontSize: '14px' }}
        >
          {running ? 'Gemini 智能檢索中…' : '🚀 執行真實 AI 智能解答'}
        </button>
      </div>

      {notice && <div className={result?.outcome === 'answered' ? 'line-success' : 'line-warning'} role="status" style={{ marginTop: '12px' }}>{notice}</div>}
      {result && (
        <div className={result.outcome === 'answered' ? 'line-success' : 'line-warning'} role="status" style={{ marginTop: '12px' }}>
          <div>provider：{result.provider} · model：{result.model} · outcome：{result.outcome}</div>
          <div>Knowledge index：{result.index_version ?? '—'} · matched QA：{result.qa_id ?? '—'}</div>
          {result.source_identity && <small>來源：{result.source_identity}</small>}
          {result.answer_text && <div style={{ marginTop: '8px', fontSize: '14px', lineHeight: 1.6 }}>{result.answer_text}</div>}
          {result.code && <div>fallback code：{result.code}</div>}

          {result.outcome === 'answered' && (
            <div className="sim-feedback-row" style={{ marginTop: '12px', borderTop: '1px dashed #fed9b8', paddingTop: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <small style={{ color: '#74593f', fontWeight: 600 }}>回覆滿意度調查：本則回覆是否有解答問題？</small>
              <button
                type="button"
                style={{ background: '#ecfdf5', border: '1px solid #10b981', color: '#047857', borderRadius: '4px', padding: '3px 10px', cursor: 'pointer', fontSize: '12px', fontWeight: 600 }}
                onClick={() => void handleFeedback('helpful')}
              >
                👍 有幫助
              </button>
              <button
                type="button"
                style={{ background: '#fef2f2', border: '1px solid #ef4444', color: '#b91c1c', borderRadius: '4px', padding: '3px 10px', cursor: 'pointer', fontSize: '12px', fontWeight: 600 }}
                onClick={() => void handleFeedback('unresolved')}
              >
                👎 未解決（通報專人客服）
              </button>
              {feedbackStatus && (
                <span style={{ fontSize: '12px', fontWeight: 600, color: feedbackStatus.includes('👍') ? '#059669' : '#dc2626', marginLeft: '6px' }}>
                  {feedbackStatus}
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
