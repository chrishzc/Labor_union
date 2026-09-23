import { useEffect, useState, type FC } from 'react';
import {
  officialServiceDateCorrectionClient,
  type OfficialDatePreview,
  type OfficialDateQuery,
  type OfficialDateSelection,
} from '../api/orders/official_service_date_correction_client';

interface Props {
  caseNo: string;
  revision?: number;
  onObserved?: () => void;
}

export const OrderOfficialDateCorrectionPanel: FC<Props> = ({ caseNo, revision, onObserved }) => {
  const [facts, setFacts] = useState<OfficialDateQuery | null>(null);
  const [selections, setSelections] = useState<OfficialDateSelection[]>([]);
  const [preview, setPreview] = useState<OfficialDatePreview | null>(null);
  const [reason, setReason] = useState('');
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    let active = true;
    setFacts(null);
    setPreview(null);
    setMessage('');
    void officialServiceDateCorrectionClient.query(caseNo).then((result) => {
      if (!active) return;
      setFacts(result);
      setSelections(result.assignments.map((item) => ({
        assignment_id: item.assignment_id,
        service_dates: [...item.service_dates],
      })));
    }).catch((error: unknown) => {
      if (active) setMessage(error instanceof Error ? error.message : '正式排班讀取失敗');
    });
    return () => { active = false; };
  }, [caseNo, revision]);

  const changeDate = (assignmentId: number, index: number, value: string) => {
    setSelections((current) => current.map((item) => item.assignment_id === assignmentId
      ? { ...item, service_dates: item.service_dates.map((day, dayIndex) => dayIndex === index ? value : day) }
      : item));
    setPreview(null);
    setKey('');
    setMessage('');
  };

  const createPreview = async () => {
    setBusy(true);
    setMessage('');
    try {
      const result = await officialServiceDateCorrectionClient.preview(caseNo, selections.map((item) => ({
        ...item,
        service_dates: [...item.service_dates].sort(),
      })));
      setPreview(result);
      setKey(crypto.randomUUID());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '更正預覽失敗');
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    if (!preview || !key) return;
    setBusy(true);
    setMessage('');
    try {
      const receipt = await officialServiceDateCorrectionClient.apply(caseNo, preview, reason.trim(), key);
      const fresh = await officialServiceDateCorrectionClient.query(caseNo);
      const observed = new Map(fresh.assignments.map((item) => [item.assignment_id, [...item.service_dates].sort()]));
      const expected = new Map(receipt.effective_assignments.map((item) => [item.assignment_id, [...item.service_dates].sort()]));
      if (fresh.generation_id !== receipt.generation_id || observed.size !== expected.size ||
        [...expected].some(([assignmentId, dates]) => JSON.stringify(observed.get(assignmentId)) !== JSON.stringify(dates))) {
        throw new Error('提交後正式排班回讀不一致，請重新查詢');
      }
      setFacts(fresh);
      setSelections(fresh.assignments.map((item) => ({ assignment_id: item.assignment_id, service_dates: [...item.service_dates] })));
      setPreview(null);
      setKey('');
      setMessage('正式排班日期已更正；重新查詢週報即可看到新週的服務工時。');
      onObserved?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '更正提交或回讀失敗；請重新查詢');
    } finally {
      setBusy(false);
    }
  };

  return <section aria-label={`案件 ${caseNo} 正式排班日期更正`}>
    <h3>正式排班日期更正</h3>
    <p>請逐日核對已完成服務的日期。更正會保留原紀錄，並更新有效排班與下次查詢的週報。</p>
    {facts?.order_status !== '訂單完成' && facts && <p role="status">目前案件尚未完成，不能使用完工後日期更正。</p>}
    {facts?.monetary_change_blocker && <p role="status">此案含特殊薪資或其他金額影響，暫不能用純日期更正。</p>}
    {facts?.assignments.map((assignment) => <fieldset key={assignment.assignment_id} disabled={busy || facts.monetary_change_blocker || facts.order_status !== '訂單完成'}>
      <legend>{assignment.staff_name || `月嫂 ${assignment.staff_id}`}</legend>
      {assignment.service_dates.map((original, index) => <label key={`${assignment.assignment_id}-${index}`}>
        原服務日 {original}　更正為
        <input type="date" aria-label={`${assignment.staff_name} 第 ${index + 1} 個正式服務日`} value={selections.find((item) => item.assignment_id === assignment.assignment_id)?.service_dates[index] ?? original}
          onChange={(event) => changeDate(assignment.assignment_id, index, event.target.value)} />
      </label>)}
    </fieldset>)}
    {facts && <button type="button" disabled={busy || facts.order_status !== '訂單完成' || facts.monetary_change_blocker} onClick={() => void createPreview()}>預覽更正</button>}
    {preview && <div>
      <p>更正後有效日期：{preview.proposed_assignments.flatMap((item) => item.service_dates).sort().join('、')}</p>
      <p>客戶與月嫂金額義務：維持原狀。</p>
      <label>更正原因<input value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} /></label>
      <button type="button" disabled={busy || !reason.trim()} onClick={() => void apply()}>確認更正正式排班</button>
    </div>}
    {message && <p role="status">{message}</p>}
  </section>;
};
