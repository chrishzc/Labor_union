/** Live notification workbench; pending facts and commands stay with their original owners. */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight, Bell, Check, ChevronLeft, ChevronRight,
  ClipboardCheck, Clock3, ExternalLink, FileText, Inbox, MessageCircle,
  RefreshCw, Search, Send, ShieldCheck, TriangleAlert, Wallet, X,
} from 'lucide-react';
import { notificationTasksClient as client, notificationFailure, type NotificationItem, type NotificationPage, type NotificationSource, type NotificationCatalog } from '../api/line_notifications/notification_tasks_client';
import { NotificationTaskActions, notificationHref } from '../components/NotificationTaskActions';
import { lineDeliveryQueryClient } from '../api/line_delivery/line_delivery_query_client';
import type { LineDeliveryStatus, LineDeliverySourceType } from '../api/line_delivery/line_delivery_query_schemas';
import { useUnsavedNavigation } from '../components/UnsavedChanges';
import './NotificationTasksPreviewPage.css';

type Group = 'review' | 'reminder' | 'support';
function deliveryGroup(source:LineDeliverySourceType):Group {
  if(['contract','identity','identity_review','matching','group_invitation'].includes(source))return 'review';
  if(['finance','assignment','follow_schedule','order'].includes(source))return 'reminder';
  return 'support';
}
const GROUPS = [
  { id: 'all', label: '全部事項', icon: Inbox },
  { id: 'review', label: '審核與協調', icon: ClipboardCheck },
  { id: 'reminder', label: '款項與日誌', icon: Wallet },
  { id: 'support', label: '客服與異常', icon: ShieldCheck },
] as const;
const DELIVERY_LABELS:Record<string,string> = {pending:'待寄送',processing:'寄送中',retryable_failed:'等待重試',sent:'已送出',failed:'寄送失敗',cancelled:'已取消'};
const PRIMARY:Record<NotificationSource,string> = {
  registration:'查看申請',identity:'審核身分綁定',profile:'審核資料異動',information:'處理確認與條件',
  customer_binding:'查看人工提醒方式',staff_binding:'查看人工提醒方式',
  followup:'查看月嫂回覆',recommendation:'開啟案件工作區',service_start:'處理日期與代班',
  deposit:'發送繳費提醒',group:'查看建群指令',overdue:'發送提醒',log:'發送提醒',
  customer_service:'查看並回覆客服案件',delivery:'查看寄送工作',runtime:'前往通知對象設定',
  notification_failure:'處理通知建立異常',
};
type Row = NotificationItem & {caseLabel:string;primary:string;secondary?:string;tone?:'attention'|'danger';delivery?:string};
function row(item:NotificationItem,record=false):Row {
  return {...item,caseLabel:item.case_no ?? (item.source==='staff_binding'?'月嫂資料':item.reference_id ? `申請／事項 #${item.reference_id}`:'系統事項'),
    primary:item.source==='deposit' && item.tag==='已核銷待通知' ? '查看訂金資料' : PRIMARY[item.source],
    secondary:item.case_no && ['overdue','deposit'].includes(item.source)?'前往核對款項':item.unavailable_reason?'前往身分與群組設定':undefined,
    tone:item.unavailable_reason || item.source==='delivery' || item.source==='runtime'?'danger':item.source==='overdue'?'attention':undefined,
    delivery:record ? item.delivery_status ?? undefined : undefined};
}
const PAGE_SIZE = 6;
export function NotificationTasksPage() {
  const {requestLeave}=useUnsavedNavigation();
  const [tab,setTab]=useState<'tasks'|'records'>('tasks');
  const [group,setGroup]=useState<Group|'all'>('all');
  const [search,setSearch]=useState('');const [deliveryFilter,setDeliveryFilter]=useState('all');
  const [page,setPage]=useState(1);const [selectedId,setSelectedId]=useState('');const [notice,setNotice]=useState('');
  const [catalog,setCatalog]=useState<NotificationCatalog>([]);
  const [pools,setPools]=useState<Partial<Record<NotificationSource,NotificationPage>>>({});
  const [failures,setFailures]=useState<Partial<Record<NotificationSource,string>>>({});
  const [queryError,setQueryError]=useState('');const [loading,setLoading]=useState(true);const [moreBusy,setMoreBusy]=useState(false);
  const [revision,setRevision]=useState(0);const [busy,setBusy]=useState(false);const [expanded,setExpanded]=useState('');
  const [records,setRecords]=useState<Row[]>([]);const [recordTotal,setRecordTotal]=useState<number|null>(null);const [recordPage,setRecordPage]=useState(1);
  const [recordError,setRecordError]=useState('');const [recordLoading,setRecordLoading]=useState(false);
  const [recordRevision,setRecordRevision]=useState(0);
  const detailRef=useRef<HTMLElement>(null);const generation=useRef(0);const locked=useRef(false);
  const intents=useRef<Record<string,string>>({});
  useEffect(()=>{
    const abort=new AbortController();const version=++generation.current;
    setLoading(true);setQueryError('');setFailures({});setPools({});setExpanded('');
    void client.catalog(abort.signal).then(async sources=>{
      if(abort.signal.aborted)return;setCatalog(sources);
      await Promise.all(sources.map(async source=>{
        try {const result=await client.list(source.source,0,abort.signal);if(!abort.signal.aborted && generation.current===version)setPools(old=>({...old,[source.source]:result}));}
        catch(error){if(!abort.signal.aborted && generation.current===version)setFailures(old=>({...old,[source.source]:notificationFailure(error)}));}
      }));
    }).catch(error=>{if(!abort.signal.aborted)setQueryError(notificationFailure(error));}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});
    return()=>abort.abort();
  },[revision]);
  const refreshSource=useCallback(async(source:NotificationSource)=>{
    const version=generation.current;const result=await client.list(source);
    if(version!==generation.current)return;
    setPools(old=>({...old,[source]:result}));setFailures(old=>({...old,[source]:undefined}));
  },[]);
  const refreshAfterCommit=useCallback(async()=>{
    const version=generation.current;
    // One original command can change several sources (for example a shared
    // assistance ticket). Re-read the bounded owner pages without closing an
    // unfinished coordination panel or pretending a failed read is zero.
    await Promise.all(catalog.map(async({source})=>{
      try {
        const result=await client.list(source);
        if(version===generation.current){setPools(old=>({...old,[source]:result}));setFailures(old=>({...old,[source]:undefined}));}
      }catch(error){if(version===generation.current)setFailures(old=>({...old,[source]:notificationFailure(error)}));}
    }));
    if(version===generation.current){setRecordPage(1);setRecordRevision(value=>value+1);}
  },[catalog]);
  useEffect(()=>{
    if(tab!=='records')return;const abort=new AbortController();setRecordLoading(true);setRecordError('');setRecords([]);
    void lineDeliveryQueryClient.list({page:recordPage,pageSize:PAGE_SIZE,status:deliveryFilter==='all'?undefined:deliveryFilter as LineDeliveryStatus,...(group==='all'?{}:{category:group})},{signal:abort.signal})
      .then(result=>{if(abort.signal.aborted)return;setRecordTotal(result.total);setRecords(result.items.map(task=>row({id:`delivery:${task.task_id}`,source:'delivery',group:deliveryGroup(task.source_type),
        title:'LINE 寄送工作',case_no:null,reference_id:task.task_id,person:'',summary:`寄送工作 #${task.task_id}・${DELIVERY_LABELS[task.status]}`,
        reason:'查看原寄送工作與目前允許的處理方式。',time:task.updated_at,tag:DELIVERY_LABELS[task.status],recipient:null,message:null,
        unavailable_reason:null,expected_version:null,delivery_status:task.status,payment:null,log:null,information:null},true)));})
      .catch(error=>{if(!abort.signal.aborted)setRecordError(notificationFailure(error));}).finally(()=>{if(!abort.signal.aborted)setRecordLoading(false);});
    return()=>abort.abort();
  },[tab,recordPage,deliveryFilter,revision,group,recordRevision]);
  const loaded=catalog.flatMap(source=>pools[source.source]?.items ?? []);
  const coveredTasks=new Set(loaded.flatMap(item=>item.failure?.related_task_ids ?? []));
  const allItems=[...new Map(loaded.filter(item=>item.source!=='delivery' || !coveredTasks.has(item.reference_id!)).map(value=>row(value)).map(item=>[item.id,item])).values()];
  const source=tab==='tasks'?allItems:records;
  const filtered=source.filter(item=>(group==='all'||item.group===group) && [item.title,item.caseLabel,item.person,item.summary].join(' ').includes(search.trim()));
  const pages=Math.max(1,Math.ceil((tab==='records'?(recordTotal??0):filtered.length)/PAGE_SIZE));
  const currentPage=Math.min(tab==='records'?recordPage:page,pages);
  const visible=tab==='records'?filtered:filtered.slice((currentPage-1)*PAGE_SIZE,currentPage*PAGE_SIZE);
  const selected=visible.find(item=>item.id===selectedId) ?? visible[0];
  const scopedSources=catalog.filter(s=>group==='all'||s.group===group);
  const pendingMore=scopedSources.filter(s=>pools[s.source]?.next_cursor!=null);
  const failedSources=scopedSources.filter(s=>failures[s.source]);
  const emptyLoading=tab==='records'?recordLoading:loading;
  const emptyError=tab==='records'?recordError:queryError || (failedSources.length?'目前分類仍有來源無法讀取，請使用來源旁的重試按鈕。':'');
  const emptyTitle=emptyLoading?'讀取中':emptyError?'目前無法完整讀取事項':tab==='tasks' && pendingMore.length?'尚有事項待載入':search.trim()?'沒有符合搜尋條件的事項':tab==='tasks'?'目前沒有待辦事項':'沒有符合條件的事項';
  const emptyMessage=emptyLoading?'正在確認目前事項，請稍候。':emptyError?'目前無法確認是否還有待辦，請重新讀取；已成功載入的資料仍可使用。':tab==='tasks' && pendingMore.length?'目前這批沒有符合的事項，請載入更多後再確認。':search.trim()?'搜尋只涵蓋已載入事項，可清除搜尋條件後查看。':'目前分類已查詢完成；有新事項時，請按重新整理。';
  const reset=()=>{setSearch('');setGroup('all');setDeliveryFilter('all');setPage(1);setRecordPage(1);setNotice('');setExpanded('');};
  const changeTab=(next:typeof tab)=>requestLeave(()=>{setTab(next);reset();});
  const select=(item:Row)=>requestLeave(()=>{setSelectedId(item.id);setNotice('');setExpanded('');if(window.matchMedia('(max-width: 1000px)').matches)window.requestAnimationFrame(()=>detailRef.current?.scrollIntoView({behavior:'smooth',block:'start'}));});
  const loadMore=async()=>{
    if(moreBusy)return;setMoreBusy(true);const version=generation.current;
    await Promise.all(pendingMore.map(async s=>{try {
      const cursor=pools[s.source]!.next_cursor!;const next=await client.list(s.source,cursor);
      if(version===generation.current)setPools(old=>({...old,[s.source]:{...next,items:[...new Map([...(old[s.source]?.items??[]),...next.items].map(item=>[item.id,item])).values()]}}));
      if(version===generation.current)setFailures(old=>({...old,[s.source]:undefined}));
    }catch(error){if(version===generation.current)setFailures(old=>({...old,[s.source]:notificationFailure(error)}));}}));setMoreBusy(false);
  };
  const act=async(item:Row)=>{
    if(locked.current)return;
    if(item.unavailable_reason && ['overdue','log','deposit'].includes(item.source) && item.tag!=='已核銷待通知')return;
    const href=notificationHref(item);if(href){window.location.hash=href;return;}
    if(['overdue','log'].includes(item.source) || (item.source==='deposit' && item.tag!=='已核銷待通知')) {
      locked.current=true;setBusy(true);setNotice('');intents.current[item.id] ??= crypto.randomUUID();
      try {const id=await client.send(item,intents.current[item.id]);setNotice(`已建立寄送工作 #${id}，尚未證明送達。`);delete intents.current[item.id];await refreshAfterCommit();}
      catch(error){setNotice(notificationFailure(error));}finally{locked.current=false;setBusy(false);}
    }else if(item.source==='deposit')window.location.hash=`#finance?tab=client-receipts&case_no=${encodeURIComponent(item.case_no!)}`;
    else setExpanded(item.id);
  };
  const secondary=(item:Row)=>{
    window.location.hash=item.secondary==='前往核對款項'?`#finance?tab=client-receipts&case_no=${encodeURIComponent(item.case_no!)}`
      : item.source==='log' || item.payment?.payment_stage!=='deposit' && item.source==='overdue'
        ? `#line-management?tab=order_groups&group_q=${encodeURIComponent(item.case_no ?? '')}`:'#line-management?tab=binding';
  };
  return <div className="notification-preview-page">
    <header className="notification-preview-heading">
      <div><p className="notification-preview-eyebrow">工會工作</p><h1><Bell aria-hidden="true" />通知事項</h1><p>集中查看需要處理的事項，接續原有工作流程。</p></div>
      <button type="button" className="np-button" disabled={loading || busy} onClick={() => requestLeave(() => { setNotice('');setPage(1);setRevision(value=>value+1); })}><RefreshCw size={16} aria-hidden="true" />重新整理</button>
    </header>

    {tab==='tasks' && (queryError || failedSources.length>0) && <div className="notification-preview-banner" role="alert"><strong>{queryError || failedSources.length===scopedSources.length?'目前無法讀取事項':'部分事項未能載入'}</strong>{queryError && <p>{queryError}</p>}{failedSources.map(s=><p key={s.source}>{s.label}：{failures[s.source]} <button type="button" className="np-button" onClick={()=>void refreshSource(s.source).catch(error=>setFailures(old=>({...old,[s.source]:notificationFailure(error)})))}>重試{s.label}</button></p>)}</div>}
    {loading && <p role="status">正在讀取待處理事項…</p>}
    {tab==='records' && recordError && <p role="alert">{recordError}</p>}
    {tab==='records' && recordLoading && <p role="status">正在讀取寄送紀錄…</p>}

    <nav className="notification-preview-tabs" aria-label="通知事項檢視">
      <button type="button" aria-pressed={tab === 'tasks'} className={tab === 'tasks' ? 'active' : ''} onClick={() => changeTab('tasks')}>需要處理<span>{loading?'—':allItems.length}{catalog.some(s=>pools[s.source]?.next_cursor!=null)?'+':''}</span></button>
      <button type="button" aria-pressed={tab === 'records'} className={tab === 'records' ? 'active' : ''} onClick={() => changeTab('records')}>寄送紀錄<span>{recordLoading?'—':recordTotal??'—'}</span></button>
    </nav>

    <div className="notification-preview-toolbar">
      <div className="notification-preview-groups" role="group" aria-label="事項分類">{GROUPS.map(({ id, label, icon: Icon }) => <button type="button" key={id} aria-pressed={group === id} className={group === id ? 'active' : ''} onClick={() => requestLeave(() => { setGroup(id); setPage(1);setRecordPage(1); setNotice(''); })}><Icon size={15} aria-hidden="true" />{label}<span>{tab==='records'?(id===group?(recordLoading?'—':recordTotal??'—'):'—'):source.filter(item => id === 'all' || item.group === id).length}</span></button>)}</div>
      <div className="notification-preview-searches"><label className="notification-preview-search"><Search size={17} aria-hidden="true" /><input type="search" aria-label="搜尋通知事項" placeholder="搜尋已載入的事項" value={search} onChange={event => { const value=event.target.value;requestLeave(() => { setSearch(value); setPage(1); setNotice(''); }); }} /></label>
        {tab === 'records' && <select aria-label="寄送狀態" value={deliveryFilter} onChange={event => { setDeliveryFilter(event.target.value); setPage(1); setRecordPage(1); setNotice(''); }}><option value="all">全部寄送狀態</option>{Object.entries(DELIVERY_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>}
      </div>
    </div>

    <div className="notification-preview-grid">
      <section className="notification-preview-list" aria-label="通知事項清單">
        <div className="notification-preview-list-heading"><strong>{tab === 'tasks' ? '待處理事項' : '寄送紀錄'}</strong><span>{tab==='records'?(recordLoading?'查詢中…':recordError?'目前無法取得筆數':`共 ${recordTotal??0} 筆`):`已載入 ${allItems.length} 筆，符合 ${filtered.length} 筆`}</span></div>
        {visible.length ? <div className="notification-preview-rows">{visible.map(item => {
          const Icon = item.tone === 'danger' ? TriangleAlert : item.group === 'review' ? ClipboardCheck : item.group === 'reminder' ? Bell : MessageCircle;
          return <button type="button" key={item.id} data-notification-id={item.id} className={`notification-preview-row${selected?.id === item.id ? ' selected' : ''}`} aria-pressed={selected?.id === item.id} onClick={() => select(item)}>
            <span className={`notification-preview-item-icon ${item.tone ?? ''}`}><Icon size={19} aria-hidden="true" /></span>
            <span className="notification-preview-row-content"><span className="notification-preview-row-title"><strong>{item.title}</strong><span className={`np-tag ${item.tone ?? ''}${item.delivery === 'sent' ? ' success' : ''}`}>{item.tag}</span></span><span className="notification-preview-row-subject">{item.caseLabel}<span>·</span>{item.person}</span><span className="notification-preview-row-summary">{item.summary}</span><span className="notification-preview-row-time"><Clock3 size={12} aria-hidden="true" />{item.time}</span></span>
            <ChevronRight className="notification-preview-row-arrow" size={17} aria-hidden="true" />
          </button>;
        })}</div> : <div className="notification-preview-empty"><Inbox size={34} aria-hidden="true" /><h2>{emptyTitle}</h2><p>{emptyMessage}</p>
          {!emptyLoading && emptyError && <button type="button" className="np-button" onClick={()=>requestLeave(()=>{if(tab==='tasks')setRevision(value=>value+1);else setRecordRevision(value=>value+1);})}>重新讀取事項</button>}
          {search.trim() && <button type="button" className="np-button" onClick={()=>requestLeave(reset)}>清除篩選</button>}</div>}
        {(tab==='records'?(recordTotal??0):filtered.length) > PAGE_SIZE && <nav className="notification-preview-pagination" aria-label="通知事項分頁"><span>第 {currentPage}／{pages} 頁</span><div><button type="button" aria-label="上一頁" disabled={currentPage <= 1} onClick={() => requestLeave(() => { tab==='records'?setRecordPage(currentPage-1):setPage(currentPage-1); setNotice(''); })}><ChevronLeft size={16} /></button><button type="button" aria-label="下一頁" disabled={currentPage >= pages} onClick={() => requestLeave(() => { tab==='records'?setRecordPage(currentPage+1):setPage(currentPage+1); setNotice(''); })}><ChevronRight size={16} /></button></div></nav>}
        {tab==='tasks' && pendingMore.length>0 && <div className="notification-preview-pagination"><span>還有事項尚未載入</span><button type="button" className="np-button" disabled={moreBusy || loading} onClick={()=>void loadMore()}>{moreBusy?'載入中…':'載入更多事項'}</button></div>}
      </section>

      <aside ref={detailRef} className="notification-preview-detail" aria-label="事項詳細內容">
        {selected ? <>
          <div className="notification-preview-detail-heading"><span>事項詳細內容</span><span className={`np-tag ${selected.tone ?? ''}`}>{selected.tag}</span></div>
          <h2>{selected.title}</h2>
          <p className="notification-preview-detail-summary">{selected.summary}</p>
          <dl className="notification-preview-facts"><div><dt>案件／申請</dt><dd>{selected.caseLabel}</dd></div><div><dt>相關對象</dt><dd>{selected.person}</dd></div><div><dt>時間</dt><dd>{selected.time || '未提供'}</dd></div></dl>
          <section className="notification-preview-reason"><h3><FileText size={15} aria-hidden="true" />{selected.delivery ? '寄送狀況' : '為什麼需要處理'}</h3><p>{selected.reason}</p>{selected.delivery && <p className="notification-preview-delivery-state">目前狀態：{DELIVERY_LABELS[selected.delivery]}</p>}</section>
          {selected.recipient && <section className="notification-preview-message"><h3><MessageCircle size={15} aria-hidden="true" />{selected.source.endsWith('_binding')?'人工提醒內容':'提醒內容'}</h3><p className="notification-preview-recipient">{selected.source.endsWith('_binding')?'聯絡電話':selected.recipient.includes('群組') ? '案件群組' : '通知對象'}<ArrowRight size={12} aria-hidden="true" /><strong>{selected.recipient}</strong></p>
            <div className="notification-preview-message-bubble">{selected.message ?? '請在下方原流程查看通知內容與寄送結果。'}</div>
          </section>}
          {selected.unavailable_reason && <div className="notification-preview-blocker" role="note"><p>{selected.unavailable_reason}</p>
            <p>{selected.source==='log' || selected.payment && selected.payment.payment_stage!=='deposit'?'請先核對本案案件群組，完成綁定後按重新整理。':selected.source==='deposit'?'請依下方入口補齊綁定與繳費資料，再按重新整理。':'請先聯絡客戶完成 LINE 綁定，再按重新核對；仍可接續其他可用操作。'}</p>
            <a href={selected.source==='log' || selected.payment && selected.payment.payment_stage!=='deposit' ? `#line-management?tab=order_groups&group_q=${encodeURIComponent(selected.case_no ?? '')}`:'#line-management?tab=binding'}>{selected.source==='log' || selected.payment && selected.payment.payment_stage!=='deposit'?'前往案件群組設定':'前往 LINE 身分綁定'}</a>
            {selected.source==='deposit' && <><a href={`#finance?tab=client-receipts&case_no=${encodeURIComponent(selected.case_no ?? '')}`}>核對繳費資料與到期日</a><a href="#line-management?tab=push_queue">核對通知及繳費頁面設定</a><p>銀行代碼需由系統設定補齊；案件專屬虛擬帳號沿原規則產生。</p></>}
          </div>}
          {selected.delivery_status && !selected.delivery && <p>最近寄送狀態：{DELIVERY_LABELS[selected.delivery_status] ?? selected.delivery_status}</p>}
          <div className="notification-preview-actions"><button type="button" className="np-button primary" disabled={busy || loading || (!!selected.unavailable_reason && selected.primary.includes('發送'))} onClick={()=>void act(selected)}>{selected.primary.includes('發送')?<Send size={16} aria-hidden="true" />:<ExternalLink size={16} aria-hidden="true" />}{busy?'處理中…':selected.primary}</button>
            {selected.secondary && <button type="button" className="np-button" disabled={busy} onClick={()=>secondary(selected)}>{selected.secondary}<ChevronRight size={15} aria-hidden="true" /></button>}
          </div>
          {expanded===selected.id && <div className="notification-task-operation" key={selected.id}><NotificationTaskActions item={selected} sourceReadError={failures[selected.source]} onCommitted={refreshAfterCommit} /></div>}
          <p className="notification-preview-footnote"><ShieldCheck size={14} aria-hidden="true" />沿用原流程處理，結果更新後同步待辦。</p>
          {notice && <div className="notification-preview-notice" role="status"><MessageCircle size={17} aria-hidden="true" /><p>{notice}</p><button type="button" aria-label="關閉操作訊息" onClick={() => setNotice('')}><X size={15} aria-hidden="true" /></button></div>}
        </> : <div className="notification-preview-empty detail-empty"><Check size={28} aria-hidden="true" /><p>選擇事項後，在這裡查看詳細內容。</p></div>}
      </aside>
    </div>
  </div>;
}
