import { ServiceHandoverWorkbench } from '../components/ServiceStartSubstituteWorkbench';
import { parseServiceHandoverLink } from '../adapters/scheduling/service_handover_navigation';

export function ServiceHandoverPage() {
  const link=parseServiceHandoverLink(window.location.hash);
  return <main><h1>服務中換人</h1>
    {!link ? <p role="alert">請從案件服務安排的服務中換人按鈕開啟。</p> : <ServiceHandoverWorkbench key={`${link.caseNo}:${link.assignmentId??''}`} caseNo={link.caseNo} assignmentId={link.assignmentId??undefined}/>}
  </main>;
}
