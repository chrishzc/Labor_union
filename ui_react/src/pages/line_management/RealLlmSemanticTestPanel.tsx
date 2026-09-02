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

  return (
    <div className="ai-editor-card" style={{ marginBottom: '16px' }}>
      <div className="ai-editor-header">
        <h4>🧠 Gemini + Knowledge 真實 M2 測試</h4>
      </div>
      <div className="line-warning" role="status">
        此按鈕會真的呼叫目前設定的 Gemini，並使用正式 READY Knowledge index／Chroma 候選流程；Gemini 只能選候選 ID，最後答案仍取核准題庫。只做 read-only 測試，不發 LINE、不建立工單、不寫入題庫。請勿貼入姓名、電話、地址等真實個資。
      </div>
      <div className="sim-input-bar">
        <input
          aria-label="Gemini 真實語意測試文字"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              void run();
            }
          }}
        />
        <button
          type="button"
          className="mock-primary-btn"
          onClick={() => void run()}
          disabled={running || !question.trim()}
        >
          {running ? 'Gemini 測試中…' : '🧠 執行真實 Gemini 測試'}
        </button>
      </div>
      {notice && <div className={result?.outcome === 'answered' ? 'line-success' : 'line-warning'} role="status">{notice}</div>}
      {result && (
        <div className={result.outcome === 'answered' ? 'line-success' : 'line-warning'} role="status">
          <div>provider：{result.provider} · model：{result.model} · outcome：{result.outcome}</div>
          <div>Knowledge index：{result.index_version ?? '—'} · matched QA：{result.qa_id ?? '—'}</div>
          {result.source_identity && <small>來源：{result.source_identity}</small>}
          {result.answer_text && <div style={{ marginTop: '8px' }}>{result.answer_text}</div>}
          {result.code && <div>fallback code：{result.code}</div>}
        </div>
      )}
    </div>
  );
};

export default RealLlmSemanticTestPanel;
