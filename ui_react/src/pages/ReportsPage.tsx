/** 營運報表與月嫂分析入口；補助報表唯一入口位於帳務工作台。 */
import React, {useState} from 'react';
import {OperationsReportsWorkspace} from '../components/reports/OperationsReportsWorkspace';
import {StaffPerformancePanel} from '../components/reports/StaffPerformancePanel';
import {useUnsavedNavigation} from '../components/UnsavedChanges';

export const ReportsPage: React.FC = () => {
  const [initialStaffId] = useState(() => {
    const value = Number(new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('staff_id'));
    return Number.isSafeInteger(value) && value > 0 ? value : undefined;
  });
  const [workspace, setWorkspace] = useState<'operations' | 'staff'>(initialStaffId ? 'staff' : 'operations');
  const { requestLeave } = useUnsavedNavigation();
  return <><nav className="reports-analysis-navigation" aria-label="報表工作區">
    <button type="button" aria-pressed={workspace === 'operations'} onClick={() => requestLeave(() => setWorkspace('operations'))}>營運報表</button>
    <button type="button" aria-pressed={workspace === 'staff'} onClick={() => requestLeave(() => setWorkspace('staff'))}>月嫂表現分析</button>
  </nav>{workspace === 'operations' ? <OperationsReportsWorkspace mode="operations" /> : <StaffPerformancePanel initialStaffId={initialStaffId} />}</>;
};

export default ReportsPage;
