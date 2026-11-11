import { ServiceHandoverWorkbench } from '../components/ServiceStartSubstituteWorkbench';
import { ManagementPageHeader } from '../components/ManagementPageHeader';
import { parseServiceHandoverLink } from '../adapters/scheduling/service_handover_navigation';

export function ServiceHandoverPage() {
  const link=parseServiceHandoverLink(window.location.hash);
  return <main><ManagementPageHeader title="服務中換人" />
    {!link ? <p role="alert">請從案件的「服務安排」開啟「服務中換人」。</p> : <ServiceHandoverWorkbench key={`${link.caseNo}:${link.assignmentId??''}`} caseNo={link.caseNo} assignmentId={link.assignmentId??undefined}/>}
  </main>;
}
