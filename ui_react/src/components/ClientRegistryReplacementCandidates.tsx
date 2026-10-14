import { useCallback, useEffect, useState } from 'react';
import { OrderCandidateQueryPanel } from './OrderCandidateQueryPanel';
import { OrderCandidateContactStatusPanel } from './OrderCandidateContactStatusPanel';
import { OrderFormalRecommendationPanel } from './OrderFormalRecommendationPanel';

interface EditState { dirty: boolean; busy: boolean }
interface Props {
  caseNo: string;
  disabled: boolean;
  onObserved: () => Promise<void>;
  onStateChange: (state: EditState) => void;
}

export function ClientRegistryReplacementCandidates({ caseNo, disabled, onObserved, onStateChange }: Props) {
  const [step, setStep] = useState(0);
  const [revision, setRevision] = useState(1);
  const [queryState, setQueryState] = useState<EditState>({ dirty: false, busy: false });
  const [contactState, setContactState] = useState<EditState>({ dirty: false, busy: false });
  const [planState, setPlanState] = useState<EditState>({ dirty: false, busy: false });
  const [readingBack, setReadingBack] = useState(false);
  const busy = queryState.busy || contactState.busy || planState.busy || readingBack;
  const dirty = queryState.dirty || contactState.dirty || planState.dirty;
  useEffect(() => { onStateChange({ dirty, busy }); }, [dirty, busy, onStateChange]);
  useEffect(() => () => { onStateChange({ dirty: false, busy: false }); }, [onStateChange]);
  const observed = useCallback(() => {
    setRevision((value) => value + 1);
    setReadingBack(true);
    void onObserved().finally(() => setReadingBack(false));
  }, [onObserved]);
  return <div className="registry-replacement-workflow" aria-label="接任月嫂選擇與確認">
    <h4>選擇接任月嫂</h4>
    <p className="registry-section-note">查詢並勾選人選，確認意願後選定正式推薦月嫂。推薦方案仍須完成客戶確認、契約與正式排班，才會列入上方正式指派。</p>
    <nav className="registry-replacement-steps" aria-label="接任月嫂辦理步驟">
      {['1. 查詢與選擇人選', '2. 確認接案意願', '3. 選定與確認推薦'].map((label, index) => <button key={label} type="button" aria-pressed={step === index} disabled={disabled || busy} onClick={() => setStep(index)}>{label}</button>)}
    </nav>
    <fieldset disabled={disabled} className="registry-terms-fieldset">
      <div hidden={step !== 0}>
        <OrderCandidateQueryPanel caseNo={caseNo} includeMultiCaregiver={false} onEditStateChange={setQueryState} onPoolReadback={() => { observed(); setStep(1); }} />
      </div>
      <div hidden={step !== 1}>
        <OrderCandidateContactStatusPanel caseNo={caseNo} revision={revision} focusWillingness onObserved={observed} onAddCandidates={() => setStep(0)} onEditStateChange={setContactState} />
        <button type="button" disabled={busy} onClick={() => setStep(2)}>下一步：選定推薦月嫂</button>
      </div>
      <div hidden={step !== 2}>
        <OrderFormalRecommendationPanel caseNo={caseNo} revision={revision} onObserved={observed} onEditStateChange={setPlanState} />
      </div>
    </fieldset>
  </div>;
}
