import { useEffect, useState } from 'react';
import { serviceArrangementStatusClient, type AutomaticCompletionStatus } from '../api/scheduling/service_arrangement_status_client';

type CompletionProps = { caseNo: string; revision: number; onObserved?: () => void };

type CompletionRead = { revision: number } & (
  | { kind: 'ready'; status: AutomaticCompletionStatus }
  | { kind: 'refreshing' | 'error'; status: AutomaticCompletionStatus | null }
);

const completionMessages = {
  awaiting_schedule: {
    label: '尚無法確認完工時間',
    detail: '請在「確認服務日期與排班」核對正式排班、最後服務日與服務時段。',
  },
  awaiting_service: {
    label: '等待訂單進入服務',
    detail: '請在「確認服務日期與排班」核對實際開始日與進入服務條件。訂單進入服務後，系統才會評估自動完工。',
  },
  waiting: {
    label: '尚未到服務完成時間',
    detail: '請等候畫面所列時間。到時由系統評估是否符合完工條件。',
  },
  due: {
    label: '已到服務完成時間，等待系統自動完工',
    detail: '請等候系統處理。畫面會自動更新，承辦人無須另行確認。',
  },
  blocked: {
    label: '自動完工受阻',
    detail: '請依下方原因核對資料，系統會在條件符合後重新評估。',
  },
  completed: {
    label: '服務已完成',
    detail: '收付款與結算可至「帳務中心」查閱。',
  },
  cancelled: {
    label: '訂單已取消或終止',
    detail: '系統會停止自動完工。可切換辦理事項查閱案件紀錄。',
  },
} satisfies Record<AutomaticCompletionStatus['state'], { label: string; detail: string }>;

const schedulePanel = '請在「確認服務日期與排班」核對排班資料。';
const completionBlockers = new Map([
  ['auto_complete.effective_generation_missing', '尚無正式排班。請在「確認服務日期與排班」核對排班進度。'],
  ['auto_complete.effective_assignment_facts_inconsistent', '正式排班的月嫂指派缺漏或狀態異常。請在「確認服務日期與排班」核對指派。'],
  ['auto_complete.official_service_days_missing', '正式排班缺少服務日。' + schedulePanel],
  ['auto_complete.official_service_owner_inconsistent', '正式服務日與月嫂指派不符。' + schedulePanel],
  ['auto_complete.official_service_days_duplicated', '正式排班有重複的服務日。' + schedulePanel],
  ['auto_complete.official_service_hours_mismatch', '正式排班的服務總時數與約定總時數不符。' + schedulePanel],
  ['auto_complete.official_service_day_count_mismatch', '正式排班的服務天數與約定天數不符。' + schedulePanel],
  ['auto_complete.actual_end_date_drift', '訂單結束日與最後一個正式服務日不符。' + schedulePanel],
  ['auto_complete.actual_end_date_missing', '訂單缺少實際結束日。請在「確認服務日期與排班」核對最後一個正式服務日。'],
  ['auto_complete.service_time_terms_incomplete', '開始時間、結束時間或跨日設定不完整。請開啟「編輯客戶與訂單資料」核對訂單服務時段。'],
]);
const unknownBlocker = '有其他條件阻擋自動完工。請在「確認服務日期與排班」核對目前資料，並提供案號給系統管理員查核。';

const taipeiCompletionTime = new Intl.DateTimeFormat('zh-TW', {
  timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
});

function formatCompletionTime(instant: string): string {
  const parts = taipeiCompletionTime.formatToParts(new Date(instant));
  const time = parts.filter(({ type }) => type === 'hour' || type === 'minute' || type === 'second')
    .map(({ value }) => value).join(':');
  if (time === '23:59:59' && /\.999999(?:Z|[+-]\d{2}:\d{2})$/.test(instant)) {
    return parts.slice(0, parts.findIndex(({ type }) => type === 'hour')).map(({ value }) => value).join('').trim() + ' 當天結束後（午夜過後）';
  }
  return parts.map(({ value }) => value).join('');
}

export function OrderAutomaticCompletionStatus(props: CompletionProps) {
  return <CaseAutomaticCompletionStatus key={props.caseNo} {...props} />;
}

function CaseAutomaticCompletionStatus({ caseNo, revision, onObserved }: CompletionProps) {
  const [readResult, setReadResult] = useState<CompletionRead | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let polling = false;
    let previousStatus: string | null = null;
    const read = async () => {
      if (polling) return;
      polling = true;
      setReadResult(previous => ({ kind: 'refreshing', revision, status: previous?.status ?? null }));
      try {
        const result = await serviceArrangementStatusClient.completion(caseNo, controller.signal);
        if (controller.signal.aborted) return;
        setReadResult({ kind: 'ready', revision, status: result });
        if (previousStatus !== null && result.current_status !== previousStatus) onObserved?.();
        previousStatus = result.current_status;
      } catch {
        if (!controller.signal.aborted) {
          setReadResult(previous => ({ kind: 'error', revision, status: previous?.status ?? null }));
        }
      } finally {
        polling = false;
      }
    };
    void read();
    const timer = window.setInterval(() => void read(), 10000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [caseNo, revision, onObserved]);
  const readKind = readResult?.revision === revision ? readResult.kind : 'refreshing';
  const status = readResult?.status ?? null;
  const message = status ? completionMessages[status.state] : null;
  const blockerLabels = status && (status.state === 'blocked' || status.state === 'awaiting_schedule')
    ? [...new Set(status.blockers.map(code => completionBlockers.get(code) ?? unknownBlocker))]
    : [];
  if (status?.state === 'blocked' && blockerLabels.length === 0) blockerLabels.push(unknownBlocker);

  return (
    <section className="service-arrangement-completion" aria-label="自動完工狀態">
      {readKind === 'refreshing' && <p role="status">{status ? '正在更新自動完工狀態。下方顯示上次查詢結果。' : '正在讀取自動完工狀態…'}</p>}
      {readKind === 'error' && <p role="alert">暫時無法讀取最新自動完工狀態。{status && '下方顯示上次查詢結果。'}系統會自動重試。若持續失敗，請提供案號給系統管理員查核。</p>}
      {status && message && <>
        <dl className="order-v2-business-summary">
          <div><dt>自動完工狀態</dt><dd>{message.label}</dd></div>
          {status.state !== 'cancelled' && status.state !== 'completed' && (
            <div><dt>最早可自動完工時間（台北）</dt><dd>{status.completion_instant ? formatCompletionTime(status.completion_instant) : '尚無法確認'}</dd></div>
          )}
        </dl>
        <p>{message.detail}</p>
        {blockerLabels.length > 0 && <ul aria-label="待核對事項">{blockerLabels.map(label => <li key={label}>{label}</li>)}</ul>}
      </>}
    </section>
  );
}
