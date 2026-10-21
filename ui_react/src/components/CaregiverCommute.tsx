import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from 'react';
import { commuteClient, type CommuteHistory, type CommuteRoute, type CommuteUsage } from '../api/scheduling/commute_client';
import { sessionClient } from '../api/auth/session_client';
import './CaregiverCommute.css';

let usage: CommuteUsage | null = null;
let usageRevision = 0;
let historyRevision = 0;
type QueryState = { busy: boolean; result: CommuteRoute | null; error: string; pendingKey: string | null };
const emptyQuery: QueryState = { busy: false, result: null, error: '', pendingKey: null };
let queries = new Map<string, QueryState>();
let activeSession = sessionClient.getToken();
let queryGeneration = 0;
let snapshot = { usage, error: '', historyRevision, queries } as {
  usage: CommuteUsage | null; error: string; historyRevision: number; queries: ReadonlyMap<string, QueryState>;
};
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
function getSnapshot() {
  const session = sessionClient.getToken();
  if (session !== activeSession) {
    activeSession = session;
    ++queryGeneration;
    queries = new Map();
    snapshot = { ...snapshot, queries };
  }
  return snapshot;
}
function publish(error = snapshot.error) { snapshot = { usage, error, historyRevision, queries }; listeners.forEach(listener => listener()); }
function setQuery(identity: string, state: QueryState) {
  queries = new Map(queries).set(identity, state);
  publish();
}
async function queryCommute(caseNo: string, staffId: number) {
  const identity = `${caseNo}:${staffId}`;
  const previous = getSnapshot().queries.get(identity) ?? emptyQuery;
  if (previous.busy) return;
  const generation = queryGeneration;
  const eventKey = previous.pendingKey ?? crypto.randomUUID();
  setQuery(identity, { ...previous, busy: true, error: '', pendingKey: eventKey });
  try {
    // The user's single request continues when its card unmounts; reopening must
    // observe the same operation rather than abandon it and send another one.
    const result = await commuteClient.query(caseNo, staffId, eventKey);
    getSnapshot();
    if (generation === queryGeneration) setQuery(identity, { busy: false, result, error: '', pendingKey: null });
  } catch (cause) {
    getSnapshot();
    if (generation === queryGeneration) setQuery(identity, { ...previous, busy: false, pendingKey: eventKey,
      error: `${cause instanceof Error ? cause.message : '通勤查詢失敗。'} 若結果未明，請以原操作確認，避免重複查詢。` });
  } finally {
    if (generation === queryGeneration) {
      ++historyRevision; publish();
      void refreshUsage();
    }
  }
}
async function refreshUsage() {
  const revision = ++usageRevision;
  try {
    const current = await commuteClient.usage();
    if (revision === usageRevision) { usage = current; publish(''); }
  } catch {
    if (revision === usageRevision) publish('用量讀取失敗，請重新讀取；目前無法確認剩餘額度。');
  }
}
const time = (value: string) => new Date(value).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei', hour12: false });

export function CommuteHistoryPanel({ caseNo }: { caseNo: string }) {
  return <HistoryForCase key={caseNo} caseNo={caseNo} />;
}

function HistoryForCase({ caseNo }: { caseNo: string }) {
  const current = useSyncExternalStore(subscribe, getSnapshot);
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<{ status: 'loading' | 'ready' | 'failed'; data: CommuteHistory | null }>({ status: 'loading', data: null });
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading', data: null });
    void commuteClient.history(caseNo, controller.signal).then(data => {
      if (!controller.signal.aborted) setState({ status: 'ready', data });
    }).catch(() => {
      if (!controller.signal.aborted) setState({ status: 'failed', data: null });
    });
    return () => controller.abort();
  }, [caseNo, current.historyRevision, refresh]);
  return <section className="commute-history" aria-label="本案機車通勤查詢紀錄">
    <div className="commute-usage-heading"><strong>本案機車通勤查詢紀錄</strong>
      <button type="button" disabled={state.status === 'loading'} onClick={() => setRefresh(value => value + 1)}>重新讀取紀錄</button>
    </div>
    <p>最近 50 筆，最新在前；時間為台灣時間。讀取紀錄不增加 Google 用量。</p>
    {state.status === 'loading' ? <p role="status">正在讀取查詢紀錄…</p>
      : state.status === 'failed' ? <p role="alert">查詢紀錄讀取失敗，請重新讀取；無法確認是否曾經查詢，請勿立即重查。</p>
      : !state.data?.records.length ? <p>本案尚無機車通勤查詢紀錄。</p>
      : <div className="commute-history-scroll"><table>
        <thead><tr><th scope="col">查詢時間</th><th scope="col">月嫂</th><th scope="col">結果</th></tr></thead>
        <tbody>{state.data.records.map(record => <tr key={record.record_id}>
          <td><time dateTime={record.queried_at}>{time(record.queried_at)}</time></td>
          <td>{record.staff_name ?? `月嫂編號 ${record.staff_id}（名冊資料已不存在）`}</td>
          <td><strong>{record.status === 'succeeded' ? '成功' : record.status === 'failed' ? '失敗' : '待確認'}</strong><p>{record.message}</p></td>
        </tr>)}</tbody>
      </table></div>}
  </section>;
}

export function CommuteUsagePanel() {
  const current = useSyncExternalStore(subscribe, getSnapshot);
  const [count, setCount] = useState('');
  const [through, setThrough] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; void refreshUsage(); return () => { mounted.current = false; }; }, []);
  const reconcile = async (event: FormEvent) => {
    event.preventDefault();
    if (!current.usage || saving) return;
    setSaving(true); setMessage('');
    try {
      const next = await commuteClient.reconcile(current.usage.billing_month, Number(count), new Date(`${through}+08:00`).toISOString());
      ++usageRevision; usage = next; publish('');
      if (mounted.current) setMessage('已登錄人工核對用量。');
    } catch (error) {
      if (mounted.current) setMessage(error instanceof Error ? error.message : '核對用量保存失敗。');
    } finally { if (mounted.current) setSaving(false); }
  };
  const data = current.usage;
  return <aside className="commute-usage" aria-label="本月機車通勤查詢用量">
    <div className="commute-usage-heading"><strong>本月機車通勤查詢用量</strong><button type="button" onClick={() => { void refreshUsage(); }}>重新讀取用量</button></div>
    {current.error ? <p role="alert">{current.error}</p> : !data ? <p role="status">正在讀取用量…</p> : <>
      <p>{data.billing_month} · 免費額度已用 <strong>{data.free_used.toLocaleString()} / {data.free_limit.toLocaleString()}</strong> 次 · 剩餘 <strong>{data.free_remaining.toLocaleString()}</strong> 次（保守估算）</p>
      {data.uncertain_requests > 0 && <p>另有 {data.uncertain_requests.toLocaleString()} 次計費待確認，已保守扣除可用次數。</p>}
      {data.paid_requests > 0 && <p>已超過免費額度，超額估計 {data.paid_requests.toLocaleString()} 次，費用約 US${data.estimated_cost_usd}（未稅）。</p>}
      {!data.configured && <p role="status">尚未設定 Google Routes API，完成設定後才能查詢距離。</p>}
      <details><summary>用量明細與帳務核對</summary>
        <p>本系統已受理 {data.local_requests.toLocaleString()} 次；計費待確認 {data.uncertain_requests.toLocaleString()} 次；超額估計 {data.paid_requests.toLocaleString()} 次，費用約 US${data.estimated_cost_usd}（未稅）。</p>
        <p>按 Google 美國太平洋時間每月歸零。數字為估算，最終以 Google 帳務為準；其他系統共用的用量須一併核對。</p>
        {data.verified_count === null ? <p>Google 帳務：尚未人工核對。</p> : <p>Google 帳務人工核對：{data.verified_count.toLocaleString()} 次，截至 {time(data.verified_through!)}；登錄時間 {time(data.verified_at!)}（台灣時間）。</p>}
        <p>請核對同一 Google 帳務帳戶、本月 Compute Routes Enterprise 的全部用量，包含其他專案及免費部分。截止時間之後，本系統新增查詢會另外加計。</p>
        <form onSubmit={event => { void reconcile(event); }}>
          <label>Google 本月累計用量（次）<input type="number" min="0" step="1" required value={count} disabled={saving} onChange={event => setCount(event.target.value)} /></label>
          <label>報表統計截止時間（台灣時間）<input type="datetime-local" required value={through} disabled={saving} onChange={event => setThrough(event.target.value)} /></label>
          <button type="submit" disabled={saving}>{saving ? '保存中…' : '保存核對用量'}</button>
        </form>
        {message && <p role="status">{message}</p>}
      </details>
    </>}
  </aside>;
}

export function CaregiverCommuteQuery(props: { caseNo: string; staffId: number; staffName: string }) {
  return <SingleCommuteQuery key={`${props.caseNo}:${props.staffId}`} {...props} />;
}
function SingleCommuteQuery({ caseNo, staffId, staffName }: { caseNo: string; staffId: number; staffName: string }) {
  const current = useSyncExternalStore(subscribe, getSnapshot);
  const { busy, result, error, pendingKey } = current.queries.get(`${caseNo}:${staffId}`) ?? emptyQuery;
  return <div className="caregiver-commute" aria-label={`${staffName}機車通勤`}>
    <button type="button" disabled={busy || current.usage?.configured === false} onClick={() => { void queryCommute(caseNo, staffId); }}>
      {busy ? '查詢機車通勤中…' : pendingKey ? '確認原查詢操作' : result ? '重新查詢機車通勤（增加用量）' : '查詢機車通勤'}
    </button>
    {error && <p role="alert">{error}</p>}
    {result && <div role="status">
      {result.status === 'ready' && result.distance_meters !== null && result.duration_seconds !== null
        ? <p><strong>機車單程 {(result.distance_meters / 1000).toFixed(1)} 公里 · 預估 {Math.ceil(result.duration_seconds / 60)} 分鐘</strong></p>
        : <p>{result.message}</p>}
      {result.status === 'ready' && result.message && <p>{result.message}</p>}
      <p>查詢時間：{time(result.queried_at)} · Google Maps</p>
      <p>同一分頁內保留上次結果；地址或路況改變時，請手動重新查詢。</p>
      {result.status === 'ready' && <p>機車路線仍在測試，可能有路線資訊不完整；請依現場道路標誌確認。</p>}
    </div>}
    {!result && !error && <span>月嫂名冊地址 → 本案客戶地址；逐位手動查詢。</span>}
  </div>;
}
