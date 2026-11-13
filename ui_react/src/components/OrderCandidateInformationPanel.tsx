import { staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';
import { useCallback, useEffect, useRef, useState } from 'react';
import { candidateContactPoolClient, createCandidateInformationSendCommand, type CandidateContactPool, type CandidateInformationPackagePreview,
  type CandidateInformationKind, type CandidateInformationSendCommand, type CaseInformationPreview,
  type CaseWeeklyServicePreview } from '../api/scheduling/candidate_contact_pool_client';
import { CandidateInquiryDialog } from './CandidateInquiryDialog';
import { CandidatePlannedServiceDates } from './CandidatePlannedServiceDates';
import { CandidateInformationDocument } from './OrderInformationSheets';

export const CANDIDATE_INFORMATION_LABELS = { 1: '服務條件與費用', 2: '照護與飲食需求', 3: '每週服務說明' } as const;
const errorText = (error: unknown) => error instanceof Error ? error.message : '無法讀取寄送內容。';

export function CandidateWeeklyServiceTable({ weekly }: { weekly: CaseWeeklyServicePreview }) {
  return <>
    {weekly.warnings.map(value => <p key={value} role="status">{value}</p>)}
    {weekly.rows.length > 0 && <div className="candidate-weekly-table"><table><thead><tr><th>週次</th><th>服務期間</th><th>每日時數</th><th>服務天數</th><th>每週時數</th></tr></thead><tbody>{weekly.rows.map(row => <tr key={row.serial_number}>
      <td>{row.serial_number}</td><td>{row.week_start_date} ～ {row.week_end_date}</td><td>{row.service_hours_per_day}</td><td>{row.weekly_work_days}</td><td>{row.weekly_hours}</td>
    </tr>)}</tbody></table></div>}
  </>;
}

export function OrderCandidateInformationPanel({ caseNo, initialKind = 1, onClose, onDatesSaved }: {
  caseNo: string; initialKind?: CandidateInformationKind; onClose: () => void; onDatesSaved?: () => void;
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
    if (!dateState.dirty || window.confirm('預計日期尚未儲存。要放棄這次試算並關閉嗎？')) onClose();
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
        onSharedPreview={updateWeekly} onEditStateChange={setDateState} onSaved={onDatesSaved} />}
      {kind === 3 && weekly && <><p>{weekly.date_basis === 'draft' ? '試算日期尚未保存' : weekly.date_basis === 'confirmed' ? '已保存的預計服務日期' : '尚未保存預計服務日期'}</p>
        <CandidateWeeklyServiceTable weekly={weekly} /></>}
      {error && <p role="alert">{error}</p>}
    </div>
  </CandidateInquiryDialog>;
}

type ReplyCard = Pick<CandidateInformationPackagePreview, 'reply_text' | 'reply_actions'>;
type InformationDocument = Pick<CaseInformationPreview, 'info_type' | 'line_sections'>;

export function CandidateInformationPages({ documents, reply }: { documents: InformationDocument[]; reply?: ReplyCard }) {
  const [page, setPage] = useState(0);
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const pages = ['訂單資訊一', '訂單資訊二', '每週服務說明'];
  if (reply) pages.push('共用回覆卡');
  const current = Math.min(page, pages.length - 1);
  const document = documents.find(part => part.info_type === current + 1);
  return <div className="candidate-package-pages">
    <nav className="candidate-information-tabs" aria-label="選擇訊息頁面">
      {pages.map((label, index) => <button key={label} type="button" aria-pressed={current === index} onClick={() => setPage(index)}>{label}</button>)}
    </nav>
    <div className="candidate-package-message"
      onTouchStart={event => { const touch = event.touches[0]; touchStart.current = event.touches.length === 1 && touch ? { x: touch.clientX, y: touch.clientY } : null; }}
      onTouchCancel={() => { touchStart.current = null; }}
      onTouchEnd={event => {
        const start = touchStart.current;
        const touch = event.changedTouches[0];
        touchStart.current = null;
        if (!start || !touch) return;
        const dx = touch.clientX - start.x;
        if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(touch.clientY - start.y)) {
          setPage(Math.max(0, Math.min(pages.length - 1, current + (dx < 0 ? 1 : -1))));
        }
      }}>
      <div className="candidate-package-header"><span>LINE 訊息預覽</span><span aria-live="polite">第 {current + 1} 頁，共 {pages.length} 頁</span></div>
      <div className="candidate-package-bubble">
        {document?.line_sections.map((section, index) => <section key={index}>
          <h5>{section.title}</h5>
          <dl>{section.rows.map(([label, value], row) => <div key={row}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
        </section>)}
        {current === 2 && !document && <p role="status">服務日期尚未保存或與約定天數不符，暫無可寄送的週安排。</p>}
        {current === 3 && reply && <>
          <h5>接案意願確認</h5>
          {reply.reply_text.map((line, index) => <p key={index}>{line}</p>)}
          {reply.reply_actions.map((label, index) => <span className="candidate-package-reply" key={index}>{label}</span>)}
        </>}
      </div>
      <nav className="candidate-package-header" aria-label="訊息翻頁">
        <button type="button" disabled={current === 0} onClick={() => setPage(current - 1)}>上一頁</button>
        <button type="button" disabled={current === pages.length - 1} onClick={() => setPage(current + 1)}>下一頁</button>
      </nav>
    </div>
  </div>;
}

export function OrderCandidateInformationSendPanel({ caseNo, candidate, revision, blocked, onSubmit, onClose, onViewDates, sendError, resend = false, datesReady = true }: {
  caseNo: string; candidate: CandidateContactPool['candidates'][number]; revision: number; blocked: boolean;
  resend?: boolean;
  datesReady?: boolean;
  onSubmit: (command: CandidateInformationSendCommand) => Promise<boolean | undefined>;
  onClose: () => void; onViewDates: () => void; sendError?: string | null;
}) {
  const [preview, setPreview] = useState<CandidateInformationPackagePreview | null>(null);
  const [sending, setSending] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); heading.current?.scrollIntoView?.({ block: 'nearest' }); }, []);
  useEffect(() => {
    const controller = new AbortController();
    setPreview(null);
    setError(null);
    void candidateContactPoolClient.previewInformationPackage(caseNo, candidate.id, { signal: controller.signal, resend })
      .then(data => { if (!controller.signal.aborted) setPreview(data); })
      .catch(reason => { if (!controller.signal.aborted) setError(errorText(reason)); });
    return () => controller.abort();
  }, [caseNo, candidate.id, revision, resend]);

  const confirm = async () => {
    if (!preview?.preview_fingerprint || !datesReady || blocked || inFlight.current) return;
    inFlight.current = true;
    setSending(true);
    try {
      const command = createCandidateInformationSendCommand(caseNo, candidate.id, preview.preview_fingerprint, resend);
      if (await onSubmit(command)) onClose();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      inFlight.current = false;
      setSending(false);
    }
  };

  return <section className="candidate-information-send" aria-label="寄送預覽">
    <header className="candidate-package-header">
      <div>
        <h4 ref={heading} tabIndex={-1}>寄送預覽</h4>
        <p>收件月嫂 {staffDisplayLabel(candidate.staff_union_no, candidate.staff_name)}</p>
      </div>
      <button type="button" disabled={blocked || sending} onClick={onClose}>關閉預覽</button>
    </header>
    {!preview && !error && <p role="status">正在讀取寄送內容…</p>}
    {preview && <>
      <CandidateInformationPages documents={preview.documents} reply={preview} />
      <div className="candidate-package-footer">
          {(!preview.preview_fingerprint || !datesReady) && <button type="button" disabled={blocked || sending} onClick={onViewDates}>查看並保存服務日期</button>}
          <button type="button" className="btn-primary-action" disabled={!preview.preview_fingerprint || !datesReady || blocked || sending}
            onClick={() => { void confirm(); }}>{resend ? '確認再次寄送' : '確認寄送'}</button>
      </div>
    </>}
    {error && <p role="alert">{error}</p>}
    {sendError && <p role="alert">{sendError}</p>}
  </section>;
}
