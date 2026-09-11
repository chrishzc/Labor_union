import { useEffect, useState } from 'react';
import { queryOrderInformation, type OrderInformation } from '../api/orders/order_information_client';
import type { AssignmentPlan } from '../api/orders/order_query_schemas';
import { candidateContactPoolClient, type CandidateContactPool, type CandidateInformationPreview } from '../api/scheduling/candidate_contact_pool_client';

const INFO_FIELDS = {
  1: [
    ['f_101_c1', '案件編號'], ['f_102_c2', '服務人員'], ['f_103_c3', '客戶姓名'],
    ['f_104_c4', '服務開始日'], ['f_105_c5', '服務結束日'],
    ['service_time', '每日服務時段'], ['service_type', '服務方式'], ['f_107_c7', '希望服務天數'],
    ['f_108_c8', '服務地址'], ['baby_info', '寶寶資訊'],
    ['f_110_ca', '總薪資'], ['f_111_cb', '預計發薪日'],
    ['f_114_ce', '特殊休假日'], ['f_115_cf', '備註'],
  ],
  2: [
    ['f_201_e1', '客戶姓名'], ['f_202_e2', '聯絡電話'], ['f_203_e3', '案件編號'], ['f_205_e5', '服務地址'],
    ['f_206_e6', '飲食習慣與中藥接受度'], ['f_207_e7', '可否接受蛋奶素餐食'],
    ['f_208_e8', '餐飲含酒比例'], ['f_209_e9', '料理用油'], ['f_210_ea', '過敏體質'],
    ['f_211_eb', '特殊照護注意事項'], ['f_212_ec', '餐點喜忌'], ['f_213_ed', '現有烹煮工具'],
    ['f_214_ee', '洗澡水準備'], ['f_215_ef', '哺乳方式'], ['f_216_f0', '三節計費約定'],
    ['f_217_f1', '胎數與特殊計費'], ['f_218_f2', '服務樓層方式'],
    ['f_219_f3', '停車位'], ['f_220_f4', '服務時間內的其他寶寶'],
  ],
} as const;

export function OrderInformationSheets({ caseNo, assignments, initialKind = 1, onOpenCandidates }: {
  caseNo: string; assignments: AssignmentPlan['assignments']; initialKind?: 1 | 2; onOpenCandidates?: () => void;
}) {
  const [kind, setKind] = useState<1 | 2>(initialKind);
  const [assignmentId, setAssignmentId] = useState<number | null>(null);
  const [result, setResult] = useState<OrderInformation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [candidates, setCandidates] = useState<CandidateContactPool['candidates']>([]);
  const [candidateId, setCandidateId] = useState<number | null>(null);
  const [candidatePreview, setCandidatePreview] = useState<CandidateInformationPreview | null>(null);
  const targets = assignments.filter((item) => item.assignment_id != null);
  const selectedId = assignmentId ?? (targets.length === 1 ? targets[0]!.assignment_id! : null);
  const selectedCandidateId = candidateId ?? (candidates.length === 1 ? candidates[0]!.id : null);

  useEffect(() => {
    if (targets.length) return;
    const controller = new AbortController();
    setCandidates([]); setCandidateId(null); setError(false);
    void candidateContactPoolClient.query(caseNo, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setCandidates(data.candidates.filter((item) => item.status !== 'withdrawn')); })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [caseNo, targets.length]);

  useEffect(() => {
    setCandidatePreview(null);
    if (targets.length || selectedCandidateId === null) return;
    let current = true;
    setLoading(true); setError(false);
    void candidateContactPoolClient.previewInformation(caseNo, selectedCandidateId, kind)
      .then((data) => { if (current) setCandidatePreview(data); })
      .catch(() => { if (current) setError(true); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [caseNo, selectedCandidateId, kind, targets.length]);

  useEffect(() => {
    setResult(null);
    if (selectedId === null) return;
    setError(false);
    const controller = new AbortController();
    setLoading(true);
    void queryOrderInformation(caseNo, kind, selectedId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setResult(data); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [caseNo, kind, selectedId]);

  return <section className="order-information-sheets" aria-label="訂單資訊預覽">
    <div className="order-information-choice" aria-label="選擇訂單資訊">
      <button type="button" aria-pressed={kind === 1} onClick={() => setKind(1)}><strong>訂單資訊－1</strong><span>服務條件與薪資 · 初步詢問</span></button>
      <button type="button" aria-pressed={kind === 2} onClick={() => setKind(2)}><strong>訂單資訊－2</strong><span>照護與飲食需求 · 分開確認</span></button>
    </div>
    {targets.length > 1 && <label>預覽哪一段服務
      <select value={selectedId ?? ''} onChange={(event) => setAssignmentId(event.target.value ? Number(event.target.value) : null)}>
        <option value="">請選擇服務人員與區段</option>
        {targets.map((item) => <option key={item.assignment_id} value={item.assignment_id!}>第 {item.sequence} 段 · 月嫂 {item.staff_id} · {item.assigned_start_date}～{item.assigned_end_date}</option>)}
      </select>
    </label>}
    <p className="order-case-review-note">資訊－1／－2 可分開詢問。不必等 BeClass 完成；初步詢問使用預計期間，尚未確定的資料顯示「待確認」。</p>
    {!targets.length && candidates.length > 0 && <label>預覽收件月嫂<select value={selectedCandidateId ?? ''} onChange={(event) => setCandidateId(event.target.value ? Number(event.target.value) : null)}><option value="">請選擇月嫂</option>{candidates.map((item) => <option key={item.id} value={item.id}>{item.staff_name} · {item.service_start_date}～{item.service_end_date}</option>)}</select></label>}
    {selectedId === null && !candidatePreview && !loading && <p role="status">{targets.length > 1 ? '請選擇服務區段以查閱本案資料。' : candidates.length ? '請選擇月嫂，查閱本次詢問內容。' : '請先在候選月嫂清單加入要詢問的人選，即可預覽與分開寄送兩份資訊。'}</p>}
    {loading && <p role="status">正在讀取本案資訊…</p>}
    {error && <p role="alert">本案資訊暫時無法讀取；下方僅顯示欄位，不代表資料已完整。</p>}
    {result && !result.can_render && <p role="status">部分資料尚未齊全，請核對標示為「待補」的欄位。</p>}
    {candidatePreview && <article className="order-information-paper"><h3>給 {candidatePreview.staff_name} 的訂單資訊－{kind}</h3><pre style={{ whiteSpace: 'pre-wrap', font: 'inherit' }}>{candidatePreview.text}</pre></article>}
    {targets.length > 0 && <article className="order-information-paper">
      <header><small>案件 {caseNo}</small><h3>給服務人員的訂單資訊－{kind}</h3><p>{kind === 1 ? '先確認服務條件與接案意願' : '確認個別照護需求與服務準備'}</p></header>
      <dl>{INFO_FIELDS[kind].map(([id, label]) => {
        const field = result?.fields.find((item) => item.field_id === id);
        const value = field?.status === 'resolved' ? field.value : null;
        return <div key={id}><dt>{label}</dt><dd className={value == null || value === '' ? 'is-missing' : ''}>{value == null || value === '' ? result ? '待確認' : '尚無本案資料' : String(value)}</dd></div>;
      })}</dl>
      {kind === 2 && <section className="order-information-ingredients"><h4>食材準備參考</h4><p>依原表保留供核對，不代表本案已同意或需要全部採買。</p><div><span>中藥／食材：四物、四君、四神、枸杞、紅棗、黃耆、杜仲、大豐草、黑豆、紅豆、白木耳、紫米、桂圓肉、米酒、麻油</span><span>肉品：雞腿、雞胸、排骨、豬／牛肉絲、絞肉、雞蛋、魚排</span><span>蔬菜：青菜、紅蘿蔔、薑、香菇、其他菇類、豆製品</span></div></section>}
    </article>}
    <div className="order-case-action-row">{onOpenCandidates && <button type="button" onClick={onOpenCandidates}>到候選月嫂清單寄送資訊－{kind}</button>}<span>從個別月嫂的寄送入口確認收件人與內容後，才會建立寄送任務。</span></div>
  </section>;
}
