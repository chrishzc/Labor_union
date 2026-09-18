/**
 * File: LineNotificationTemplateEditor.tsx
 * Description: 編輯通知規則實際發送的文字內容，並即時模擬手機顯示。
 */
import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Info, RotateCcw, Save, Smartphone } from 'lucide-react';
import { ApiHttpError } from '../api/shared/typed_errors';
import {
  lineNotificationTemplateClient,
  type LineNotificationTemplateClient,
  type LineNotificationTemplateData,
} from '../api/line_notification_rules/line_notification_template_client';

export interface LineNotificationTemplateEditorProps {
  ruleId: string;
  client?: LineNotificationTemplateClient;
}

function displayError(error: unknown): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return '登入已失效，請重新登入後再試。';
    if (error.status === 403) return '目前帳號沒有維護 LINE 通知內容的權限。';
    if (error.status === 404) return '找不到此規則目前使用的訊息模板。';
    if (error.status === 409) return '訊息內容已被其他人修改，請重新載入後再試。';
    if (error.status === 422) return '訊息內容不完整，請檢查後再試。';
  }
  return '通知訊息內容目前無法讀取，請稍後再試。';
}

function renderPreview(content: string, variables: string[]): string {
  return variables.reduce(
    (current, variable) => current.replaceAll(`{${variable}}`, `〔${variable}〕`),
    content,
  );
}

export const LineNotificationTemplateEditor: React.FC<
  LineNotificationTemplateEditorProps
> = ({ ruleId, client = lineNotificationTemplateClient }) => {
  const [template, setTemplate] = useState<LineNotificationTemplateData | null>(null);
  const [content, setContent] = useState('');
  const [savedContent, setSavedContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setFeedback(null);
    client.get(ruleId, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        setTemplate(result);
        setContent(result.content);
        setSavedContent(result.content);
        setLoading(false);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setTemplate(null);
        setLoading(false);
        setFeedback({ type: 'error', message: displayError(error) });
      });
    return () => controller.abort();
  }, [client, reloadVersion, ruleId]);

  const hasChanges = content !== savedContent;
  const preview = useMemo(
    () => renderPreview(content, template?.variables ?? []),
    [content, template?.variables],
  );

  const save = async (): Promise<void> => {
    if (!template || !content.trim() || !hasChanges) return;
    setSaving(true);
    setFeedback(null);
    try {
      const updated = await client.update(ruleId, {
        content,
        expected_revision: template.revision,
      });
      setTemplate(updated);
      setContent(updated.content);
      setSavedContent(updated.content);
      setFeedback({ type: 'success', message: '通知訊息內容已成功儲存！' });
    } catch (error) {
      setFeedback({ type: 'error', message: displayError(error) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="notification-template-editor" aria-label="通知訊息內容編輯">
      <div className="notification-template-heading">
        <div>
          <h5>通知訊息內容</h5>
          <p>直接編輯此規則實際發送的文字；動態資料會在發送時代入。</p>
        </div>
        {template && <span className="line-status line-status-bound">版本 Rev.{template.revision}</span>}
      </div>

      {loading && <div className="line-loading" role="status">正在載入通知訊息內容…</div>}

      {feedback && (
        <div className={feedback.type === 'success' ? 'line-success' : 'line-error'} role={feedback.type === 'error' ? 'alert' : 'status'}>
          {feedback.type === 'success'
            ? <CheckCircle2 aria-hidden="true" />
            : <AlertCircle aria-hidden="true" />}
          <span>{feedback.message}</span>
        </div>
      )}

      {!loading && !template && (
        <button type="button" className="line-secondary-btn" onClick={() => setReloadVersion((value) => value + 1)}>重新載入訊息內容</button>
      )}

      {template && (
        <div className="notification-template-workbench">
          <div className="notification-template-compose">
            <div className="notification-template-label-row">
              <label htmlFor={`line-notification-template-content-${ruleId}`}>訊息內容編輯</label>
              <button
                type="button"
                className="line-secondary-btn line-compact-button"
                disabled={!hasChanges || saving}
                onClick={() => {
                  setContent(savedContent);
                  setFeedback(null);
                }}
              >
                <RotateCcw aria-hidden="true" />放棄修改
              </button>
            </div>
            <textarea
              id={`line-notification-template-content-${ruleId}`}
              value={content}
              rows={14}
              maxLength={5_000}
              disabled={saving}
              onChange={(event) => {
                setContent(event.target.value);
                if (feedback) setFeedback(null);
              }}
            />
            <div className="notification-template-meta">
              <span>{content.length} / 5000 字</span>
              {template.variables.length > 0 && (
                <span className="notification-template-variables">
                  <Info aria-hidden="true" />動態變數：{template.variables.map((name) => `{${name}}`).join('、')}
                </span>
              )}
            </div>
            <button
              type="button"
              className="line-primary-btn notification-template-save"
              disabled={saving || !hasChanges || !content.trim()}
              onClick={() => void save()}
            >
              <Save aria-hidden="true" />{saving ? '儲存中…' : '儲存訊息內容'}
            </button>
          </div>

          <div className="notification-preview-panel notification-template-preview">
            <div className="notification-preview-header">
              <strong className="richmenu-heading-with-icon">
                <Smartphone aria-hidden="true" />即時預覽（手機畫面呈現）
              </strong>
              <span className="notification-trigger-badge">{template.name}</span>
            </div>
            <div className="notification-message-preview">
              {preview || '（尚未輸入內容）'}
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

export default LineNotificationTemplateEditor;
