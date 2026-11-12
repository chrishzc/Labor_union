import { useEffect, useState } from 'react';
import {
  officialServiceDateCorrectionClient as client,
  type AttributionFundingInput,
  type AttributionFundingReview,
} from '../api/orders/official_service_date_correction_client';
import { useStaffIdentityLabels } from './StaffIdentityProvider';

const fundingLabels = { client: '自備款', subsidy: '補助款', unsplit: '未分來源' };
const money = (amount: number) => `NT$ ${amount.toLocaleString('zh-TW')}`;

export function OrderAttributionFundingReview({ caseNo, revision, onSaved }: {
  caseNo: string;
  revision: number;
  onSaved: () => void;
}) {
  const staff = useStaffIdentityLabels();
  const [review, setReview] = useState<AttributionFundingReview | null>(null);
  const [preview, setPreview] = useState<{ result: AttributionFundingReview; input: AttributionFundingInput; key: string } | null>(null);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [evidence, setEvidence] = useState('');
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [saved, setSaved] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setReview(null);
    setPreview(null);
    setAmounts({});
    setEvidence('');
    setMessage('');
    void client.queryFundingReview(caseNo, controller.signal).then(result => {
      if (!controller.signal.aborted) setReview(result.pending ? result : null);
    }).catch(() => {
      if (!controller.signal.aborted) setMessage('暫時無法讀取排班帳務待核對。');
    });
    return () => controller.abort();
  }, [caseNo, revision, reload]);

  if (!review) return saved ? <p role="status">分來源拆付已確認。</p> : message
    ? <p role="alert">{message} <button type="button" onClick={() => setReload(value => value + 1)}>重讀帳務</button></p> : null;

  const complete = review.assignments.every(item => /^\d+$/.test(amounts[item.assignment_id] ?? ''));
  async function submit() {
    if (!review) return;
    setBusy(true);
    setMessage('');
    try {
      if (preview) {
        await client.applyFundingReview(caseNo, preview.input, preview.result.preview_fingerprint, preview.key);
        setSaved(true);
        setReview(null);
        setPreview(null);
        setOpen(false);
        onSaved();
      } else {
        const input = { evidence: evidence.trim(), selections: review.assignments.map(item => ({
          assignment_id: item.assignment_id, subsidy_ntd: Number(amounts[item.assignment_id]),
        })) };
        const result = await client.previewFundingReview(caseNo, input);
        if (!result.pending) throw new Error('這筆帳務已核對，請重讀帳務。');
        setPreview({ result, input, key: crypto.randomUUID() });
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '分來源拆付暫時無法處理。');
    } finally {
      setBusy(false);
    }
  }

  return <section className="formal-recommendation-inline-form" aria-label="排班帳務待核對">
    <h3>排班帳務待核對</h3>
    <p>正式排班已儲存。受影響的舊應付暫停核銷，已完成的核銷仍保留在原受款人及來源。</p>
    {!open ? <button type="button" onClick={() => setOpen(true)}>補齊分來源金額</button> :
      <div>
        <p>本次需分配的原補助款合計 {money(review.subsidy_ntd)}。各區段的自備款由應付扣除補助款。</p>
        {review.sources.map((item, index) => <p key={index}>
          {staff.label(item.staff_id)} · 原{fundingLabels[item.kind]} {money(item.amount_ntd)} ·
          已核銷 {item.settled_ntd === null ? '待核對' : money(item.settled_ntd)}
        </p>)}
        {review.payment_evidence_missing && <p role="status">請先核對原銀行流水與核銷來源，再重讀帳務。</p>}
        {preview ? <div aria-label="分來源拆付預覽">
          {preview.result.installments.map((item, index) => <p key={index}>
            {staff.label(item.staff_id)} · {fundingLabels[item.kind]} · 更正後應付 {money(item.amount_ntd)}
            {' · '}原核銷 {money(item.settled_ntd ?? 0)} · 待付 {money(item.payable_ntd)} · 新增追償 {money(item.recovery_ntd)}
          </p>)}
          <button type="button" disabled={busy} onClick={() => setPreview(null)}>返回金額編輯</button>
        </div> : <fieldset disabled={busy}>
          {review.assignments.map(item => <label key={item.assignment_id}>
            {staff.label(item.staff_id)} · {item.service_dates.at(0)} 至 {item.service_dates.at(-1)}
            {' · '}應付 {money(item.amount_ntd)} · 補助款
            <input type="number" min={0} max={item.amount_ntd} step={1}
              value={amounts[item.assignment_id] ?? ''}
              onChange={event => setAmounts(current => ({ ...current, [item.assignment_id]: event.target.value }))} />
          </label>)}
          <label>分來源金額核對依據 <input maxLength={500} value={evidence}
            onChange={event => setEvidence(event.target.value)} /></label>
        </fieldset>}
        <button type="button" disabled={busy || (!preview && (!complete || !evidence.trim() || review.payment_evidence_missing))}
          onClick={() => void submit()}>{preview ? '確認分來源拆付' : '預覽分來源拆付'}</button>
        <button type="button" disabled={busy} onClick={() => setReload(value => value + 1)}>重讀帳務</button>
        {message && <p role="alert">{message}</p>}
      </div>}
  </section>;
}
