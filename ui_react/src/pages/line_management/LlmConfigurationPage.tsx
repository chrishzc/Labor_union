/**
 * File: LlmConfigurationPage.tsx
 * Description: 系統管理員 write-only LLM API Key 設定頁；永不讀回或顯示既有 secret。
 */
import React, { FormEvent, useEffect, useState } from 'react';
import {
  fetchLlmApiKeyStatus,
  replaceLlmApiKey,
  type LlmApiKeyStatus,
} from '../../api/system/llm_configuration_client';
import {
  ApiHttpError,
  ApiNetworkError,
  ApiTimeoutError,
} from '../../api/shared/typed_errors';
import './LlmConfigurationPage.css';


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


export const LlmConfigurationPage: React.FC = () => {
  const [apiKey, setApiKey] = useState('');
  const [status, setStatus] = useState<LlmApiKeyStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [saving, setSaving] = useState(false);
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
      setError('請輸入有效的 API Key。');
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
      setNotice('API Key 已儲存。基於安全設計，系統不提供讀回或顯示功能。');
    } catch (saveError: unknown) {
      setError(safeSaveErrorMessage(saveError));
    } finally {
      setSaving(false);
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
            此頁只允許寫入或覆寫 LLM API Key。既有 Key 不會回傳至瀏覽器，也不提供顯示功能。
          </p>
        </div>
        <div className={`llm-config-status ${status?.configured ? 'configured' : 'empty'}`}>
          <span className="llm-config-status-dot" aria-hidden="true" />
          <span>
            {loadingStatus
              ? '查詢中'
              : status?.configured
                ? 'API Key 已設定'
                : '尚未設定 API Key'}
          </span>
        </div>
      </header>

      <div className="llm-config-card">
        <div className="llm-config-card-heading">
          <h2>LLM API Key</h2>
          <p>儲存後輸入框會立即清空。再次提交會直接覆寫目前設定。</p>
        </div>

        <form onSubmit={handleSubmit} className="llm-config-form">
          <label htmlFor="llm-api-key">API Key</label>
          <input
            id="llm-api-key"
            name="llm-api-key"
            type="password"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="貼上 API Key"
            disabled={saving}
            aria-describedby="llm-api-key-help"
          />
          <p id="llm-api-key-help" className="llm-config-help">
            系統只會回報是否已設定，不會回傳完整或遮罩後的 Key。
          </p>

          <div className="llm-config-actions">
            <button type="submit" disabled={saving || apiKey.trim().length < 8}>
              {saving ? '儲存中…' : status?.configured ? '覆寫 API Key' : '儲存 API Key'}
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
