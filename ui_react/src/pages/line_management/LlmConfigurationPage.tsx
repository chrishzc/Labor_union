/**
 * File: LlmConfigurationPage.tsx
 * Description: 系統管理員 write-only Google AI Studio API Key 設定頁；永不讀回或顯示既有 secret。
 */
import React, { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import {
  fetchLlmApiKeyStatus,
  replaceLlmApiKey,
  testLlmConnection,
  type LlmApiKeyStatus,
} from '../../api/system/llm_configuration_client';
import {
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../../api/shared/typed_errors';
import './LlmConfigurationPage.css';


const GEMINI_MODEL = 'gemini-3.5-flash-lite';


function safeSaveErrorMessage(error: unknown): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return '管理員 Session 已失效，請重新登入後再試。';
    if (error.status === 403) return '目前帳號沒有 AI 模型設定權限（HTTP 403）。';
    if (error.status === 404) {
      return '後端尚未載入 AI 模型設定 API（HTTP 404）。請重新啟動 FastAPI 後再試。';
    }
    if (error.status === 422) return 'API Key 格式不符合目前的輸入規則（HTTP 422）。';
    if (error.status === 503) return '後端目前無法寫入 API Key 儲存位置（HTTP 503）。';
    return `API Key 儲存失敗（HTTP ${error.status} / ${error.code}）。`;
  }
  if (error instanceof ApiTimeoutError) return 'API Key 儲存逾時，請確認後端服務狀態後再試。';
  if (error instanceof ApiNetworkError) return '無法連線到後端 API，請確認 FastAPI 是否正在執行。';
  return 'API Key 儲存失敗，請稍後再試。';
}


function connectionResultMessage(code: string | null): string {
  if (code === 'not_configured') return '尚未設定 Gemini API Key。';
  if (code === 'authentication_failed') return 'Google 拒絕驗證此 API Key，請重新產生或覆寫 Key。';
  if (code === 'model_unavailable') return `目前無法使用 ${GEMINI_MODEL}。`;
  if (code === 'rate_limited') return '已連到 Google，但目前受到配額或頻率限制。';
  if (code === 'timeout') return 'Gemini 連線測試逾時。';
  if (code === 'unavailable') return '目前無法連線到 Google Gemini API。';
  if (code === 'empty_response') return 'Google 已回應，但沒有取得有效測試內容。';
  return 'Gemini 連線測試未通過。';
}


export const LlmConfigurationPage: React.FC = () => {
  const [apiKey, setApiKey] = useState('');
  const [status, setStatus] = useState<LlmApiKeyStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchLlmApiKeyStatus()
      .then((nextStatus) => {
        if (active) setStatus(nextStatus);
      })
      .catch((statusError: unknown) => {
        if (active) {
          if (statusError instanceof ApiHttpError && statusError.status === 404) {
            setError('後端尚未載入 AI 模型設定 API（HTTP 404）。請重新啟動 FastAPI。');
          } else if (statusError instanceof ApiNetworkError) {
            setError('無法連線到後端 API，請確認 FastAPI 是否正在執行。');
          } else {
            setError('無法讀取 API Key 設定狀態。');
          }
        }
      })
      .finally(() => {
        if (active) setLoadingStatus(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = apiKey.trim();
    if (normalized.length < 8) {
      setError('請輸入有效的 Google AI Studio API Key。');
      setNotice(null);
      return;
    }

    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const nextStatus = await replaceLlmApiKey(normalized);
      setStatus(nextStatus);
      setApiKey('');
      setNotice('Google AI Studio API Key 已儲存。系統不提供讀回或顯示功能。');
    } catch (saveError: unknown) {
      setError(safeSaveErrorMessage(saveError));
    } finally {
      setSaving(false);
    }
  };

  const handleConnectionTest = async () => {
    setTestingConnection(true);
    setError(null);
    setNotice(null);
    try {
      const result = await testLlmConnection();
      if (result.connected) {
        setNotice(`Gemini 連線成功：${result.model}`);
      } else {
        setError(connectionResultMessage(result.code));
      }
    } catch (testError: unknown) {
      if (testError instanceof ApiHttpError && testError.status === 401) {
        setError('管理員 Session 已失效，請重新登入後再試。');
      } else if (testError instanceof ApiHttpError && testError.status === 403) {
        setError('目前帳號沒有 AI 模型設定權限（HTTP 403）。');
      } else if (testError instanceof ApiNetworkError) {
        setError('無法連線到後端 API，請確認 FastAPI 是否正在執行。');
      } else if (testError instanceof ApiTimeoutError) {
        setError('後端連線測試逾時。');
      } else {
        setError('無法執行 Gemini 連線測試。');
      }
    } finally {
      setTestingConnection(false);
    }
  };

  const updatedAt = status?.updated_at
    ? new Date(status.updated_at).toLocaleString('zh-TW')
    : null;

  return (
    <section className="llm-config-page" aria-labelledby="llm-config-title">
      <header className="llm-config-header">
        <div>
          <p className="llm-config-eyebrow">LINE Hub / AI</p>
          <h1 id="llm-config-title">AI 模型設定</h1>
          <p className="llm-config-description">
            目前固定使用 Google AI Studio 的 Gemini API，並優先採用 Free Tier 的 Flash-Lite 模型。
            Key 只會送往後端寫入私有 runtime secret；既有 Key 不會回傳至瀏覽器。
          </p>
        </div>
        <div className={`llm-config-status ${status?.configured ? 'configured' : 'empty'}`}>
          <span className="llm-config-status-dot" aria-hidden="true" />
          <span>
            {loadingStatus
              ? '查詢中'
              : status?.configured
                ? 'Gemini API Key 已設定'
                : '尚未設定 Gemini API Key'}
          </span>
        </div>
      </header>

      <div className="llm-config-card">
        <div className="llm-config-card-heading">
          <h2>Google AI Studio / Gemini API</h2>
          <p>模型：{GEMINI_MODEL}（Free Tier 優先）。儲存後輸入框立即清空；再次提交會覆寫目前設定。</p>
        </div>

        <form onSubmit={handleSubmit} className="llm-config-form">
          <label htmlFor="llm-api-key">Google AI Studio API Key</label>
          <input
            id="llm-api-key"
            name="llm-api-key"
            type="password"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="貼上 Gemini API Key"
            disabled={saving}
            aria-describedby="llm-api-key-help"
          />
          <p id="llm-api-key-help" className="llm-config-help">
            系統只回報是否已設定與更新時間；不會透過任何管理 API 回傳完整或遮罩後的 Key。
          </p>

          <div className="llm-config-actions">
            <button type="submit" disabled={saving || apiKey.trim().length < 8}>
              {saving ? '儲存中…' : status?.configured ? '覆寫 Gemini API Key' : '儲存 Gemini API Key'}
            </button>
            <button
              type="button"
              onClick={handleConnectionTest}
              disabled={!status?.configured || saving || testingConnection}
            >
              {testingConnection ? '測試中…' : '測試 Gemini 連線'}
            </button>
          </div>
        </form>

        {updatedAt && (
          <p className="llm-config-meta">最後更新：{updatedAt}</p>
        )}
        {notice && <div className="llm-config-notice success" role="status">{notice}</div>}
        {error && <div className="llm-config-notice error" role="alert">{error}</div>}
      </div>
    </section>
  );
};

export default LlmConfigurationPage;
