/** Public sample bindings and display-only LINE conversation rendering. */
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { ChevronLeft, Info, Search, ShieldCheck, Smartphone } from 'lucide-react';
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

function TablePicture({ node, style }: { node: PreviewNode; style?: CSSProperties }) {
  const dialog = useRef<HTMLDialogElement>(null);
  return <><button type="button" className="notification-table-picture" style={style} aria-label={`放大${node.text}`} onClick={() => dialog.current?.showModal()}><img className="notification-table-image" src={node.image_data} alt={node.text} /></button><dialog ref={dialog} className="notification-picture-dialog" aria-label={`${node.text}完整圖片`}><button type="button" className="notification-button" onClick={() => dialog.current?.close()}>關閉圖片</button><img src={node.image_data} alt={`${node.text}完整圖片`} /></dialog></>;
}

const FLEX_TEXT_SIZES = new Map(Object.entries({ xxs: 11, xs: 13, sm: 14, md: 16, lg: 19, xl: 22, xxl: 29, '3xl': 35, '4xl': 48, '5xl': 74 }));
const FLEX_BUBBLE_WIDTHS = { nano: 120, micro: 160, deca: 180, hecto: 200, kilo: 240, mega: 300, giga: 360 };
type FlexGap = { layout: PreviewNode['layout']; space: number };

function flexNodeStyle(node: PreviewNode, previousGap?: FlexGap): CSSProperties | undefined {
  const style = node.appearance;
  if (!style) return undefined;
  const isButton = node.kind === 'button';
  const link = isButton && style.button_style === 'link';
  const marginOffset = previousGap && style.margin !== undefined ? style.margin - previousGap.space : undefined;
  return {
    backgroundColor: isButton && !link ? style.color : style.background_color,
    color: isButton && !link ? undefined : style.color,
    borderColor: style.border_color ?? (node.kind === 'separator' ? style.color : undefined),
    borderStyle: style.border_width === undefined ? undefined : 'solid',
    borderWidth: style.border_width,
    borderRadius: style.corner_radius,
    paddingTop: style.padding_top,
    paddingRight: style.padding_right,
    paddingBottom: style.padding_bottom,
    paddingLeft: style.padding_left,
    gap: style.gap,
    marginInlineStart: previousGap?.layout === 'horizontal' ? marginOffset : undefined,
    marginBlockStart: previousGap?.layout === 'vertical' ? marginOffset : undefined,
    width: style.width,
    height: style.height,
    flex: style.flex === 0 ? '0 0 auto' : style.flex,
    textAlign: style.align,
    justifyContent: style.justify_content,
    alignItems: style.align_items,
    whiteSpace: style.wrap === false ? 'nowrap' : undefined,
    overflow: style.wrap === false ? 'hidden' : undefined,
    textOverflow: style.wrap === false ? 'ellipsis' : undefined,
  };
}

function FlexNode({ node, previousGap, onAction }: { node: PreviewNode; previousGap?: FlexGap; onAction(value: string): void }) {
  const style = flexNodeStyle(node, previousGap);
  if (node.kind === 'image') return <TablePicture node={node} style={style} />;
  if (node.kind === 'text') {
    const fontSize = FLEX_TEXT_SIZES.get(node.size) ?? (/^[1-9]\d?px$/.test(node.size) ? node.size : undefined);
    return <p className={`notification-flex-text ${node.bold ? 'bold' : ''}`} style={{ ...style, fontSize }}>{node.text}</p>;
  }
  if (node.kind === 'separator') return <hr style={style} />;
  if (node.kind === 'button') return <button type="button" className={`notification-flex-action ${node.appearance?.button_style ?? (node.primary ? 'primary' : '')}`} style={style} onClick={() => onAction(`${node.text}：${node.action_description}`)}>{node.text}</button>;
  const gap = { layout: node.layout, space: node.appearance?.gap ?? 0 };
  return <div className={`notification-flex-box ${node.layout}`} style={style}>{node.children.map((child, index) => <FlexNode key={index} node={child} previousGap={index > 0 ? gap : undefined} onAction={onAction} />)}</div>;
}

function cardTitle(node: PreviewNode): string {
  if (node.kind === 'text' || node.kind === 'image') return node.text.trim();
  for (const child of node.children) {
    const title = cardTitle(child);
    if (title) return title;
  }
  return '';
}

export function LineMessagePreviewWorkspace({ descriptor, entryId, content, client, editor, footer }: {
  descriptor?: PreviewDescriptor; entryId: string; content?: string; client: LineMessagePreviewClient;
  editor: ReactNode; footer: ReactNode;
}) {
  const [state, setState] = useState<({ key: string; entryId: string } & ({ result: MessagePreviewResult } | { error: string })) | null>(null);
  const [action, setAction] = useState('');
  const [retry, setRetry] = useState(0);
  const [bubbleIndex, setBubbleIndex] = useState<number | 'last'>(0);
  const generation = useRef(0);
  const key = JSON.stringify([entryId, content, retry]);
  const result = state?.entryId === entryId && 'result' in state && (state.key === key || state.result.status === 'ready') ? state.result : undefined;
  const failed = state?.key === key && 'error' in state ? state.error : undefined;
  const updating = descriptor && result && state?.key !== key;
  const lastBubble = Math.max(0, (result?.bubbles.length ?? 1) - 1);
  const visibleBubble = bubbleIndex === 'last' ? lastBubble : Math.min(bubbleIndex, lastBubble);
  const bubble = result?.bubbles[visibleBubble];
  const bubbleSize = bubble?.appearance?.bubble_size;
  const selectBubble = (index: number) => { setBubbleIndex(index); setAction(''); };
  useEffect(() => { setBubbleIndex(['card-customer-confirmation', 'card-customer-profiles', 'card-candidate-information-package', 'card-candidate-information-1', 'card-candidate-information-2'].includes(entryId) ? 'last' : 0); }, [entryId]);
  useEffect(() => {
    if (!descriptor) return;
    const controller = new AbortController(), request = ++generation.current;
    setAction('');
    const timer = window.setTimeout(() => {
      void client.render({ id: entryId, data_source: 'sample', ...(content === undefined ? {} : { content }) }, { signal: controller.signal })
        .then(value => {
          if (controller.signal.aborted || generation.current !== request) return;
          setAction('');
          setState({ key, entryId, result: value });
        })
        .catch(error => { if (!controller.signal.aborted && generation.current === request) setState({ key, entryId, error: previewError(error) }); });
    }, 250);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [client, content, descriptor, entryId, key]);
  return <div className="notification-edit-and-preview">
    <div className="notification-inline-editor"><div className="notification-inline-scroll">{editor}</div><div className="notification-inline-footer">{footer}</div></div>
    <aside className="notification-phone-pane" aria-label="LINE 對話預覽">
      <div className="notification-phone-preview">
      <div className="notification-phone-heading"><strong>用戶看到的樣子</strong><span><ShieldCheck />僅預覽，不發送</span></div>
      <p className="notification-device-label">一般手機 · 完整訊息預覽</p>
      <div className="notification-phone"><div className="notification-phone-screen"><div className="notification-phone-clock">9:41 <Smartphone /></div><div className="notification-phone-nav"><ChevronLeft /><strong>新竹市月子工會</strong><Search /></div>
      {result?.status === 'ready' && result.format === 'flex' && result.bubbles.length > 1 && <nav className="notification-preview-pagination" aria-label="卡片預覽切換">
        <label>預覽卡片<select aria-label="選擇預覽卡片" value={visibleBubble} onChange={event => selectBubble(Number(event.target.value))}>{result.bubbles.map((bubble, index) => <option key={index} value={index}>{index + 1}. {cardTitle(bubble) || '訊息卡片'}</option>)}</select></label>
        <button type="button" className="notification-button" aria-label="上一張卡片" disabled={visibleBubble === 0} onClick={() => selectBubble(visibleBubble - 1)}>上一張</button><span aria-live="polite">第 {visibleBubble + 1} / {result.bubbles.length} 張</span><button type="button" className="notification-button" aria-label="下一張卡片" disabled={visibleBubble === result.bubbles.length - 1} onClick={() => selectBubble(visibleBubble + 1)}>下一張</button>
      </nav>}
      <div className="notification-phone-chat">
        <span className="notification-chat-today">今天</span><p className="notification-chat-sender">新竹市月子工會</p>
        {!descriptor ? <p className="notification-preview-state" role="status">此訊息的預覽來源尚未載入，請重新整理。</p> : failed ? <div className="notification-preview-state" role="alert">{failed}<button type="button" className="notification-text-button" onClick={() => setRetry(v => v + 1)}>重新查詢預覽</button></div> : !result ? <p className="notification-preview-state" role="status">正在產生預覽…</p> : result.status !== 'ready' ? <p className="notification-preview-state" role="status">{result.note}</p> : result.format === 'text' ? <div className="notification-bubble">{result.text}</div> : <div className="notification-flex-carousel">{bubble ? <article className={`notification-real-flex-bubble${bubble.appearance ? ' with-appearance' : ''}`} style={{ width: bubbleSize ? FLEX_BUBBLE_WIDTHS[bubbleSize] : undefined }}><FlexNode node={bubble} onAction={setAction} /></article> : <p className="notification-preview-state" role="status">此訊息目前沒有可顯示的卡片。</p>}</div>}
        <p className="notification-preview-updating" role="status">{updating ? '正在更新預覽…' : ''}</p>
      </div><div className="notification-phone-composer">＋ <span>輸入訊息</span> ☺</div></div></div>
      {action && result?.status === 'ready' && <p className="notification-action-description" role="status">{action}</p>}
      <p className="notification-phone-note"><Info />公版資料僅供預覽；實際顯示可能因 LINE 與手機設定而異。</p>
      </div>
    </aside>
  </div>;
}
