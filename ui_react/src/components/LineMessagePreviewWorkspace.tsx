/** Public sample bindings and display-only LINE conversation rendering. */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, FlaskConical, Info, Search, ShieldCheck, Smartphone } from 'lucide-react';
import type { LineMessagePreviewClient, MessagePreviewResult, PreviewDescriptor, PreviewNode } from '../api/line_notification_rules/line_message_preview_client';
import { ApiHttpError } from '../api/shared/typed_errors';

function previewError(error: unknown): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return '登入已失效，請重新登入。';
    if (error.status === 403) return '目前帳號沒有預覽權限。';
    if (error.status === 404) return '所選訊息已不存在，請重新選擇。';
    if (error.status === 422) return '文案或必要變數不完整，請確認內容後再試。';
  }
  return '預覽載入失敗，請重新查詢。';
}

function FlexNode({ node, onAction }: { node: PreviewNode; onAction(value: string): void }) {
  if (node.kind === 'text') return <p className={`notification-flex-text ${node.bold ? 'bold' : ''} ${['md', 'lg', 'xl', 'xxl'].includes(node.size) ? 'large' : ''}`}>{node.text}</p>;
  if (node.kind === 'separator') return <hr />;
  if (node.kind === 'button') return <button type="button" className={`notification-flex-action ${node.primary ? 'primary' : ''}`} onClick={() => onAction(`${node.text}：${node.action_description}`)}>{node.text}</button>;
  return <div className={`notification-flex-box ${node.layout}`}>{node.children.map((child, index) => <FlexNode key={index} node={child} onAction={onAction} />)}</div>;
}

export function LineMessagePreviewWorkspace({ descriptor, entryId, content, client, editor, footer, showSources = true }: {
  descriptor?: PreviewDescriptor; entryId: string; content?: string; client: LineMessagePreviewClient;
  editor: ReactNode; footer: ReactNode; showSources?: boolean;
}) {
  const [state, setState] = useState<{ key: string; result?: MessagePreviewResult; error?: string } | null>(null);
  const [action, setAction] = useState('');
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  const key = JSON.stringify([entryId, content, retry]);
  const result = state?.key === key ? state.result : undefined;
  const failed = state?.key === key && state.error;
  useEffect(() => {
    if (!descriptor) return;
    const controller = new AbortController(), request = ++generation.current;
    setAction('');
    const timer = window.setTimeout(() => {
      void client.render({ id: entryId, data_source: 'sample', ...(content === undefined ? {} : { content }) }, { signal: controller.signal })
        .then(value => { if (!controller.signal.aborted && generation.current === request) setState({ key, result: value }); })
        .catch(error => { if (!controller.signal.aborted && generation.current === request) setState({ key, error: previewError(error) }); });
    }, 250);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [client, content, descriptor, entryId, key]);
  return <div className="notification-edit-and-preview">
    <div className="notification-inline-editor"><div className="notification-inline-scroll">{editor}
      {showSources && descriptor && <section className="notification-record-section" aria-label="公版預覽資料">
        <h3>公版預覽資料 <span>範例資料</span></h3>
        <p className="notification-help">以下是公版範例，非真實案件或月嫂，不受案件資格限制。實際發送時由正式流程帶入資料。</p>
        {result && result.facts.length > 0 ? <div className="notification-sample-bindings-scroll" role="region" aria-label="帶入欄位與值" tabIndex={0}><table className="notification-sample-bindings"><caption>本次帶入欄位與值</caption><thead><tr><th scope="col">欄位</th><th scope="col">帶入值</th></tr></thead><tbody>{result.facts.map(fact => <tr key={fact.id}><th scope="row">{fact.id}</th><td>{fact.label || '未提供'}</td></tr>)}</tbody></table></div> : result?.status === 'ready' ? <p className="notification-help">此訊息為固定文案，沒有需要帶入的欄位。</p> : null}
      </section>}
    </div><div className="notification-inline-footer">{footer}</div></div>
    <aside className="notification-phone-pane" aria-label="LINE 對話預覽">
      <div className="notification-phone-heading"><strong>用戶看到的樣子</strong><span><ShieldCheck />僅預覽，不發送</span></div>
      <p className="notification-device-label">一般手機 · 公版範例</p>
      <div className="notification-phone"><div className="notification-phone-screen"><div className="notification-phone-clock">9:41 <Smartphone /></div><div className="notification-phone-nav"><ChevronLeft /><strong>新竹市月子工會</strong><Search /></div><div className="notification-phone-chat">
        <span className="notification-chat-today">今天</span><p className="notification-chat-sender">新竹市月子工會</p>
        {!descriptor ? <p className="notification-preview-state" role="status">此訊息的預覽來源尚未載入，請重新整理。</p> : failed ? <div className="notification-preview-state" role="alert">{failed}<button type="button" className="notification-text-button" onClick={() => setRetry(v => v + 1)}>重新查詢預覽</button></div> : !result ? <p className="notification-preview-state" role="status">正在產生預覽…</p> : result.status !== 'ready' ? <p className="notification-preview-state" role="status">{result.note}</p> : result.format === 'text' ? <div className="notification-bubble">{result.text}</div> : <div className="notification-flex-carousel">{result.bubbles.map((bubble, index) => <article className="notification-real-flex-bubble" key={index}><FlexNode node={bubble} onAction={setAction} /></article>)}</div>}
      </div><div className="notification-phone-composer">＋ <span>輸入訊息</span> ☺</div></div></div>
      {action && result?.status === 'ready' && <p className="notification-action-description" role="status">{action}</p>}
      <p className="notification-phone-note"><Info />實際呈現會依 LINE 版本與手機設定而異。卡片按鈕只顯示動作說明。</p>
      <p className="notification-phone-note"><FlaskConical />不產生互動憑證、不寫入資料或發送訊息。</p>
    </aside>
  </div>;
}
