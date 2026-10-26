/** 精簡 LINE 訊息流程導覽；只查詢目錄與規則，不提供 writer 或發送操作。 */
import { useEffect, useState, type CSSProperties } from 'react';
import { ArrowRight, ChevronDown, MessageSquare, RefreshCw, X } from 'lucide-react';
import { lineConfigurationQueryClient, type LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import { lineMessagePreviewClient, type LineMessagePreviewClient, type PreviewDescriptor } from '../api/line_notification_rules/line_message_preview_client';
import { adaptLineNotificationRulesCatalog, type LineNotificationRuleModel } from '../adapters/line_configuration/line_configuration_query_adapter';
import { LINE_MESSAGE_FLOWS, MESSAGE_FLOW_STATUS_LABELS, resolveFlowMessages, type FlowMessage } from '../adapters/line_configuration/line_message_flow_adapter';
import './LineMessageFlow.css';

interface Props {
  active?: boolean;
  configuration?: LineConfigurationQueryClient;
  previews?: LineMessagePreviewClient;
  onOpenMessage(id: string): void;
}

export function LineMessageFlow({ active = true, configuration = lineConfigurationQueryClient, previews = lineMessagePreviewClient, onOpenMessage }: Props) {
  const [journeyId, setJourneyId] = useState('matching');
  const [stageIndex, setStageIndex] = useState<number | null>(null);
  const [expandedNode, setExpandedNode] = useState<string | null>(null);
  const [descriptors, setDescriptors] = useState<PreviewDescriptor[]>([]);
  const [rules, setRules] = useState<LineNotificationRuleModel[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setState('loading');
    void Promise.all([configuration.getNotificationRules({ signal: controller.signal }), previews.catalog({ signal: controller.signal })])
      .then(([catalog, items]) => {
        if (controller.signal.aborted) return;
        setRules(adaptLineNotificationRulesCatalog(catalog).rules);
        setDescriptors(items);
        setState('ready');
      }).catch(() => { if (!controller.signal.aborted) setState('error'); });
    return () => controller.abort();
  }, [active, configuration, previews, reload]);

  if (!active) return null;
  const journey = LINE_MESSAGE_FLOWS.find(item => item.id === journeyId)!;
  const stage = stageIndex === null ? null : journey.stages[stageIndex];
  const openMessage = (message: FlowMessage) => onOpenMessage(message.descriptor.id);
  const selectJourney = (id: string) => { setJourneyId(id); setStageIndex(null); setExpandedNode(null); };
  const statusLabel = (message: FlowMessage) => <span className={`line-flow-message-status ${message.status}`}>{MESSAGE_FLOW_STATUS_LABELS[message.status]}</span>;
  return <section className="line-message-flow" aria-label="LINE 流程圖">
    <header className="line-flow-heading"><div><h2>LINE 流程圖</h2><p>先看流程，點選步驟再看訊息。</p></div><button className="line-secondary-btn" type="button" disabled={state === 'loading'} onClick={() => setReload(value => value + 1)}><RefreshCw size={16} aria-hidden="true" />重新整理</button></header>
    <div className="line-flow-workspace">
      <div className="line-flow-tabs" role="tablist" aria-label="流程類別">{LINE_MESSAGE_FLOWS.map((item, index) => <button type="button" key={item.id} role="tab" tabIndex={item.id === journeyId ? 0 : -1} aria-selected={item.id === journeyId} aria-controls="line-flow-journey" id={`line-flow-tab-${item.id}`} onClick={() => selectJourney(item.id)} onKeyDown={event => {
        const next = event.key === 'ArrowRight' ? (index + 1) % LINE_MESSAGE_FLOWS.length : event.key === 'ArrowLeft' ? (index + LINE_MESSAGE_FLOWS.length - 1) % LINE_MESSAGE_FLOWS.length : event.key === 'Home' ? 0 : event.key === 'End' ? LINE_MESSAGE_FLOWS.length - 1 : null;
        if (next === null) return;
        event.preventDefault(); selectJourney(LINE_MESSAGE_FLOWS[next].id);
        event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
      }}>{item.name}</button>)}</div>
      {journey.summary && <p className="line-flow-journey-summary">{journey.summary}</p>}
      {state === 'loading' ? <p className="line-flow-feedback" role="status">正在讀取正式訊息與啟用狀態…</p> : state === 'error' ? <div className="line-flow-feedback" role="alert"><p>流程訊息暫時無法載入，請重新整理。</p><button type="button" className="line-secondary-btn" onClick={() => setReload(value => value + 1)}>重新載入流程訊息</button></div> : <div id="line-flow-journey" role="tabpanel" aria-labelledby={`line-flow-tab-${journey.id}`}>
        <div className="line-flow-steps" style={{ '--line-flow-stage-count': journey.stages.length } as CSSProperties}>{journey.stages.map((item, index) => {
          const count = item.nodes.reduce((sum, node) => sum + resolveFlowMessages(node, descriptors, rules).length, 0);
          return <div className="line-flow-step-wrap" key={item.title}>
            {index > 0 && <div className="line-flow-line" aria-hidden="true"><ArrowRight size={18} /></div>}
            <button type="button" className={`line-flow-step${stageIndex === index ? ' selected' : ''}`} aria-expanded={stageIndex === index} aria-controls="line-flow-stage-messages" onClick={() => { setStageIndex(stageIndex === index ? null : index); setExpandedNode(null); }}>
              <span className="line-flow-circle">{index + 1}</span><strong>{item.title}</strong><span className={count ? 'line-flow-count' : 'line-flow-no-message'}>{count > 0 && <MessageSquare size={13} aria-hidden="true" />}{count ? `${count} 則訊息` : item.nodes.some(node => !node.internal) ? '缺少訊息設定' : '內部作業'}</span>
            </button>
          </div>;
        })}</div>
        {stage ? <section className="line-flow-details" id="line-flow-stage-messages" aria-label={`${stage.title}的訊息`}><header><div><span>步驟 {stageIndex! + 1}</span><h3>{stage.title}</h3></div><button type="button" aria-label="收合訊息" onClick={() => { setStageIndex(null); setExpandedNode(null); }}><X size={18} /></button></header>
          {stage.nodes.length === 0 ? <p className="line-flow-instruction">由工會人員處理，這個步驟沒有額外的 LINE 通知。</p> : stage.nodes.map(node => {
            if (node.internal) return <article key={node.id} className="line-flow-internal"><strong>{node.title}</strong><span>自助／內部操作</span><p>{node.summary}</p></article>;
            const items = resolveFlowMessages(node, descriptors, rules);
            const single = items.length === 1 ? items[0] : null;
            return <div className="line-flow-message-group" key={node.id}><button type="button" className="line-flow-message-row" disabled={items.length === 0} aria-expanded={!single && items.length > 0 ? expandedNode === node.id : undefined} onClick={() => single ? openMessage(single) : setExpandedNode(expandedNode === node.id ? null : node.id)}>
              <span className="line-flow-row-name">{node.title}</span>{single ? statusLabel(single) : <span className="line-flow-group-count">{items.length ? `${items.length} 則訊息` : '缺少訊息設定'}</span>}<span className="line-flow-row-action">{single ? '調整訊息' : items.length ? '查看訊息' : '尚未設定'}{single ? <ArrowRight size={14} /> : <ChevronDown size={14} className={expandedNode === node.id ? 'expanded' : ''} />}</span>
            </button>{items.length === 0 && <p className="line-flow-node-summary">此訊息的規則或模板尚未設定，請先同步通知設定。</p>}{node.summary && <p className="line-flow-node-summary">{node.summary}</p>}{!single && expandedNode === node.id && <div className="line-flow-nested">{items.map(item => <button type="button" key={item.descriptor.id} onClick={() => openMessage(item)}><span>{item.descriptor.name}</span>{statusLabel(item)}<ArrowRight size={14} aria-hidden="true" /></button>)}</div>}</div>;
          })}
        </section> : <div className="line-flow-instruction" id="line-flow-stage-messages"><MessageSquare size={18} aria-hidden="true" /><p>點選上方步驟，查看這個環節的 LINE 訊息。</p></div>}
      </div>}
    </div>
  </section>;
}
