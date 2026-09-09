/**
 * File: LlmConfigurationPage.tsx
 * Description: 系統管理員 write-only Google AI Studio API Key 設定頁；永不讀回或顯示既有 secret。
 */
import React, { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Bot, Eye, EyeOff, PlugZap, Save } from 'lucide-react';
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
  const [showApiKey, setShowApiKey] = useState(false);
  const [lastConnectionTestAt, setLastConnectionTestAt] = useState<Date | null>(null);
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
      setLastConnectionTestAt(new Date());
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
        <div className="llm-config-heading">
          <span className="llm-config-heading-icon" aria-hidden="true"><Bot /></span>
          <div>
            <p className="llm-config-eyebrow">LINE 專區</p>
            <h1 id="llm-config-title">AI 模型設定</h1>
            <p className="llm-config-description">
              管理 Gemini 連線憑證，並確認目前模型是否可正常回應。
            </p>
          </div>
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
          <dl className="llm-config-model-facts">
            <div><dt>供應商</dt><dd>Google AI Studio</dd></div>
            <div><dt>模型</dt><dd>{GEMINI_MODEL}</dd></div>
            <div><dt>方案</dt><dd>Free Tier 優先</dd></div>
          </dl>
        </div>

        <form onSubmit={handleSubmit} className="llm-config-form">
          <label htmlFor="llm-api-key">Google AI Studio API Key</label>
          <div className="llm-config-secret-field">
            <input
              id="llm-api-key"
              name="llm-api-key"
              type={showApiKey ? 'text' : 'password'}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="貼上新的 Gemini API Key"
              disabled={saving}
              aria-describedby="llm-api-key-help"
            />
            <button
              className="llm-config-secret-toggle"
              type="button"
              aria-label={showApiKey ? '隱藏正在輸入的 API Key' : '顯示正在輸入的 API Key'}
              aria-pressed={showApiKey}
              onClick={() => setShowApiKey((visible) => !visible)}
              disabled={saving || apiKey.length === 0}
            >
              {showApiKey ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
            </button>
          </div>
          <p id="llm-api-key-help" className="llm-config-help">
            {status?.configured
              ? '目前已有金鑰。基於安全契約，系統不回傳完整內容或末四碼；送出新值會覆寫原設定。'
              : '金鑰只會送往後端私密儲存，儲存後立即清空。'}
          </p>

          <div className="llm-config-actions">
            <button className="llm-config-primary-action" type="submit" disabled={saving || apiKey.trim().length < 8}>
              <Save aria-hidden="true" />
              {saving ? '儲存中…' : status?.configured ? '覆寫 Gemini API Key' : '儲存 Gemini API Key'}
            </button>
            <button
              className="llm-config-secondary-action"
              type="button"
              onClick={handleConnectionTest}
              disabled={!status?.configured || saving || testingConnection}
            >
              <PlugZap aria-hidden="true" />
              {testingConnection ? '測試中…' : '測試 Gemini 連線'}
            </button>
          </div>
        </form>

        {updatedAt && (
          <p className="llm-config-meta">最後更新：{updatedAt}</p>
        )}
        {lastConnectionTestAt && (
          <p className="llm-config-meta">最近測試：{lastConnectionTestAt.toLocaleString('zh-TW')}</p>
        )}
        {notice && <div className="llm-config-notice success" role="status">{notice}</div>}
        {error && <div className="llm-config-notice error" role="alert">{error}</div>}
      </div>
    </section>
  );
};

export default LlmConfigurationPage;
