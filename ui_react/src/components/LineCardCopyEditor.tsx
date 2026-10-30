/** Edit a complete card's display copy without exposing its business actions. */
import { useRef, type RefObject } from 'react';
import type { LineNotificationTemplateData } from '../api/line_notification_rules/line_notification_template_client';

export type CardCopyField = NonNullable<LineNotificationTemplateData['fields']>[number];
export const cardCopyFieldId = (id: string) => `notification-card-copy-${encodeURIComponent(id)}`;

const VARIABLE_NAMES: Record<string, string> = {
  case_no: '案件編號', staff_name: '月嫂姓名', caregiver_names: '月嫂姓名', client_name: '客戶姓名',
  service_dates: '服務日期', service_period: '服務期間', first_payment_notice: '第一期款提醒',
  amount_ntd: '金額', due_date: '繳款日期', start_date: '服務開始日', end_date: '服務結束日',
};

export function LineCardCopyEditor({ fields, content, variables, disabled, onChange, bodyRef }: {
  fields: CardCopyField[]; content: string; variables: string[]; disabled: boolean;
  onChange(value: string): void; bodyRef: RefObject<HTMLTextAreaElement | null>;
}) {
  const values = JSON.parse(content) as Record<string, string>;
  const textareas = useRef<Record<string, HTMLTextAreaElement | null>>({});
  const kind = (field: CardCopyField) => field.kind ?? (field.label === '卡片標題' ? 'title' : field.label === '卡片文字' || field.label === '說明內容' ? 'body' : field.label === '按鈕名稱' ? 'button' : 'label');
  const titles = fields.filter(field => kind(field) === 'title');
  const bodies = fields.filter(field => kind(field) === 'body');
  const buttons = fields.filter(field => kind(field) === 'button');
  const others = fields.filter(field => !['title', 'body', 'button'].includes(kind(field)));
  const update = (field: CardCopyField, value: string) => onChange(JSON.stringify({ ...values, [field.id]: value }));
  const insert = (field: CardCopyField, value: string, atEnd = false) => {
    const textarea = textareas.current[field.id];
    if (!textarea) return;
    const current = values[field.id] ?? '';
    const start = atEnd ? current.length : textarea.selectionStart;
    const end = atEnd ? current.length : textarea.selectionEnd;
    if (current.length - (end - start) + value.length > field.max_length) return;
    update(field, current.slice(0, start) + value + current.slice(end));
    window.requestAnimationFrame(() => { textarea.focus(); textarea.setSelectionRange(start + value.length, start + value.length); if (atEnd) textarea.scrollTop = textarea.scrollHeight; });
  };
  const input = (field: CardCopyField, label: string) => <label key={field.id} className="notification-card-input" htmlFor={cardCopyFieldId(field.id)}>{label}<input id={cardCopyFieldId(field.id)} value={values[field.id] ?? ''} maxLength={field.max_length} aria-required={!field.optional} disabled={disabled} onChange={event => update(field, event.target.value)} /></label>;
  return <section className="notification-card-editor" aria-label="整張卡片文案編輯">
    {titles.map((field, index) => input(field, titles.length > 1 ? `卡片標題 ${index + 1}` : '卡片標題'))}
    {bodies.map((field, index) => <div className="notification-card-body" key={field.id}>
      <div className="notification-card-body-heading"><label htmlFor={cardCopyFieldId(field.id)}>{bodies.length > 1 ? `說明內容 ${index + 1}` : '說明內容'}</label><span>自由增減段落，換行會同步顯示</span></div>
      <div className="notification-card-toolbar">{variables.length > 0 && <span>插入系統資料</span>}{variables.map(variable => <button key={variable} type="button" className="notification-card-insert" disabled={disabled} onClick={() => insert(field, `{${variable}}`)}>＋ {VARIABLE_NAMES[variable] ?? variable}</button>)}<button type="button" className="notification-card-insert" disabled={disabled} onClick={() => insert(field, '\n\n', true)}>＋ 新增段落</button></div>
      <textarea id={cardCopyFieldId(field.id)} ref={element => { textareas.current[field.id] = element; if (index === 0) bodyRef.current = element; }} value={values[field.id] ?? ''} maxLength={field.max_length} aria-required={!field.optional} disabled={disabled} placeholder="在這裡新增說明、提醒或其他補充內容。" rows={16} onChange={event => update(field, event.target.value)} />
      <div className="notification-card-body-help"><span>{variables.length > 0 ? '系統資料標記會在發送時自動帶入' : '可自行新增說明；案件資料仍由原流程帶入'}</span><span>{(values[field.id] ?? '').length.toLocaleString()} / {field.max_length.toLocaleString()} 字</span></div>
    </div>)}
    {buttons.length > 0 && <section className="notification-card-buttons" aria-label="按鈕名稱"><div><strong>按鈕名稱</strong><span>確認與協助流程保持原有設定</span></div><div className="notification-card-button-inputs">{buttons.map((field, index) => input(field, index === 0 ? '主要按鈕' : buttons.length === 2 ? '其他選擇' : `按鈕 ${index + 1}`))}</div></section>}
    {others.length > 0 && <details className="notification-card-other-copy"><summary>其他文字與訊息摘要</summary><div>{others.map(field => input(field, field.label + (others.filter(item => item.label === field.label).length > 1 ? ` · ${field.content.slice(0, 20)}` : '')))}</div></details>}
  </section>;
}
