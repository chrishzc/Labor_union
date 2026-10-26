/** Government cash is reconciled by a selected whole period. */
import { useState } from 'react';
import { SubsidyPeriodWorkbench } from './SubsidyPeriodWorkbench';
import { CaseSubsidyDetailDrawer } from './CaseSubsidyDetailDrawer';
export function OrderGovernmentSubsidyLane({expanded,onExpandedChange}:{expanded?:boolean;onExpandedChange?:(open:boolean)=>void}) {
  const [localOpen,setLocalOpen]=useState(false);
  const [caseNo,setCaseNo]=useState<string|null>(null);
  const open=expanded??localOpen;
  return <><button type="button" className={`order-v2-lane ${open?'active':''}`} aria-expanded={open} onClick={()=>{setLocalOpen(!open);onExpandedChange?.(!open);}}><span><strong>政府補助結算支線</strong><small>查看月、季、年整期入款與代墊回收。</small></span><b>{open?'檢視中':'開啟'}</b></button>
    {open&&<section style={{gridColumn:'1 / -1'}} aria-label="政府補助結算支線工作清單"><SubsidyPeriodWorkbench onOpenCase={setCaseNo}/></section>}
    {caseNo&&<CaseSubsidyDetailDrawer caseNo={caseNo} onClose={()=>setCaseNo(null)} onOpenBank={()=>{window.location.hash='finance';}} onChanged={()=>{}}/>}
  </>;
}
