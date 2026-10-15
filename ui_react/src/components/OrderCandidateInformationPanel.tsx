import { useCallback, useEffect, useRef, useState } from 'react';
import { candidateContactPoolClient, createCandidateInformationSendCommand, type CandidateContactPool,
  type CandidateInformationKind, type CandidateInformationSendCommand, type CaseInformationPreview,
  type CaseWeeklyServicePreview } from '../api/scheduling/candidate_contact_pool_client';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { CandidateInquiryDialog } from './CandidateInquiryDialog';
import { CandidatePlannedServiceDates } from './CandidatePlannedServiceDates';
import { CandidateInformationDocument } from './OrderInformationSheets';

export const CANDIDATE_INFORMATION_LABELS = { 1: '服務條件與費用', 2: '照護與飲食需求', 3: '每週服務說明' } as const;
const errorText = (error: unknown) => error instanceof Error ? error.message : '無法讀取寄送內容。';

export function OrderCandidateInformationPanel({ caseNo, initialKind = 1, onClose }: {
  caseNo: string; initialKind?: CandidateInformationKind; onClose: () => void;
}) {
  const [kind, setKind] = useState<CandidateInformationKind>(initialKind);
  const [preview, setPreview] = useState<CaseInformationPreview | null>(null);
  const [weekly, setWeekly] = useState<CaseWeeklyServicePreview | null>(null);
  const [dateState, setDateState] = useState({ dirty: false, busy: false });
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    setPreview(null); setError(null);
    void candidateContactPoolClient.previewCaseInformation(caseNo, kind, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setPreview(data); })
      .catch(reason => { if (!controller.signal.aborted) setError(errorText(reason)); });
    return () => controller.abort();
  }, [caseNo, kind]);
  const updateWeekly = useCallback((data: CaseWeeklyServicePreview | null) => {
    setWeekly(data);
    if (data?.date_basis === 'confirmed') {
      void candidateContactPoolClient.previewCaseInformation(caseNo, 3)
        .then(value => { if (mounted.current) setPreview(value); })
        .catch(reason => { if (mounted.current) setError(errorText(reason)); });
    }
  }, [caseNo]);
  const close = () => {
    if (dateState.busy) return;
    if (!dateState.dirty || window.confirm('預計日期尚未保存，要放棄這次試算並關閉嗎？')) onClose();
  };
  return <CandidateInquiryDialog title="訂單共用資訊" wide busy={dateState.busy} onClose={close}>
    <p className="candidate-inquiry-intro">所有候選月嫂共用這三份訂單內容。寄送請回到候選清單操作。</p>
    <nav className="candidate-information-tabs" aria-label="選擇詢問內容">
      {([1, 2, 3] as const).map(value => <button type="button" key={value} aria-pressed={kind === value}
        disabled={dateState.busy || dateState.dirty} onClick={() => { setKind(value); setWeekly(null); }}>{CANDIDATE_INFORMATION_LABELS[value]}</button>)}
    </nav>
    <div className="candidate-inquiry-dialog-content">
      {!preview && !error && <p role="status">正在讀取訂單內容…</p>}
      {preview && kind !== 3 && <div className="order-information-paper candidate-information-paper"><CandidateInformationDocument kind={kind} sections={preview.line_sections} /></div>}
      {preview && kind === 3 && preview.start_date && <CandidatePlannedServiceDates caseNo={caseNo} startDate={preview.start_date}
        onSharedPreview={updateWeekly} onEditStateChange={setDateState} />}
      {kind === 3 && weekly && <><p>{weekly.date_basis === 'draft' ? '試算日期尚未保存' : weekly.date_basis === 'confirmed' ? '已保存的預計服務日期' : '尚未保存預計服務日期'}</p>
        {weekly.warnings.map(value => <p key={value} role="status">{value}</p>)}
        <div className="candidate-weekly-table"><table><thead><tr><th>週次</th><th>服務期間</th><th>每日時數</th><th>服務天數</th><th>每週時數</th></tr></thead><tbody>{weekly.rows.map(row => <tr key={row.serial_number}>
          <td>{row.serial_number}</td><td>{row.week_start_date} ～ {row.week_end_date}</td><td>{row.service_hours_per_day}</td><td>{row.weekly_work_days}</td><td>{row.weekly_hours}</td>
        </tr>)}</tbody></table></div></>}
      {error && <p role="alert">{error}</p>}
    </div>
  </CandidateInquiryDialog>;
}

export function OrderCandidateInformationSendPanel({ caseNo, candidate, kind, revision, blocked, onSubmit, onClose, onBusyChange, onViewInformation, sendError }: {
  caseNo: string; candidate: CandidateContactPool['candidates'][number]; kind: CandidateInformationKind; revision: number; blocked: boolean;
  onSubmit: (command: CandidateInformationSendCommand) => Promise<boolean | undefined>; onClose: () => void;
  onBusyChange: (busy: boolean) => void; onViewInformation: (kind: CandidateInformationKind) => void; sendError?: string | null;
}) {
  const [command, setCommand] = useState<CandidateInformationSendCommand | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsDates, setNeedsDates] = useState(false);
  const mounted = useRef(true);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onBusyChange(busy); }, [busy, onBusyChange]);
  useEffect(() => () => onBusyChange(false), [onBusyChange]);
  useEffect(() => { heading.current?.focus(); heading.current?.scrollIntoView({ block: 'nearest' }); }, []);
  useEffect(() => {
    const controller = new AbortController();
    setCommand(null); setError(null); setNeedsDates(false); setBusy(true);
    void (async () => {
      try {
        const [preview, fresh] = await Promise.all([
          candidateContactPoolClient.previewCaseInformation(caseNo, kind, { signal: controller.signal }),
          candidateContactPoolClient.query(caseNo, { signal: controller.signal }),
        ]);
        if (controller.signal.aborted) return;
        if (!fresh.candidates.some(value => value.id === candidate.id && value.status === 'active')
          || orderMutationFlowStore.getCandidateInformation(caseNo, candidate.id, kind)) throw new Error('收件人或寄送狀態已變更，請重新讀取候選清單。');
        if (!preview.send_allowed) { setNeedsDates(true); return; }
        const bound = await candidateContactPoolClient.previewInformation(caseNo, candidate.id, kind, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (JSON.stringify(bound.line_sections) !== JSON.stringify(preview.line_sections)) throw new Error('訂單內容已更新，請重新查看這份資訊後再寄送。');
        setCommand(createCandidateInformationSendCommand(caseNo, candidate.id, kind, bound.preview_fingerprint));
      } catch (reason) { if (!controller.signal.aborted) setError(errorText(reason)); }
      finally { if (!controller.signal.aborted) setBusy(false); }
    })();
    return () => controller.abort();
  }, [caseNo, candidate.id, kind, revision]);
  const send = async () => {
    if (!command || busy || blocked) return;
    setBusy(true); setError(null);
    try { if (await onSubmit(command)) onClose(); }
    catch (reason) { if (mounted.current) setError(errorText(reason)); }
    finally { if (mounted.current) setBusy(false); }
  };
  return <section className="candidate-information-send" aria-label="寄送前確認">
    <h4 ref={heading} tabIndex={-1}>寄送{CANDIDATE_INFORMATION_LABELS[kind]}</h4>
    <p>收件月嫂：{candidate.staff_name}；案件：{caseNo}。本次只寄送這一份資訊。</p>
    {busy && <p role="status">正在處理寄送資訊…</p>}
    {needsDates && <p role="status">請先在「查看這份內容」完成並保存預計日期，才能寄送每週服務說明。</p>}
    {error && <p role="alert">{error}</p>}{sendError && <p role="alert">{sendError}</p>}
    <div className="order-case-action-row">
      <button type="button" className="btn-primary-action" disabled={busy || blocked || !command} onClick={() => void send()}>確認寄送{CANDIDATE_INFORMATION_LABELS[kind]}</button>
      <button type="button" disabled={busy || blocked} onClick={() => onViewInformation(kind)}>查看這份內容</button>
      <button type="button" disabled={busy} onClick={onClose}>取消寄送</button>
    </div>
  </section>;
}
