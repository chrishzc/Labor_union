import { useEffect, useState } from 'react';
import { serviceArrangementStatusClient, type AutomaticCompletionStatus } from '../api/scheduling/service_arrangement_status_client';

export function OrderAutomaticCompletionStatus({ caseNo, revision, onObserved }: { caseNo: string; revision: number; onObserved?: () => void }) {
  const [status, setStatus] = useState<AutomaticCompletionStatus | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    let polling = false;
    let previousStatus: string | null = null;
    const read = async () => {
      if (polling) return;
      polling = true;
      try {
        const result = await serviceArrangementStatusClient.completion(caseNo, controller.signal);
        if (controller.signal.aborted) return;
        setStatus(result); setError('');
        if (previousStatus !== null && result.current_status !== previousStatus) onObserved?.();
        previousStatus = result.current_status;
      } catch (caught) { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '自動完工狀態暫時無法讀取。'); }
      finally { polling = false; }
    };
    void read();
    const timer = window.setInterval(() => void read(), 10000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [caseNo, revision, onObserved]);
  return <section className="service-arrangement-completion" aria-label="自動完工狀態"><dl className="order-v2-business-summary"><div><dt>預計服務完成時間</dt><dd>{status?.completion_instant ? new Intl.DateTimeFormat('zh-TW', { timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(status.completion_instant)) : '排班後顯示'}</dd></div><div><dt>自動完工狀態</dt><dd>{status ? { awaiting_schedule: '等待排班', awaiting_service: '等待進入服務', waiting: '尚未到服務完成時間', due: '已到服務完成時間，等待系統自動完工', blocked: '自動完工暫停，需核對服務資料', completed: '服務已自動完成', cancelled: '訂單已取消' }[status.state] : '讀取中…'}</dd></div></dl>{error && <p role="alert">{error}</p>}{status?.state === 'blocked' && <p role="status">{status.blockers.join('、')}</p>}</section>;
}
