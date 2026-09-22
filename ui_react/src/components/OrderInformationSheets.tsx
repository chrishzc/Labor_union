import { useEffect, useState } from 'react';
import { queryOrderInformation, type OrderInformation } from '../api/orders/order_information_client';
import type { AssignmentPlan } from '../api/orders/order_query_schemas';
import { candidateContactPoolClient, type CandidateContactPool, type CandidateInformationPreview, type CandidateWeeklyServicePreview } from '../api/scheduling/candidate_contact_pool_client';

const INFO_FIELDS = {
  1: [
    ['f_101_c1', '案件編號'], ['f_102_c2', '服務人員'], ['f_103_c3', '客戶姓名'],
    ['f_104_c4', '服務開始日'], ['f_105_c5', '服務結束日'],
    ['service_time', '每日服務時段'], ['f_106_c6', '每日服務時數'],
    ['service_type', '服務方式'], ['f_107_c7', '希望服務天數'],
    ['f_108_c8', '服務地址'], ['f_109_c9', '是否需要下廚'], ['baby_info', '寶寶資訊'],
    ['f_112_cc', '訂金金額'], ['f_113_cd', '預計訂金繳款日'],
    ['f_116_cg', '第一期金額'], ['f_117_ch', '預計第一期繳款日'],
    ['f_118_ci', '第二期金額'], ['f_119_cj', '預計第二期繳款日'],
    ['f_120_ck', '樓層費'], ['f_121_cl', '樓層費預計繳款日'],
    ['f_122_cm', '客戶應付總額'],
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

type DisplayField = { label: string; value: string; missing: boolean };
type DisplaySection = { title: string; fields: DisplayField[] };
const MONEY_FIELD_IDS = new Set([
  'f_112_cc', 'f_116_cg', 'f_118_ci', 'f_120_ck', 'f_122_cm',
]);

function candidateSections(preview: CandidateInformationPreview): DisplaySection[] {
  return preview.line_sections.map((section) => ({
    title: section.title,
    fields: section.rows.map(([label, value]) => ({ label, value, missing: value === '待確認' })),
  }));
}

const LINE_SECTION_FIELDS = {
  1: [
    ['服務約定', [
      ['f_104_c4', '預計服務開始日'], ['f_105_c5', '預計服務結束日'],
      ['service_time', '每日服務時段'], ['f_106_c6', '每日服務時數'],
      ['service_type', '服務方式'], ['f_107_c7', '希望服務天數'],
      ['f_109_c9', '下廚需求'], ['baby_info', '寶寶資訊'],
    ]],
    ['客戶付款約定', [
      ['f_112_cc', '訂金金額'], ['f_113_cd', '預計訂金繳款日'],
      ['f_116_cg', '第一期金額'], ['f_117_ch', '預計第一期繳款日'],
      ['f_118_ci', '第二期金額'], ['f_119_cj', '預計第二期繳款日'],
      ['f_120_ck', '樓層費'], ['f_121_cl', '樓層費預計繳款日'],
      ['f_122_cm', '客戶應付總額'],
    ]],
    ['其他約定', [['f_114_ce', '特殊休假日'], ['f_115_cf', '注意事項']]],
  ],
  2: [
    ['飲食與照護需求', INFO_FIELDS[2].slice(4, 11)],
    ['服務環境與費用約定', INFO_FIELDS[2].slice(11)],
  ],
} as const;

function projectedSections(kind: 1 | 2, result: OrderInformation | null): DisplaySection[] {
  return LINE_SECTION_FIELDS[kind].map(([title, configuredFields]) => ({
    title,
    fields: configuredFields.map(([id, label]) => {
      const field = result?.fields.find((item) => item.field_id === id);
      const rawValue = field?.status === 'resolved' ? field.value : null;
      const value = rawValue == null || rawValue === ''
        ? field?.status === 'absent' && field.requiredness === 'conditional'
          ? '不適用'
          : result ? '待確認' : '尚無本案資料'
        : id === 'f_109_c9' && typeof rawValue === 'boolean'
          ? rawValue ? '需要下廚' : '不需要下廚'
          : MONEY_FIELD_IDS.has(id) && typeof rawValue === 'number'
            ? `NT$ ${rawValue.toLocaleString('zh-TW')}`
          : String(rawValue);
      return { label, value, missing: rawValue == null || rawValue === '' };
    }),
  }));
}

function InformationFieldList({ fields }: { fields: DisplayField[] }) {
  return <dl>{fields.map((field, index) => <div key={`${field.label}-${index}`}>
    <dt>{field.label}</dt><dd className={field.missing ? 'is-missing' : ''}>{field.value}</dd>
  </div>)}</dl>;
}

function ContractScreenshot({ sections }: { sections: DisplaySection[] }) {
  return <figure className="order-information-contract-shot">
    <figcaption>契約重點截圖</figcaption>
    <div className="order-information-contract-shot__title">坐月子到府服務契約</div>
    {sections.map(({ title, fields }) => <section key={title}>
      <h4>{title}</h4><InformationFieldList fields={fields} />
    </section>)}
  </figure>;
}

function InformationSections({ sections }: { sections: DisplaySection[] }) {
  return <div className="order-information-two-sections">{sections.map(({ title, fields }) => fields.length > 0 && <section key={title}>
    <h4>{title}</h4><InformationFieldList fields={fields} />
  </section>)}</div>;
}

function IngredientsReference() {
  return <section className="order-information-ingredients"><h4>食材準備參考</h4><p>依原表保留供核對，不代表本案已同意或需要全部採買。</p><div><span><strong>中藥／食材</strong>四物、四君、四神、枸杞、紅棗、黃耆、杜仲、大豐草、黑豆、紅豆、白木耳、紫米、桂圓肉、米酒、麻油</span><span><strong>肉品</strong>雞腿、雞胸、排骨、豬／牛肉絲、絞肉、雞蛋、魚排</span><span><strong>蔬菜</strong>青菜、紅蘿蔔、薑、香菇、其他菇類、豆製品</span></div></section>;
}

export function OrderInformationSheets({ caseNo, assignments, initialKind = 1, onOpenCandidates }: {
  caseNo: string; assignments: AssignmentPlan['assignments']; initialKind?: 1 | 2; onOpenCandidates?: () => void;
}) {
  const [kind, setKind] = useState<1 | 2 | 'weekly'>(initialKind);
  const [assignmentId, setAssignmentId] = useState<number | null>(null);
  const [result, setResult] = useState<OrderInformation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [candidates, setCandidates] = useState<CandidateContactPool['candidates']>([]);
  const [candidateId, setCandidateId] = useState<number | null>(null);
  const [candidatePreview, setCandidatePreview] = useState<CandidateInformationPreview | null>(null);
  const [weeklyPreview, setWeeklyPreview] = useState<CandidateWeeklyServicePreview | null>(null);
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
    if (targets.length || selectedCandidateId === null || kind === 'weekly') return;
    const controller = new AbortController();
    setLoading(true); setError(false);
    void candidateContactPoolClient.previewInformation(caseNo, selectedCandidateId, kind, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setCandidatePreview(data); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [caseNo, selectedCandidateId, kind, targets.length]);

  useEffect(() => {
    setResult(null);
    if (selectedId === null || kind === 'weekly') return;
    setError(false);
    const controller = new AbortController();
    setLoading(true);
    void queryOrderInformation(caseNo, kind, selectedId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setResult(data); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [caseNo, kind, selectedId]);

  useEffect(() => {
    setWeeklyPreview(null);
    if (kind !== 'weekly' || targets.length || selectedCandidateId === null) return;
    const controller = new AbortController();
    setLoading(true); setError(false);
    void candidateContactPoolClient.previewWeeklyService(caseNo, selectedCandidateId, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setWeeklyPreview(data); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [caseNo, kind, selectedCandidateId, targets.length]);

  return <section className="order-information-sheets" aria-label="訂單資訊預覽">
    <div className="order-information-choice" aria-label="選擇訂單資訊">
      <button type="button" aria-pressed={kind === 1} onClick={() => setKind(1)}><strong>訂單資訊－1</strong><span>契約重點截圖 · 初步詢問</span></button>
      <button type="button" aria-pressed={kind === 2} onClick={() => setKind(2)}><strong>訂單資訊－2</strong><span>照護與飲食需求 · 分開確認</span></button>
      <button type="button" aria-pressed={kind === 'weekly'} onClick={() => setKind('weekly')}><strong>每週服務時間說明</strong><span>預計工作日與每週時數</span></button>
    </div>
    {targets.length > 1 && <label>預覽哪一段服務
      <select value={selectedId ?? ''} onChange={(event) => setAssignmentId(event.target.value ? Number(event.target.value) : null)}>
        <option value="">請選擇服務人員與區段</option>
        {targets.map((item) => <option key={item.assignment_id} value={item.assignment_id!}>第 {item.sequence} 段 · 月嫂 {item.staff_id} · {item.assigned_start_date}～{item.assigned_end_date}</option>)}
      </select>
    </label>}
    <p className="order-case-review-note">三份內容都可在寄送前預覽。訂單資訊－1使用契約約定的預計服務與付款日期。</p>
    {!targets.length && candidates.length > 0 && <label>預覽收件月嫂<select value={selectedCandidateId ?? ''} onChange={(event) => setCandidateId(event.target.value ? Number(event.target.value) : null)}><option value="">請選擇月嫂</option>{candidates.map((item) => <option key={item.id} value={item.id}>{item.staff_name} · {item.service_start_date}～{item.service_end_date}</option>)}</select></label>}
    {selectedId === null && !candidatePreview && !weeklyPreview && !loading && <p role="status">{targets.length > 1 ? '請選擇服務區段以查閱本案資料。' : candidates.length ? '請選擇月嫂，查閱本次詢問內容。' : '請先在候選月嫂清單加入要詢問的人選，即可預覽完整資訊。'}</p>}
    {loading && <p role="status">正在讀取本案資訊…</p>}
    {error && <p role="alert">本案資訊暫時無法讀取；下方僅顯示欄位，不代表資料已完整。</p>}
    {result && result.warnings.length > 0 && <p role="status">部分資料尚未提供，已在欄位中標示；不影響目前資料的預覽。</p>}
    {result && !result.can_render && <p role="alert">模板或資料投影發生技術錯誤，目前無法完成預覽。</p>}
    {candidatePreview && kind !== 'weekly' && <article className="order-information-paper">
      <header><small>給 {candidatePreview.staff_name}</small><h3>訂單資訊－{kind}</h3><p>{kind === 1 ? '依契約重點欄位排列' : '照護需求已依主題分組'}</p></header>
      {kind === 1 ? <ContractScreenshot sections={candidateSections(candidatePreview)} /> : <><InformationSections sections={candidateSections(candidatePreview)} /><IngredientsReference /></>}
    </article>}
    {targets.length > 0 && kind !== 'weekly' && <article className="order-information-paper">
      <header><small>案件 {caseNo}</small><h3>給服務人員的訂單資訊－{kind}</h3><p>{kind === 1 ? '先確認服務條件與接案意願' : '確認個別照護需求與服務準備'}</p></header>
      {kind === 1 ? <ContractScreenshot sections={projectedSections(1, result)} /> : <><InformationSections sections={projectedSections(2, result)} /><IngredientsReference /></>}
    </article>}
    {kind === 'weekly' && targets.length > 0 && <p role="status">目前方案的每週服務內容可在「推薦月嫂」步驟直接預覽。</p>}
    {weeklyPreview && <article className="order-information-paper"><header><h3>每週服務時間說明</h3><p>依目前候選服務期間推算，尚未建立正式排班。</p></header>
      <div className="formal-recommendation-weekly-preview"><table><thead><tr><th>週次</th><th>服務人員</th><th>期間</th><th>工作日</th><th>時數</th></tr></thead><tbody>
        {weeklyPreview.rows.map((item) => <tr key={item.serial_number}><td>第 {item.serial_number} 週</td><td>{item.staff_name}</td><td>{item.week_start_date}～{item.week_end_date}</td><td>{item.weekly_work_days} 日</td><td>{item.weekly_hours} 小時</td></tr>)}
      </tbody></table></div>
    </article>}
    <div className="order-case-action-row">{onOpenCandidates && kind !== 'weekly' && <button type="button" onClick={onOpenCandidates}>到候選月嫂清單寄送資訊－{kind}</button>}<span>從個別月嫂的寄送入口確認收件人與內容後，才會建立寄送任務。</span></div>
  </section>;
}
