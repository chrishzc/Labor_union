/** Current replacement of the retired per-case settlement panel. */
import { SubsidyPeriodWorkbench } from './SubsidyPeriodWorkbench';
export function SubsidyAdvanceSettlementPanel({onOpenImport}:{initialCaseNo?:string;onOpenImport:()=>void;compact?:boolean;onLockedChange?:(locked:boolean)=>void;onSettled?:()=>void}) {
  return <><p>代墊回收由政府整期入款核銷同步處理。</p><SubsidyPeriodWorkbench onOpenCase={onOpenImport}/></>;
}
