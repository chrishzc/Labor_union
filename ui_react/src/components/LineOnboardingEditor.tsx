/**
 * File: LineOnboardingEditor.tsx
 * Description: 提供 LINE 新好友 Onboarding 歡迎訊息的手動編輯、即時預覽與儲存工作台。
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Info,
  RotateCcw,
  Save,
  Smartphone,
  Sparkles,
} from 'lucide-react';
import {
  lineOnboardingClient,
  type LineOnboardingClient,
  type LineOnboardingData,
} from '../api/line_onboarding/line_onboarding_client';

export interface LineOnboardingEditorProps {
  client?: LineOnboardingClient;
  onSaved?: (data: LineOnboardingData) => void;
}

export const OFFICIAL_DEFAULT_ONBOARDING_MESSAGE = `您好！歡迎加入【新竹市月子工會】官方服務平台 🤱✨
我們提供專業、安心、有保障的到府坐月子媒合與母嬰照護服務。

📱【新手快速導覽・三步驟開始使用】

1️⃣ 準爸媽／產婦專區：
👉 請開啟以下專屬登記頁面，進行服務需求填寫或核對市府登記案件：
{url}
（此安全登記連結將於 15 分鐘後失效）

2️⃣ 專業月嫂服務人員：
👉 請點擊下方選單【月嫂專區】或直接在對話框輸入「我要綁定月嫂」進行身分認證。

3️⃣ 服務說明與專人諮詢：
👉 請點擊下方選單【服務說明】查看服務流程與常見問答。

---
💡 如需真人專員協助，隨時在對話框輸入「轉真人客服」，我們將由專人為您服務。

👇 請點擊下方圖文選單，開啟您的專屬服務！`;

const SAMPLE_GATEWAY_URL =
  'https://liff.line.me/{LIFF_ID}/gateway （安全專屬連結，15分鐘內有效）';

export const LineOnboardingEditor: React.FC<LineOnboardingEditorProps> = ({
  client = lineOnboardingClient,
  onSaved,
}) => {
  const [data, setData] = useState<LineOnboardingData | null>(null);
  const [content, setContent] = useState<string>('');
  const [savedContent, setSavedContent] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFeedback(null);
    client
      .get()
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setContent(res.content);
        setSavedContent(res.content);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        // 若伺服器端尚未建立自訂訊息或首次載入，自動預填官方推薦標準範本
        setData({
          template_id: 'customer_onboarding_welcome',
          content: OFFICIAL_DEFAULT_ONBOARDING_MESSAGE,
          revision: 0,
          sample_preview: OFFICIAL_DEFAULT_ONBOARDING_MESSAGE.replace(/\{url\}/g, SAMPLE_GATEWAY_URL),
          variables: ['url'],
        });
        setContent(OFFICIAL_DEFAULT_ONBOARDING_MESSAGE);
        setSavedContent(OFFICIAL_DEFAULT_ONBOARDING_MESSAGE);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const hasChanges = useMemo(() => {
    return content !== savedContent;
  }, [content, savedContent]);

  const previewText = useMemo(() => {
    if (!content) return '';
    return content.replace(/\{url\}/g, SAMPLE_GATEWAY_URL);
  }, [content]);

  const handleResetToDefault = () => {
    setContent(OFFICIAL_DEFAULT_ONBOARDING_MESSAGE);
    setFeedback(null);
  };

  const handleDiscardChanges = () => {
    setContent(savedContent);
    setFeedback(null);
  };

  const handleInsertUrlVariable = () => {
    if (content.includes('{url}')) return;
    setContent((prev) => `${prev}\n{url}`);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!data) return;
    if (!content.trim()) {
      setFeedback({ type: 'error', message: '歡迎訊息內容不可為空。' });
      return;
    }
    setSaving(true);
    setFeedback(null);
    try {
      const updated = await client.update({
        content,
        expected_revision: data.revision,
      });
      setData(updated);
      setContent(updated.content);
      setSavedContent(updated.content);
      setFeedback({ type: 'success', message: 'Onboarding 歡迎訊息已成功儲存！' });
      if (onSaved) onSaved(updated);
    } catch (err) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : '儲存歡迎訊息失敗，請稍後再試。',
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="richmenu-card notification-onboarding-card">
        <div className="line-card-description" style={{ padding: '24px', textAlign: 'center' }}>
          正在載入 Onboarding 歡迎訊息設定…
        </div>
      </div>
    );
  }

  return (
    <div className="richmenu-card notification-onboarding-card" data-testid="onboarding-editor-card">
      <div className="richmenu-card-header">
        <div>
          <div className="notification-heading-row">
            <h3 className="line-card-title richmenu-heading-with-icon">
              <Sparkles aria-hidden="true" />新好友加入即時歡迎詞與功能導覽
            </h3>
            <span className="line-status line-status-bound notification-preview-status">
              版本 Rev.{data?.revision ?? 0}
            </span>
          </div>
          <p className="line-card-description">
            此訊息為新好友加好友（LINE Follow Webhook）或重新解除封鎖時，系統自動發送的第一則引導訊息。您可於下方自由編修，並可即時預覽手機顯示效果。
          </p>
        </div>
      </div>

      {feedback && (
        <div
          role="alert"
          style={{
            margin: '0 0 16px 0',
            padding: '12px 16px',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '0.9rem',
            background: feedback.type === 'success' ? '#f0fdf4' : '#fef2f2',
            color: feedback.type === 'success' ? '#166534' : '#991b1b',
            border: `1px solid ${feedback.type === 'success' ? '#bbf7d0' : '#fecaca'}`,
          }}
        >
          {feedback.type === 'success' ? (
            <CheckCircle2 size={18} aria-hidden="true" />
          ) : (
            <AlertCircle size={18} aria-hidden="true" />
          )}
          <span>{feedback.message}</span>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
        {/* 左側：手動編輯區 */}
        <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <label htmlFor="onboarding-content-input" style={{ fontWeight: 700, fontSize: '0.92rem' }}>
              歡迎訊息內容編輯
            </label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                className="line-secondary-btn"
                style={{ fontSize: '0.8rem', padding: '3px 8px' }}
                onClick={handleResetToDefault}
                title="恢復為工會推薦的標準文案"
              >
                <RotateCcw size={14} style={{ marginRight: '4px' }} aria-hidden="true" />
                還原官方預設
              </button>
              {hasChanges && (
                <button
                  type="button"
                  className="line-secondary-btn"
                  style={{ fontSize: '0.8rem', padding: '3px 8px' }}
                  onClick={handleDiscardChanges}
                  title="放棄未儲存的變更"
                >
                  放棄修改
                </button>
              )}
            </div>
          </div>

          <textarea
            id="onboarding-content-input"
            data-testid="onboarding-textarea"
            rows={16}
            value={content}
            onChange={(e) => {
              setContent(e.target.value);
              if (feedback?.type === 'error') setFeedback(null);
            }}
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: '6px',
              border: '1px solid var(--line-color-border-subtle, #e2e8f0)',
              fontFamily: 'inherit',
              fontSize: '0.88rem',
              lineHeight: 1.6,
              resize: 'vertical',
              boxSizing: 'border-box',
            }}
            placeholder="請輸入新好友歡迎訊息內容…"
          />

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '8px 12px',
              background: '#f8fafc',
              borderRadius: '6px',
              fontSize: '0.82rem',
              color: '#64748b',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Info size={16} aria-hidden="true" />
              <span>
                支援動態變數：<code style={{ background: '#e2e8f0', padding: '1px 5px', borderRadius: '3px' }}>{'{url}'}</code>（自動帶入 15 分鐘專屬安全登記連結）
              </span>
            </div>
            {!content.includes('{url}') && (
              <button
                type="button"
                style={{
                  border: 'none',
                  background: 'none',
                  color: 'var(--line-color-primary, #0284c7)',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.8rem',
                }}
                onClick={handleInsertUrlVariable}
              >
                + 插入連結變數
              </button>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '6px' }}>
            <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
              字數統計：{content.length} 字
            </span>
            <button
              type="submit"
              data-testid="onboarding-save-btn"
              className="line-primary-btn"
              disabled={saving || !hasChanges}
              style={{
                opacity: saving || !hasChanges ? 0.6 : 1,
                cursor: saving || !hasChanges ? 'not-allowed' : 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <Save size={16} aria-hidden="true" />
              {saving ? '儲存中…' : '儲存歡迎訊息'}
            </button>
          </div>
        </form>

        {/* 右側：即時預覽區 */}
        <div>
          <div className="notification-preview-panel" style={{ marginTop: 0 }}>
            <div className="notification-preview-header">
              <strong className="richmenu-heading-with-icon">
                <Smartphone aria-hidden="true" />即時預覽（手機畫面呈現）
              </strong>
              <span className="notification-trigger-badge">
                觸發條件：LINE Follow Webhook
              </span>
            </div>

            <div
              className="notification-message-preview"
              data-testid="onboarding-preview-box"
              style={{ minHeight: '340px' }}
            >
              {previewText || '（尚未輸入內容）'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LineOnboardingEditor;
