/** 政府補助唯一報表入口，沿用既有 Reporting 畫面、欄位與 XLSX 服務。 */
import {OperationsReportsWorkspace} from './reports/OperationsReportsWorkspace';

export function FinanceGovernmentSubsidyList({onCase,revision=0}: {onCase:(caseNo:string)=>void;revision?:number}) {
 return <OperationsReportsWorkspace mode="subsidy" onCase={onCase} revision={revision}/>;
}
