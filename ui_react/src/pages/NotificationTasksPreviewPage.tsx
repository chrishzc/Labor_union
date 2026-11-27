/**
 * File: NotificationTasksPreviewPage.tsx
 * Description: 整合展示各待辦通知來源，支援入帳待辦於列表直接標記已通知消除。
 */
import { ManagementPageHeader } from '../components/ManagementPageHeader';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight, Bell, Check, ChevronLeft, ChevronRight,
  ClipboardCheck, Clock3, ExternalLink, FileText, Inbox, MessageCircle,
  RefreshCw, Search, Send, ShieldCheck, TriangleAlert, Wallet, X,
} from 'lucide-react';
import { notificationTasksClient as client, notificationFailure, notifyNotificationTasksChanged, type NotificationItem, type NotificationPage, type NotificationSource, type NotificationCatalog } from '../api/line_notifications/notification_tasks_client';
import { importFieldIssueHref } from '../api/case_import/import_field_issues';
import { NotificationTaskActions, notificationHref, OptionalImportFieldSkip } from '../components/NotificationTaskActions';
import { useUnsavedNavigation } from '../components/UnsavedChanges';
import { formatTaipeiDateTime } from '../shared/taipeiTime';
import './NotificationTasksPreviewPage.css';

const ALL_TASKS = { id: 'all', label: '全部事項', icon: Inbox };
const LEGACY_GROUP_LABELS = { review: '審核與協調', reminder: '款項與群組', support: '支援' };
const CATEGORY_ICONS = new Map([
  ['applications', ClipboardCheck], ['identity', ShieldCheck], ['coordination', Clock3],
  ['payments', Wallet], ['groups', MessageCircle], ['review', ClipboardCheck], ['reminder', Wallet],
]);
const categoryId = (source: NotificationCatalog[number]) => source.category_id ?? source.group;
const DELIVERY_LABELS: Record<string, string> = {
  pending: '待寄送。請等待系統處理。',
  processing: '寄送中。請等待系統回報結果。',
  retryable_failed: '等待重試。請到「通知與寄送」查看後續進度。',
  sent: '已送出。',
  failed: '寄送失敗。請到「通知與寄送」核對失敗原因。',
  cancelled: '已取消。請到「通知與寄送」查看原寄送紀錄。',
};
const PRIMARY:Record<NotificationSource,string> = {
  registration:'查看申請',identity:'審核身分綁定',
  staff_profile:'審核月嫂資料異動',import_fields:'前往客戶名冊修正',
  customer_binding:'查看人工提醒方式',staff_binding:'查看人工提醒方式',
  followup:'查看月嫂回覆',recommendation:'開啟案件工作區',service_start:'處理換人交接',
  deposit:'發送繳費提醒',payment_receipt:'前往帳務確認',group:'查看建群指令',overdue:'發送提醒',
  delivery:'查看寄送工作',runtime:'前往通知對象設定',
  notification_failure:'處理通知建立異常',
};
type Row = NotificationItem & {caseLabel:string;personLabel:string;primary:string;secondary?:string;tone?:'attention'|'danger'};
function row(item:NotificationItem):Row {
  const caseLabel = item.source==='registration' ? `申請編號：${item.reference_id ?? '未提供'}`
    : item.case_no ?? (item.source==='staff_binding'?'月嫂資料':item.reference_id ? `申請／事項 #${item.reference_id}`:'系統事項');
  return {...item,time:formatTaipeiDateTime(item.time),caseLabel,
    personLabel:'相關對象',
    primary:item.source==='deposit' && item.tag==='已核銷待通知' ? '查看訂金資料' : PRIMARY[item.source],
    secondary:item.source==='payment_receipt' && item.receipt?.amount_ntd != null && item.receipt.source_version != null && item.receipt.source_reference != null
      ? '已於官方帳號發送／標記已通知'
      : item.case_no && ['overdue','deposit'].includes(item.source)?'前往核對款項':item.unavailable_reason?'前往身分與群組設定':undefined,
    tone:item.unavailable_reason || item.source==='delivery' || item.source==='runtime'?'danger':item.source==='overdue'?'attention':undefined};
}
const PAGE_SIZE = 6;
export function NotificationTasksPage() {
  const {requestLeave}=useUnsavedNavigation();
  const [group,setGroup]=useState('all');
  const [search,setSearch]=useState('');
  const [page,setPage]=useState(1);const [selectedId,setSelectedId]=useState('');const [notice,setNotice]=useState('');
  const [catalog,setCatalog]=useState<NotificationCatalog>([]);
  const [pools,setPools]=useState<Partial<Record<NotificationSource,NotificationPage>>>({});
  const [failures,setFailures]=useState<Partial<Record<NotificationSource,string>>>({});
  const [queryError,setQueryError]=useState('');const [loading,setLoading]=useState(true);const [moreBusy,setMoreBusy]=useState(false);
  const [revision,setRevision]=useState(0);const [busy,setBusy]=useState(false);const [expanded,setExpanded]=useState('');
  const detailRef=useRef<HTMLElement>(null);const generation=useRef(0);const locked=useRef(false);
  const intents=useRef<Record<string,string>>({});
  const importFieldReads = useRef({ loadedPages: 1, version: 0 });
  useEffect(()=>{
    const abort=new AbortController();const version=++generation.current;
    importFieldReads.current = { loadedPages: 1, version: 0 };
    setLoading(true);setQueryError('');setFailures({});setPools({});setExpanded('');
    void client.catalog(abort.signal).then(async sources=>{
      if(abort.signal.aborted)return;
      setCatalog(sources);
      setGroup(previous=>previous==='all' || sources.some(source=>categoryId(source)===previous) ? previous : 'all');
      await Promise.all(sources.map(async source=>{
        try {const result=await client.list(source.source,0,abort.signal);if(!abort.signal.aborted && generation.current===version)setPools(old=>({...old,[source.source]:result}));}
        catch(error){if(!abort.signal.aborted && generation.current===version)setFailures(old=>({...old,[source.source]:notificationFailure(error)}));}
      }));
    }).catch(error=>{if(!abort.signal.aborted)setQueryError(notificationFailure(error));}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});
    return()=>abort.abort();
  },[revision]);
  useEffect(()=>{
    const recheck=()=>{if(window.location.hash.split('?')[0]==='#notifications'){setRevision(value=>value+1);}};
    window.addEventListener('hashchange',recheck);
    return()=>window.removeEventListener('hashchange',recheck);
  },[]);
  const refreshSource=useCallback(async(source:NotificationSource)=>{
    const version = generation.current;
    const importRead = source === 'import_fields' ? importFieldReads.current : null;
    const importVersion = importRead ? ++importRead.version : 0;
    const isCurrent = () => version === generation.current && (!importRead || importRead.version === importVersion);
    try {
      let result = await client.list(source);
      const items = [...result.items];
      let loadedPages = 1;
      while (isCurrent() && importRead && loadedPages < importRead.loadedPages && result.next_cursor != null) {
        result = await client.list(source, result.next_cursor);
        items.push(...result.items);
        loadedPages += 1;
      }
      if (!isCurrent()) return;
      if (importRead) {
        importRead.loadedPages = loadedPages;
        importRead.version += 1;
      }
      setPools(old => ({...old, [source]: {...result, items}}));
      setFailures(old => ({...old, [source]: undefined}));
    } catch (error) {
      if (!isCurrent()) return;
      if (importRead) importRead.version += 1;
      setFailures(old => ({...old, [source]: notificationFailure(error)}));
    }
  },[]);
  const refreshAfterCommit=useCallback(async()=>{
    notifyNotificationTasksChanged();
    await Promise.all(catalog.map(({source}) => refreshSource(source)));
  },[catalog,refreshSource]);
  const loaded=catalog.flatMap(source=>pools[source.source]?.items ?? []);
  const coveredTasks=new Set(loaded.flatMap(item=>item.failure?.related_task_ids ?? []));
  const allItems=[...new Map(loaded.filter(item=>item.source!=='delivery' || !coveredTasks.has(item.reference_id!)).map(value=>row(value)).map(item=>[item.id,item])).values()];
  const sourceCategories=new Map(catalog.map(source=>[source.source,categoryId(source)]));
  const categories=new Map(catalog.map(source=>{
    const id=categoryId(source);
    return [id,{id,label:source.category_label ?? LEGACY_GROUP_LABELS[source.group],icon:CATEGORY_ICONS.get(id) ?? ClipboardCheck}];
  }));
  const groupOptions=[ALL_TASKS,...categories.values()];
  const matchesGroup=(source:NotificationSource,id:string)=>id==='all' || sourceCategories.get(source)===id;
  const groupCount=(id:string)=>{
    const sources=catalog.filter(source=>matchesGroup(source.source,id));
    if(loading || queryError || sources.some(({source})=>failures[source] || !pools[source]))return '—';
    const count=allItems.filter(item=>matchesGroup(item.source,id)).length;
    return sources.some(({source})=>pools[source]?.next_cursor!=null) ? `${count}+` : count;
  };
  const filtered=allItems.filter(item=>matchesGroup(item.source,group) && [item.title,item.caseLabel,item.person,item.summary].join(' ').includes(search.trim()));
  const pages=Math.max(1,Math.ceil(filtered.length/PAGE_SIZE));
  const currentPage=Math.min(page,pages);
  const visible=filtered.slice((currentPage-1)*PAGE_SIZE,currentPage*PAGE_SIZE);
  const selected=visible.find(item=>item.id===selectedId) ?? visible[0];
  const selectedCaseNo=selected?.case_no;
  const scopedSources=catalog.filter(s=>matchesGroup(s.source,group));
  const pendingMore=scopedSources.filter(s=>pools[s.source]?.next_cursor!=null);
  const failedSources=scopedSources.filter(s=>failures[s.source]);
  const emptyLoading=loading;
  const emptyError=queryError || (failedSources.length?'目前分類仍有來源無法讀取，請使用來源旁的重試按鈕。':'');
  const emptyTitle=emptyLoading?'讀取中':emptyError?'目前無法完整讀取事項':pendingMore.length?'尚有事項待載入':search.trim()?'沒有符合搜尋條件的事項':'目前沒有待辦事項';
  const emptyMessage=emptyLoading?'正在確認目前事項，請稍候。':emptyError?'無法確認是否還有待辦。已載入的事項仍可使用，請重新整理。':pendingMore.length?'目前這批沒有符合的事項，請載入更多後再確認。':search.trim()?'搜尋只涵蓋已載入事項，可清除搜尋條件後查看。':'此分類目前沒有新事項。可重新整理查看最新結果。';
  const reset=()=>{setSearch('');setGroup('all');setPage(1);setNotice('');setExpanded('');};
  const select=(item:Row)=>requestLeave(()=>{setSelectedId(item.id);setNotice('');setExpanded('');if(window.matchMedia('(max-width: 1000px)').matches)window.requestAnimationFrame(()=>detailRef.current?.scrollIntoView({behavior:'smooth',block:'start'}));});
  const loadMore=async()=>{
    if(moreBusy)return;setMoreBusy(true);const version=generation.current;
    await Promise.all(pendingMore.map(async ({source}) => {
      const cursor = pools[source]?.next_cursor;
      if (cursor == null) return;
      const importRead = source === 'import_fields' ? importFieldReads.current : null;
      const importVersion = importRead?.version;
      const isCurrent = () => version === generation.current && importRead?.version === importVersion;
      try {
        const next = await client.list(source, cursor);
        if (!isCurrent()) return;
        if (importRead) importRead.loadedPages += 1;
        setPools(old => ({...old, [source]: {...next, items: [...new Map([...(old[source]?.items ?? []), ...next.items].map(item => [item.id, item])).values()]}}));
        setFailures(old => ({...old, [source]: undefined}));
      } catch (error) {
        if (isCurrent()) setFailures(old => ({...old, [source]: notificationFailure(error)}));
      }
    }));
    setMoreBusy(false);
  };
  const act=async(item:Row)=>{
    if(locked.current)return;
    if(item.unavailable_reason && ['overdue','deposit'].includes(item.source) && item.tag!=='已核銷待通知')return;
    const href=notificationHref(item);if(href){window.location.hash=href;return;}
    if(item.source==='overdue' || (item.source==='deposit' && item.tag!=='已核銷待通知')) {
      locked.current=true;setBusy(true);setNotice('');intents.current[item.id] ??= crypto.randomUUID();
      try {const id=await client.send(item,intents.current[item.id]);setNotice(`已建立寄送工作 #${id}，尚未證明送達。`);delete intents.current[item.id];await refreshAfterCommit();}
      catch(error){setNotice(notificationFailure(error));}finally{locked.current=false;setBusy(false);}
    }else if(item.source==='deposit')window.location.hash=`#finance?tab=client-receipts&case_no=${encodeURIComponent(item.case_no!)}`;
    else setExpanded(item.id);
  };
  const secondary=async(item:Row)=>{
    if(item.source==='payment_receipt') {
      if(locked.current)return;
      locked.current=true;setBusy(true);setNotice('');
      try {await client.send(item,'');setNotice('已標記入帳通知為已發送，並從待辦清單消除。');await refreshAfterCommit();}
      catch(error){setNotice(notificationFailure(error));}finally{locked.current=false;setBusy(false);}
      return;
    }
    window.location.hash=item.secondary==='前往核對款項'?`#finance?tab=client-receipts&case_no=${encodeURIComponent(item.case_no!)}`
      : item.payment?.payment_stage!=='deposit' && item.source==='overdue'
        ? `#line-management?tab=order_groups&group_q=${encodeURIComponent(item.case_no ?? '')}`:'#line-management?tab=binding';
  };
  return <>
    <ManagementPageHeader className="notification-preview-heading" title={<><Bell size={24} aria-hidden="true" />通知事項</>} description="集中查看需要處理的事項，接續原有工作流程。">
      <div className="notification-preview-heading-actions">
        <span className="notification-preview-eyebrow">工會工作</span>
        <button type="button" className="np-button" disabled={loading || busy} onClick={() => requestLeave(() => { setNotice('');setPage(1);setRevision(value=>value+1); })}><RefreshCw size={16} aria-hidden="true" />重新整理</button>
      </div>
    </ManagementPageHeader>
    <div className="notification-preview-page">

    {(queryError || failedSources.length>0) && <div className="notification-preview-banner" role="alert"><strong>{queryError || failedSources.length===scopedSources.length?'目前無法讀取事項':'部分事項未能載入'}</strong>{queryError && <p>{queryError}</p>}{failedSources.map(s=><p key={s.source}>{s.label}：{failures[s.source]} <button type="button" className="np-button" onClick={()=>void refreshSource(s.source)}>重試{s.label}</button></p>)}</div>}
    {loading && <p role="status">正在讀取待處理事項…</p>}
    <div className="notification-preview-toolbar">
      <div className="notification-preview-groups" role="group" aria-label="事項分類">{groupOptions.map(({ id, label, icon: Icon }) => <button type="button" key={id} aria-pressed={group === id} className={group === id ? 'active' : ''} onClick={() => requestLeave(() => { setGroup(id); setPage(1); setNotice(''); })}><Icon size={15} aria-hidden="true" />{label}<span>{groupCount(id)}</span></button>)}</div>
      <div className="notification-preview-searches"><label className="notification-preview-search"><Search size={17} aria-hidden="true" /><input type="search" aria-label="搜尋通知事項" placeholder="搜尋已載入的事項" value={search} onChange={event => { const value=event.target.value;requestLeave(() => { setSearch(value); setPage(1); setNotice(''); }); }} /></label>
      </div>
    </div>

    <div className="notification-preview-grid">
      <section className="notification-preview-list" aria-label="通知事項清單">
        <div className="notification-preview-list-heading"><strong>待處理事項</strong><span>{`已載入 ${allItems.length} 筆，符合 ${filtered.length} 筆`}</span></div>
        {visible.length ? <div className="notification-preview-rows">{visible.map(item => {
          const Icon = item.tone === 'danger' ? TriangleAlert : item.group === 'review' ? ClipboardCheck : item.group === 'reminder' ? Bell : MessageCircle;
          return <button type="button" key={item.id} data-notification-id={item.id} className={`notification-preview-row${selected?.id === item.id ? ' selected' : ''}`} aria-pressed={selected?.id === item.id} onClick={() => select(item)}>
            <span className={`notification-preview-item-icon ${item.tone ?? ''}`}><Icon size={19} aria-hidden="true" /></span>
            <span className="notification-preview-row-content"><span className="notification-preview-row-title"><strong>{item.title}</strong>{item.source!=='registration' && <span className={`np-tag ${item.tone ?? ''}`}>{item.tag}</span>}</span><span className="notification-preview-row-subject">{item.caseLabel}{item.source!=='registration' && item.person && <><span>·</span>{item.person}</>}</span>{item.source!=='registration' && <span className="notification-preview-row-summary">{item.summary}</span>}{item.time && <span className="notification-preview-row-time"><Clock3 size={12} aria-hidden="true" />{item.time}</span>}</span>
            <ChevronRight className="notification-preview-row-arrow" size={17} aria-hidden="true" />
          </button>;
        })}</div> : <div className="notification-preview-empty"><Inbox size={34} aria-hidden="true" /><h2>{emptyTitle}</h2><p>{emptyMessage}</p>
          {!emptyLoading && emptyError && <button type="button" className="np-button" onClick={()=>requestLeave(()=>{setRevision(value=>value+1);})}>重新讀取事項</button>}
          {search.trim() && <button type="button" className="np-button" onClick={()=>requestLeave(reset)}>清除篩選</button>}</div>}
        {filtered.length > PAGE_SIZE && <nav className="notification-preview-pagination" aria-label="通知事項分頁"><span>第 {currentPage}／{pages} 頁</span><div><button type="button" aria-label="上一頁" disabled={currentPage <= 1} onClick={() => requestLeave(() => { setPage(currentPage-1); setNotice(''); })}><ChevronLeft size={16} /></button><button type="button" aria-label="下一頁" disabled={currentPage >= pages} onClick={() => requestLeave(() => { setPage(currentPage+1); setNotice(''); })}><ChevronRight size={16} /></button></div></nav>}
        {pendingMore.length>0 && <div className="notification-preview-pagination"><span>還有事項尚未載入</span><button type="button" className="np-button" disabled={moreBusy || loading} onClick={()=>void loadMore()}>{moreBusy?'載入中…':'載入更多事項'}</button></div>}
      </section>

      <aside ref={detailRef} className="notification-preview-detail" aria-label="事項詳細內容">
        {selected ? <>
          <div className="notification-preview-detail-heading"><span>事項詳細內容</span>{selected.source!=='registration' && <span className={`np-tag ${selected.tone ?? ''}`}>{selected.tag}</span>}</div>
          <h2>{selected.title}</h2>
          {selected.source!=='registration' && <p className="notification-preview-detail-summary">{selected.summary}</p>}
          <dl className="notification-preview-facts">{selected.source==='registration'
            ? <><div><dt>申請編號</dt><dd>{selected.reference_id ?? '未提供'}</dd></div><div><dt>收件時間</dt><dd>{selected.time || '未提供'}</dd></div></>
            : <><div><dt>案件／申請</dt><dd>{selected.caseLabel}</dd></div>{selected.source !== 'import_fields' && <><div><dt>{selected.personLabel}</dt><dd>{selected.person}</dd></div><div><dt>時間</dt><dd>{selected.time || '未提供'}</dd></div></>}</>}</dl>
          {selected.source!=='registration' && <section className="notification-preview-reason"><h3><FileText size={15} aria-hidden="true" />處理原因</h3><p>{selected.reason}</p></section>}
          {selected.source === 'import_fields' && selectedCaseNo && <section className="notification-preview-reason">
            <h3>待修正欄位</h3>
            <ul>{selected.import_field_issues?.map(issue => <li key={JSON.stringify([issue.source, issue.owner, issue.field, issue.source_field, issue.code, issue.optional_skip_review_identity])}>
              <a href={importFieldIssueHref(selectedCaseNo, issue)}>{issue.message}</a>
              {issue.optional_skip_review_identity && !failures.import_fields && <OptionalImportFieldSkip caseNo={selectedCaseNo} reviewIdentity={issue.optional_skip_review_identity} sourceField={issue.source_field} onCommitted={refreshAfterCommit} />}
            </li>)}</ul>
          </section>}
          {selected.recipient && selected.source!=='customer_binding' && selected.source!=='registration' && <section className="notification-preview-message"><h3><MessageCircle size={15} aria-hidden="true" />{selected.source.endsWith('_binding')?'人工提醒內容':'提醒內容'}</h3><p className="notification-preview-recipient">{selected.source.endsWith('_binding')?'聯絡電話':selected.recipient.includes('群組') ? '案件群組' : '通知對象'}<ArrowRight size={12} aria-hidden="true" /><strong>{selected.recipient}</strong></p>
            <div className="notification-preview-message-bubble">{selected.message ?? '請在下方原流程查看通知內容與寄送結果。'}</div>
          </section>}
          {selected.unavailable_reason && selected.source!=='customer_binding' && selected.source!=='registration' && <div className="notification-preview-blocker" role="note"><p>{selected.unavailable_reason}</p>
            <p>{selected.payment && selected.payment.payment_stage!=='deposit'?'請先核對本案案件群組，完成綁定後按重新整理。':selected.source==='deposit'?'請依下方入口補齊綁定與繳費資料，再按重新整理。':'請先聯絡客戶完成 LINE 綁定，再按重新核對；仍可接續其他可用操作。'}</p>
            <a href={selected.payment && selected.payment.payment_stage!=='deposit' ? `#line-management?tab=order_groups&group_q=${encodeURIComponent(selected.case_no ?? '')}`:'#line-management?tab=binding'}>{selected.payment && selected.payment.payment_stage!=='deposit'?'前往案件群組設定':'前往 LINE 身分綁定'}</a>
            {selected.source==='deposit' && <><a href={`#finance?tab=client-receipts&case_no=${encodeURIComponent(selected.case_no ?? '')}`}>核對繳費資料與到期日</a><a href="#line-management?tab=push_queue">核對通知及繳費頁面設定</a><p>銀行代碼需由系統設定補齊；案件專屬虛擬帳號沿原規則產生。</p></>}
          </div>}
          {selected.delivery_status && <p>最近寄送狀態：{Object.hasOwn(DELIVERY_LABELS, selected.delivery_status)
            ? DELIVERY_LABELS[selected.delivery_status] : '目前無法判讀。請到「通知與寄送」核對最新紀錄。'}</p>}
          <div className="notification-preview-actions">{!['customer_binding','staff_binding'].includes(selected.source) && <button type="button" className="np-button primary" disabled={busy || loading || (!!selected.unavailable_reason && selected.primary.includes('發送'))} onClick={()=>void act(selected)}>{selected.primary.includes('發送')?<Send size={16} aria-hidden="true" />:<ExternalLink size={16} aria-hidden="true" />}{busy?'處理中…':selected.primary}</button>}
            {selected.secondary && selected.source!=='customer_binding' && selected.source!=='registration' && <button type="button" className="np-button" disabled={busy} onClick={()=>void secondary(selected)}>{selected.secondary}<ChevronRight size={15} aria-hidden="true" /></button>}
          </div>
          {(selected.can_dismiss || expanded===selected.id || ['customer_binding','staff_binding'].includes(selected.source)) && <div className="notification-task-operation" key={selected.id}><NotificationTaskActions item={selected} expanded={expanded===selected.id} onCommitted={refreshAfterCommit} /></div>}
          <p className="notification-preview-footnote"><ShieldCheck size={14} aria-hidden="true" />處理完成後，待辦會自動更新。</p>
          {notice && <div className="notification-preview-notice" role="status"><MessageCircle size={17} aria-hidden="true" /><p>{notice}</p><button type="button" aria-label="關閉操作訊息" onClick={() => setNotice('')}><X size={15} aria-hidden="true" /></button></div>}
        </> : <div className="notification-preview-empty detail-empty"><Check size={28} aria-hidden="true" /><p>選擇事項即可查看明細。</p></div>}
      </aside>
    </div>
  </div></>;
}
